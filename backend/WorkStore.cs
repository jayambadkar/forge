using System.Globalization;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Forge.Api;

public sealed class WorkStore
{
    public const string EngineVersion = "forge-sop-4";
    private readonly string _path;
    private readonly object _gate = new();
    private Store _store;
    private static readonly JsonSerializerOptions Json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        PropertyNameCaseInsensitive = true,
        WriteIndented = false,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    };

    public WorkStore(string root)
    {
        var dir = Path.Combine(root, "data");
        Directory.CreateDirectory(dir);
        _path = Path.Combine(dir, "workstore.json");
        if (File.Exists(_path))
            _store = JsonSerializer.Deserialize<Store>(File.ReadAllText(_path), Json) ?? new Store();
        else
            _store = new Store();
    }

    public string MlModel { get; set; } = "lightgbm-full";
    public string LlmMode { get; set; } = "not-used";
    public string AgentNote { get; set; } = "Decided by the policy engine. The LLM adjudicator was not called: set FORGE_LLM=1 and either XAI_API_KEY or OPENROUTER_API_KEY.";

    public CaseWork Get(string institution, string caseId)
    {
        lock (_gate)
        {
            if (_store.Cases.TryGetValue(Key(institution, caseId), out var state)) return ToWork(state);
            return new CaseWork("New", "", false, "", "", "");
        }
    }

    public void SyncPolicy(IEnumerable<PolicySeed> seeds, string syncedAt)
    {
        var jobId = "book-" + syncedAt.Replace(":", "").Replace("-", "");
        lock (_gate)
        {
            var latest = new Dictionary<string, AuditRow>();
            foreach (var row in _store.Events)
            {
                if (row.Action != "policy" || row.CaseId.Length == 0) continue;
                var key = Key(row.Institution, row.CaseId);
                if (!latest.ContainsKey(key)) latest[key] = row;
            }
            var changed = false;
            foreach (var seed in seeds)
            {
                var key = Key(seed.Institution, seed.CaseId);
                latest.TryGetValue(key, out var prior);
                if (prior is not null && prior.Verdict == seed.Verdict && prior.ReasonCode == seed.ReasonCode)
                {
                    if (EnsureEscalated(key, seed, syncedAt)) changed = true;
                    if (ReleaseEscalation(key, seed)) changed = true;
                    if (NoteDisagreement(seed, syncedAt)) changed = true;
                    continue;
                }
                if (!_store.Cases.TryGetValue(key, out var state))
                {
                    state = new CaseState();
                    _store.Cases[key] = state;
                }
                if (seed.Verdict == "ESCALATE" && state.DecidedVerdict.Length == 0 && state.Status is "New" or "")
                {
                    state.Status = "Escalated / MLRO";
                    state.UpdatedAt = syncedAt;
                }
                else if (seed.Verdict != "ESCALATE" && state.DecidedVerdict.Length == 0 && state.Status == "Escalated / MLRO")
                {
                    state.Status = "New";
                    state.UpdatedAt = syncedAt;
                }
                var confidence = Confidence(seed);
                _store.Events.Insert(0, new AuditRow
                {
                    Id = Guid.NewGuid().ToString("N"),
                    At = syncedAt,
                    Kind = "ai",
                    Actor = "policy-engine",
                    Action = "policy",
                    Institution = seed.Institution,
                    CaseId = seed.CaseId,
                    Detail = $"Policy {EngineVersion} returned {seed.Verdict} / {seed.ReasonCode}. {AgentNote}",
                    Agent = "policy-engine",
                    Model = EngineVersion,
                    MlModel = MlModel,
                    MlScore = confidence,
                    Llm = LlmMode,
                    JobId = jobId,
                    Verdict = seed.Verdict,
                    ReasonCode = seed.ReasonCode,
                    Reason = seed.Reason,
                    Evidence = seed.Evidence.ToList(),
                    Rules = seed.Rules.ToList(),
                    Confidence = confidence,
                });
                changed = true;
                if (NoteDisagreement(seed, syncedAt)) changed = true;
            }
            if (changed)
            {
                if (_store.Events.Count > 20000) _store.Events.RemoveRange(20000, _store.Events.Count - 20000);
                _store.ReadUpTo = _store.Events.Count;
                Save();
            }
        }
    }

    public AuditRow Apply(string institution, string caseId, string action, string actor, string? verdict, string? note, string recommended)
    {
        if (string.IsNullOrWhiteSpace(actor)) throw new ArgumentException("An analyst name is required.");
        var verb = action.Trim().ToLowerInvariant();
        lock (_gate)
        {
            var key = Key(institution, caseId);
            if (!_store.Cases.TryGetValue(key, out var state))
            {
                state = new CaseState();
                _store.Cases[key] = state;
            }
            var before = $"status={Show(state.Status)}; verdict={Show(state.DecidedVerdict)}; assignee={Show(state.Assignee)}; rfiSent={state.RfiSent}";
            var detail = verb switch
            {
                "accept" => Accept(state, recommended),
                "override" => Override(state, verdict, note),
                "assign" => Assign(state, actor),
                "rfi" => MarkRfi(state, recommended),
                _ => throw new ArgumentException("Unknown action."),
            };
            state.UpdatedAt = Now();
            var after = $"status={Show(state.Status)}; verdict={Show(state.DecidedVerdict)}; assignee={Show(state.Assignee)}; rfiSent={state.RfiSent}";
            var row = new AuditRow
            {
                Id = Guid.NewGuid().ToString("N"),
                At = state.UpdatedAt,
                Kind = "human",
                Actor = actor,
                Action = verb,
                Institution = institution,
                CaseId = caseId,
                Detail = detail,
                Before = before,
                After = after,
                Note = string.IsNullOrWhiteSpace(note) ? null : note.Trim(),
                Verdict = state.DecidedVerdict.Length == 0 ? recommended : state.DecidedVerdict,
            };
            _store.Events.Insert(0, row);
            Save();
            return row;
        }
    }

    public IReadOnlyList<AuditRow> Audit(int limit, string? institution, string? caseId, string? kind, string? action, string? q)
    {
        lock (_gate)
        {
            IEnumerable<AuditRow> rows = _store.Events;
            if (!string.IsNullOrWhiteSpace(institution)) rows = rows.Where(row => row.Institution == institution);
            if (!string.IsNullOrWhiteSpace(caseId)) rows = rows.Where(row => row.CaseId == caseId);
            if (!string.IsNullOrWhiteSpace(kind)) rows = rows.Where(row => row.Kind == kind);
            if (!string.IsNullOrWhiteSpace(action)) rows = rows.Where(row => row.Action == action);
            if (!string.IsNullOrWhiteSpace(q))
            {
                var needle = q.Trim();
                rows = rows.Where(row =>
                    row.CaseId.Contains(needle, StringComparison.OrdinalIgnoreCase)
                    || row.Actor.Contains(needle, StringComparison.OrdinalIgnoreCase)
                    || row.Detail.Contains(needle, StringComparison.OrdinalIgnoreCase)
                    || (row.ReasonCode ?? "").Contains(needle, StringComparison.OrdinalIgnoreCase));
            }
            return rows.Take(Math.Clamp(limit, 1, 5000)).ToList();
        }
    }

    public (int Unread, IReadOnlyList<AuditRow> Items) Notifications()
    {
        lock (_gate)
        {
            var unread = Math.Max(0, _store.Events.Count - _store.ReadUpTo);
            var items = _store.Events.Where(row => row.Kind is "human" or "system").Take(8).ToList();
            return (unread, items);
        }
    }

    public void MarkRead()
    {
        lock (_gate)
        {
            _store.ReadUpTo = _store.Events.Count;
            Save();
        }
    }

    public void StartJob(string id, string institution, string mode)
    {
        lock (_gate)
        {
            _store.Jobs.Insert(0, new JobRow(id, institution, mode == "run" ? "Batch run" : "Replay", Now(), "", "Running", 0));
            Save();
        }
    }

    public void FinishJob(string id, string status, int cases, string institution)
    {
        lock (_gate)
        {
            var job = _store.Jobs.FirstOrDefault(item => item.Id == id);
            if (job is null) return;
            var index = _store.Jobs.IndexOf(job);
            var finished = Now();
            _store.Jobs[index] = job with { FinishedAt = finished, Status = status, Cases = cases };
            _store.Events.Insert(0, new AuditRow
            {
                Id = Guid.NewGuid().ToString("N"),
                At = finished,
                Kind = "system",
                Actor = "batch-runner",
                Action = "batch",
                Institution = institution,
                CaseId = "",
                Detail = $"Job {id} {status.ToLowerInvariant()} for {institution}. {cases} decisions streamed.",
                JobId = id,
                Model = EngineVersion,
                Agent = "policy-engine",
            });
            Save();
        }
    }

    public IReadOnlyList<JobRow> Jobs()
    {
        lock (_gate) return _store.Jobs.Take(40).ToList();
    }

    private bool NoteDisagreement(PolicySeed seed, string syncedAt)
    {
        var expected = ExpectedVerdict(seed);
        if (expected.Length == 0 || expected == seed.Verdict) return false;
        var detail = $"Second check disagrees: model expects {expected}.";
        var already = _store.Events.Any(row =>
            row.Action == "second-check"
            && row.Institution == seed.Institution
            && row.CaseId == seed.CaseId
            && row.Detail == detail);
        if (already) return false;
        _store.Events.Insert(0, new AuditRow
        {
            Id = Guid.NewGuid().ToString("N"),
            At = syncedAt,
            Kind = "model",
            Actor = "second-check",
            Action = "second-check",
            Institution = seed.Institution,
            CaseId = seed.CaseId,
            Detail = detail,
            Agent = "second-check",
            Model = EngineVersion,
            MlModel = MlModel,
            Verdict = expected,
            ReasonCode = seed.ReasonCode,
            Confidence = Confidence(seed),
        });
        return true;
    }

    private static string ExpectedVerdict(PolicySeed seed)
    {
        var close = seed.PClose ?? 0;
        var rfi = seed.PRfi ?? 0;
        var escalate = seed.PEscalate ?? 0;
        if (close <= 0 && rfi <= 0 && escalate <= 0) return "";
        if (rfi >= close && rfi >= escalate) return "RFI";
        if (escalate >= close && escalate >= rfi) return "ESCALATE";
        return "CLOSE";
    }

    private bool EnsureEscalated(string key, PolicySeed seed, string syncedAt)
    {
        if (seed.Verdict != "ESCALATE") return false;
        if (!_store.Cases.TryGetValue(key, out var state))
        {
            state = new CaseState();
            _store.Cases[key] = state;
        }
        if (state.DecidedVerdict.Length == 0 && state.Status is "New" or "")
        {
            state.Status = "Escalated / MLRO";
            if (state.UpdatedAt.Length == 0) state.UpdatedAt = syncedAt;
            return true;
        }
        return false;
    }

    private bool ReleaseEscalation(string key, PolicySeed seed)
    {
        if (seed.Verdict == "ESCALATE") return false;
        if (!_store.Cases.TryGetValue(key, out var state)) return false;
        if (state.DecidedVerdict.Length == 0 && state.Status == "Escalated / MLRO")
        {
            state.Status = "New";
            return true;
        }
        return false;
    }

    private static string Accept(CaseState state, string recommended)
    {
        if (recommended is not ("CLOSE" or "RFI" or "ESCALATE"))
            throw new ArgumentException("This case has no recommendation to accept.");
        state.DecidedVerdict = recommended;
        state.Status = recommended == "ESCALATE" ? "Escalated / MLRO" : "Decided";
        return $"Accepted the recommendation {recommended}.";
    }

    private static string Override(CaseState state, string? verdict, string? note)
    {
        var chosen = (verdict ?? "").Trim().ToUpperInvariant();
        if (chosen is not ("CLOSE" or "RFI" or "ESCALATE"))
            throw new ArgumentException("Override needs a verdict of CLOSE, RFI or ESCALATE.");
        if (string.IsNullOrWhiteSpace(note) || note.Trim().Length < 8)
            throw new ArgumentException("Override needs a note of at least a few words.");
        state.DecidedVerdict = chosen;
        state.Note = note.Trim();
        state.Status = chosen == "ESCALATE" ? "Escalated / MLRO" : "Decided";
        return $"Overrode the recommendation to {chosen}. {state.Note}";
    }

    private static string Assign(CaseState state, string actor)
    {
        state.Assignee = actor;
        if (state.Status is "New" or "") state.Status = "In review";
        return $"Assigned the case to {actor}.";
    }

    private static string MarkRfi(CaseState state, string recommended)
    {
        var effective = state.DecidedVerdict.Length == 0 ? recommended : state.DecidedVerdict;
        if (effective != "RFI") throw new ArgumentException("RFI can be marked sent only when the working verdict is RFI.");
        state.RfiSent = true;
        if (state.Status is "New" or "") state.Status = "In review";
        return "Marked the request for information as sent.";
    }

    private void Save()
    {
        var temp = _path + ".tmp";
        File.WriteAllText(temp, JsonSerializer.Serialize(_store, Json));
        File.Move(temp, _path, true);
    }

    private static CaseWork ToWork(CaseState state) =>
        new(state.Status.Length == 0 ? "New" : state.Status, state.Assignee, state.RfiSent, state.DecidedVerdict, state.Note, state.UpdatedAt);

    private static double? Confidence(PolicySeed seed)
    {
        var score = seed.Verdict switch
        {
            "CLOSE" => seed.PClose,
            "RFI" => seed.PRfi,
            "ESCALATE" => seed.PEscalate,
            _ => null,
        };
        return score;
    }

    private static string Key(string institution, string caseId) => institution + ":" + caseId;
    private static string Now() => DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture);
    private static string Show(string value) => value.Length == 0 ? "—" : value;

    private sealed class Store
    {
        public Dictionary<string, CaseState> Cases { get; set; } = new();
        public List<AuditRow> Events { get; set; } = [];
        public List<JobRow> Jobs { get; set; } = [];
        public int ReadUpTo { get; set; }
    }

    private sealed class CaseState
    {
        public string Status { get; set; } = "New";
        public string Assignee { get; set; } = "";
        public bool RfiSent { get; set; }
        public string DecidedVerdict { get; set; } = "";
        public string Note { get; set; } = "";
        public string UpdatedAt { get; set; } = "";
    }
}

public sealed record CaseWork(string Status, string Assignee, bool RfiSent, string DecidedVerdict, string Note, string UpdatedAt);

public sealed class AuditRow
{
    public string Id { get; set; } = "";
    public string At { get; set; } = "";
    public string Kind { get; set; } = "";
    public string Actor { get; set; } = "";
    public string Action { get; set; } = "";
    public string Institution { get; set; } = "";
    public string CaseId { get; set; } = "";
    public string Detail { get; set; } = "";
    public string? Agent { get; set; }
    public string? Model { get; set; }
    public string? MlModel { get; set; }
    public double? MlScore { get; set; }
    public string? Llm { get; set; }
    public string? JobId { get; set; }
    public string? Verdict { get; set; }
    public string? ReasonCode { get; set; }
    public string? Reason { get; set; }
    public List<string>? Evidence { get; set; }
    public List<string>? Rules { get; set; }
    public double? Confidence { get; set; }
    public string? Before { get; set; }
    public string? After { get; set; }
    public string? Note { get; set; }
}

public sealed record JobRow(string Id, string Institution, string Mode, string StartedAt, string FinishedAt, string Status, int Cases);

public sealed record RunRequest(string Institution, string? Mode);

public sealed record ActionRequest(string Action, string Actor, string? Verdict, string? Note);

public sealed record PolicySeed(
    string Institution,
    string CaseId,
    string Verdict,
    string ReasonCode,
    string Reason,
    IReadOnlyList<string> Evidence,
    IReadOnlyList<string> Rules,
    double? PClose,
    double? PRfi,
    double? PEscalate);
