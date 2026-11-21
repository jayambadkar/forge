using System.Globalization;
using System.Text;
using System.Text.Json;
using Forge.Api;

var builder = WebApplication.CreateBuilder(args);
builder.WebHost.UseUrls("http://0.0.0.0:43124");
builder.Services.AddCors(options =>
{
    options.AddDefaultPolicy(policy => policy.AllowAnyOrigin().AllowAnyHeader().AllowAnyMethod());
});

var root = Environment.GetEnvironmentVariable("FORGE_ROOT") ?? FindRoot(Directory.GetCurrentDirectory());
var catalog = new Catalog(root);
var work = new WorkStore(root);
var reportPath = Path.Combine(root, "ml", "report.json");
if (File.Exists(reportPath))
{
    try
    {
        using var report = JsonDocument.Parse(File.ReadAllText(reportPath));
        if (report.RootElement.TryGetProperty("inner_winner", out var winner))
            work.MlModel = winner.GetString() ?? work.MlModel;
    }
    catch (JsonException)
    {
        // A partial report must not stop the desk.
    }
}
var llmOn = Environment.GetEnvironmentVariable("FORGE_LLM") == "1";
var provider = (Environment.GetEnvironmentVariable("FORGE_LLM_PROVIDER") ?? "").Trim().ToLowerInvariant();
var xaiKey = Environment.GetEnvironmentVariable("XAI_API_KEY");
var openKey = Environment.GetEnvironmentVariable("OPENROUTER_API_KEY");
var useXai = provider == "xai" || (provider != "openrouter" && !string.IsNullOrWhiteSpace(xaiKey) && string.IsNullOrWhiteSpace(openKey));
var useOpen = provider == "openrouter" || (provider != "xai" && !string.IsNullOrWhiteSpace(openKey));
if (llmOn && useXai && !string.IsNullOrWhiteSpace(xaiKey) && !useOpen)
{
    var model = Environment.GetEnvironmentVariable("FORGE_LLM_MODEL") ?? "grok-4";
    work.LlmMode = model;
    work.AgentNote = $"Decided by policy engine {WorkStore.EngineVersion}. xAI adjudicator {model} is configured and was not applied to the scored verdict.";
}
else if (llmOn && useOpen && !string.IsNullOrWhiteSpace(openKey))
{
    var model = Environment.GetEnvironmentVariable("FORGE_LLM_MODEL") ?? "x-ai/grok-4";
    work.LlmMode = model;
    work.AgentNote = $"Decided by policy engine {WorkStore.EngineVersion}. OpenRouter adjudicator {model} is configured and was not applied to the scored verdict.";
}
else if (llmOn && !string.IsNullOrWhiteSpace(xaiKey))
{
    var model = Environment.GetEnvironmentVariable("FORGE_LLM_MODEL") ?? "grok-4";
    work.LlmMode = model;
    work.AgentNote = $"Decided by policy engine {WorkStore.EngineVersion}. xAI adjudicator {model} is configured and was not applied to the scored verdict.";
}
work.SyncPolicy(catalog.Seeds(), catalog.SyncedAt);

builder.Services.AddSingleton(catalog);
builder.Services.AddSingleton(work);
builder.Services.AddSingleton<RunHub>();

var app = builder.Build();
app.UseCors();

app.MapGet("/api/health", (Catalog books) => new
{
    ok = true,
    book = books.BookKind,
    environment = "Production · EU-West",
    syncedAt = books.SyncedAt,
    institutions = Catalog.Ids.Where(books.Known).ToArray(),
});

app.MapGet("/api/institutions", (Catalog books) => books.Institutions());

app.MapGet("/api/dashboard", (Catalog books, WorkStore store) => books.Dashboard(store.Get));

app.MapGet("/api/cases", (Catalog books, WorkStore store, string? institution, string? verdict, string? reason, string? q, string? rule, string? risk, string? status, string? sort, int? limit, int? offset) =>
    books.Cases(institution, verdict, reason, q, Math.Clamp(limit ?? 25, 1, 5000), Math.Max(0, offset ?? 0), rule, risk, status, sort, store.Get));

app.MapGet("/api/cases/{institution}/{caseId}", (Catalog books, WorkStore store, string institution, string caseId) =>
{
    var detail = books.Detail(institution, caseId, store.Get(institution, caseId), store.Audit(200, institution, caseId, null, null, null));
    return detail is null ? Results.NotFound() : Results.Ok(detail);
});

app.MapGet("/api/cases/{institution}/{caseId}/related", (Catalog books, string institution, string caseId) => books.Related(institution, caseId));

app.MapPost("/api/cases/{institution}/{caseId}/actions", (Catalog books, WorkStore store, string institution, string caseId, ActionRequest request) =>
{
    var detail = books.Detail(institution, caseId, store.Get(institution, caseId), []);
    if (detail is null) return Results.NotFound();
    try
    {
        var row = store.Apply(institution, caseId, request.Action, request.Actor, request.Verdict, request.Note, detail.Decision?.Verdict ?? "");
        return Results.Ok(row);
    }
    catch (ArgumentException ex)
    {
        return Results.BadRequest(new { error = ex.Message });
    }
});

app.MapGet("/api/audit", (WorkStore store, string? institution, string? caseId, string? kind, string? action, string? q, int? limit) =>
    store.Audit(limit ?? 200, institution, caseId, kind, action, q));

app.MapGet("/api/notifications", (WorkStore store) =>
{
    var (unread, items) = store.Notifications();
    return new { unread, items };
});

app.MapPost("/api/notifications/read", (WorkStore store) =>
{
    store.MarkRead();
    return Results.Ok(new { ok = true });
});

app.MapGet("/api/export", (Catalog books, WorkStore store, string? format, string? institution, string? verdict, string? reason, string? q, string? rule, string? risk, string? status) =>
{
    var page = books.Cases(institution, verdict, reason, q, 5000, 0, rule, risk, status, "opened", store.Get);
    var csv = string.Equals(format, "csv", StringComparison.OrdinalIgnoreCase);
    if (csv)
    {
        var builder = new StringBuilder();
        builder.AppendLine("case_id,institution,customer,verdict,reason_code,status,assignee,sla_days,amount_gbp,reason,evidence");
        foreach (var row in page.Cases)
        {
            var facts = books.Facts(row.Institution, row.CaseId);
            var evidence = string.Join(" ", facts.Evidence);
            builder.AppendLine(string.Join(",",
                Csv(row.CaseId), Csv(row.Institution), Csv(row.CustomerName), Csv(row.Verdict), Csv(row.ReasonCode),
                Csv(row.Status), Csv(row.Assignee), row.SlaDays.ToString(CultureInfo.InvariantCulture), (row.Amount ?? 0).ToString("0.00", CultureInfo.InvariantCulture),
                Csv(row.Reason), Csv(evidence)));
        }
        return Results.File(Encoding.UTF8.GetBytes(builder.ToString()), "text/csv", "forge-decisions.csv");
    }
    var lines = new StringBuilder();
    foreach (var row in page.Cases)
    {
        var facts = books.Facts(row.Institution, row.CaseId);
        var payload = new
        {
            case_id = row.CaseId,
            alert_ids = facts.Alerts,
            verdict = row.Verdict,
            reason_code = row.ReasonCode,
            reason = row.Reason,
            evidence = facts.Evidence,
        };
        lines.AppendLine(JsonSerializer.Serialize(payload));
    }
    return Results.File(Encoding.UTF8.GetBytes(lines.ToString()), "application/x-ndjson", "forge-decisions.jsonl");
});

app.MapGet("/api/audit/export", (WorkStore store, string? format, string? institution, string? caseId, string? kind) =>
{
    var rows = store.Audit(5000, institution, caseId, kind, null, null);
    var csv = string.Equals(format, "csv", StringComparison.OrdinalIgnoreCase);
    if (csv)
    {
        var builder = new StringBuilder();
        builder.AppendLine("at,kind,actor,action,institution,case_id,verdict,reason_code,model,ml_model,confidence,job_id,before,after,note,detail");
        foreach (var row in rows)
        {
            builder.AppendLine(string.Join(",",
                Csv(row.At), Csv(row.Kind), Csv(row.Actor), Csv(row.Action), Csv(row.Institution), Csv(row.CaseId),
                Csv(row.Verdict), Csv(row.ReasonCode), Csv(row.Model), Csv(row.MlModel),
                row.Confidence?.ToString("0.00", CultureInfo.InvariantCulture) ?? "", Csv(row.JobId), Csv(row.Before), Csv(row.After), Csv(row.Note), Csv(row.Detail)));
        }
        return Results.File(Encoding.UTF8.GetBytes(builder.ToString()), "text/csv", "forge-audit.csv");
    }
    var lines = new StringBuilder();
    foreach (var row in rows) lines.AppendLine(JsonSerializer.Serialize(row));
    return Results.File(Encoding.UTF8.GetBytes(lines.ToString()), "application/x-ndjson", "forge-audit.jsonl");
});

app.MapGet("/api/models", (Catalog books) =>
{
    var path = Path.Combine(books.Root, "ml", "report.json");
    if (!File.Exists(path)) return Results.Json(new { available = false });
    return Results.Content(File.ReadAllText(path), "application/json");
});

app.MapGet("/api/runs", (WorkStore store) => store.Jobs());

app.MapPost("/api/runs", (RunRequest request, RunHub hub) =>
{
    var mode = request.Mode is "run" or "replay" ? request.Mode : "replay";
    try
    {
        return Results.Ok(hub.Start(request.Institution, mode));
    }
    catch (ArgumentException ex)
    {
        return Results.BadRequest(new { error = ex.Message });
    }
});

app.MapGet("/api/runs/{id}/events", async (string id, HttpContext context, RunHub hub) =>
{
    await hub.Stream(id, context.Response, context.RequestAborted);
});

app.Run();

static string Csv(string? value)
{
    var text = value ?? "";
    if (text.Contains('"') || text.Contains(',') || text.Contains('\n'))
        return "\"" + text.Replace("\"", "\"\"") + "\"";
    return text;
}

static string FindRoot(string start)
{
    var dir = new DirectoryInfo(start);
    while (dir is not null)
    {
        if (File.Exists(Path.Combine(dir.FullName, "system", "run"))) return dir.FullName;
        dir = dir.Parent;
    }
    return start;
}
