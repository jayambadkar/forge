using System.Globalization;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace Forge.Api;

public sealed class Catalog
{
    private readonly Dictionary<string, InstBook> _books = new();
    private readonly Dictionary<string, RiskDto> _scores = new();
    public string Root { get; }
    public string BookDir { get; }
    public string BookKind { get; }

    public Catalog(string root)
    {
        Root = root;
        var official = Path.Combine(root, "data", "hackathon", "institutions");
        var demo = Path.Combine(root, "fixtures", "demo", "institutions");
        if (File.Exists(Path.Combine(official, "bank", "cases.jsonl")))
        {
            BookDir = official;
            BookKind = "development";
        }
        else
        {
            BookDir = demo;
            BookKind = "fixture";
        }
        var scores = Path.Combine(root, "ml", "scores.jsonl");
        foreach (var row in ReadJsonl(scores))
        {
            var id = Str(row, "case_id");
            if (id.Length == 0) continue;
            var groups = new Dictionary<string, double>();
            if (row["groups"] is JsonObject grouped)
            {
                foreach (var pair in grouped)
                {
                    if (pair.Value is JsonValue value && value.TryGetValue<double>(out var number))
                        groups[pair.Key] = number;
                }
            }
            _scores[id] = new RiskDto(Num(row, "p_close") ?? 0, Num(row, "p_rfi") ?? 0, Num(row, "p_escalate") ?? 0, groups);
        }
    }

    public static readonly string[] Ids = ["bank", "emoney", "investment", "payments_fx"];

    public static string Label(string id) => id switch
    {
        "bank" => "Retail bank",
        "emoney" => "E-money",
        "investment" => "Investment",
        "payments_fx" => "Payments & FX",
        _ => id,
    };

    public bool Known(string id) => Ids.Contains(id) && Directory.Exists(Path.Combine(BookDir, id));

    public IReadOnlyList<InstitutionSummary> Institutions()
    {
        return Ids.Where(Known).Select(id =>
        {
            var book = Load(id);
            var counts = book.Decisions.Values.GroupBy(row => Str(row, "verdict")).ToDictionary(group => group.Key, group => group.Count());
            var reasons = book.Decisions.Values
                .GroupBy(row => Str(row, "reason_code"))
                .Select(group => new ReasonCount(group.Key, group.Count()))
                .OrderByDescending(item => item.Count)
                .ToList();
            return new InstitutionSummary(
                id,
                Label(id),
                BookKind,
                book.Cases.Count,
                counts.GetValueOrDefault("CLOSE"),
                counts.GetValueOrDefault("RFI"),
                counts.GetValueOrDefault("ESCALATE"),
                reasons);
        }).ToList();
    }

    public CasePage Cases(string? institution, string? verdict, string? reason, string? query, int limit, int offset, string? rule, string? risk, string? status, string? sort, Func<string, string, CaseWork>? workOf)
    {
        var rows = new List<CaseSummary>();
        foreach (var id in string.IsNullOrWhiteSpace(institution) ? Ids.Where(Known) : Ids.Where(item => item == institution && Known(item)))
        {
            var book = Load(id);
            foreach (var row in book.Cases)
                rows.Add(Summarise(id, book, row, workOf));
        }
        if (!string.IsNullOrWhiteSpace(verdict))
            rows = rows.Where(item => item.Verdict.Equals(verdict, StringComparison.OrdinalIgnoreCase)).ToList();
        if (!string.IsNullOrWhiteSpace(reason))
            rows = rows.Where(item => item.ReasonCode.Equals(reason, StringComparison.OrdinalIgnoreCase)).ToList();
        if (!string.IsNullOrWhiteSpace(rule))
            rows = rows.Where(item => item.Rules.Split(' ', StringSplitOptions.RemoveEmptyEntries).Contains(rule)).ToList();
        if (!string.IsNullOrWhiteSpace(risk))
            rows = rows.Where(item => item.RiskBand.Equals(risk, StringComparison.OrdinalIgnoreCase)).ToList();
        if (!string.IsNullOrWhiteSpace(status))
            rows = rows.Where(item => item.Status.Equals(status, StringComparison.OrdinalIgnoreCase)).ToList();
        if (!string.IsNullOrWhiteSpace(query))
        {
            var needle = query.Trim();
            rows = rows.Where(item =>
                item.CaseId.Contains(needle, StringComparison.OrdinalIgnoreCase)
                || item.CustomerName.Contains(needle, StringComparison.OrdinalIgnoreCase)
                || item.ReasonCode.Contains(needle, StringComparison.OrdinalIgnoreCase)
                || item.Reason.Contains(needle, StringComparison.OrdinalIgnoreCase)).ToList();
        }
        rows = (sort ?? "opened") switch
        {
            "amount" => rows.OrderByDescending(item => item.Amount ?? 0).ToList(),
            "risk" => rows.OrderByDescending(item => item.PEscalate).ToList(),
            "sla" => rows.OrderByDescending(item => item.SlaDays).ToList(),
            "customer" => rows.OrderBy(item => item.CustomerName).ToList(),
            _ => rows.OrderByDescending(item => item.OpenedAt).ToList(),
        };
        return new CasePage(rows.Count, rows.Skip(offset).Take(limit).ToList());
    }

    public DashboardDto Dashboard(Func<string, string, CaseWork>? workOf)
    {
        var rows = Cases(null, null, null, null, 5000, 0, null, null, null, "opened", workOf).Cases;
        var open = rows.Where(item => item.Status is not "Decided").ToList();
        int band(int from, int to) => open.Count(item => item.SlaDays >= from && item.SlaDays <= to);
        return new DashboardDto(
            rows.Count,
            open.Count,
            rows.Count(item => item.Verdict == "CLOSE"),
            rows.Count(item => item.Verdict == "RFI"),
            rows.Count(item => item.Verdict == "ESCALATE"),
            rows.Count(item => item.Status == "Decided"),
            rows.Count(item => item.Status == "In review"),
            rows.Count(item => item.Status == "New"),
            rows.Count(item => item.Status == "Escalated / MLRO"),
            open.Count(item => item.SlaDays > 30),
            rows.Count(item => item.Verdict == "CLOSE" && item.PEscalate >= 0.2),
            band(0, 30),
            band(31, 60),
            band(61, 90),
            open.Count(item => item.SlaDays > 90),
            SyncedAt);
    }

    public string SyncedAt
    {
        get
        {
            var latest = DateTime.MinValue;
            foreach (var id in Ids.Where(Known))
            {
                var path = OutputPath(id);
                if (File.Exists(path))
                {
                    var stamp = File.GetLastWriteTimeUtc(path);
                    if (stamp > latest) latest = stamp;
                }
            }
            if (latest == DateTime.MinValue) latest = DateTime.UtcNow;
            return latest.ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture);
        }
    }

    public List<PolicySeed> Seeds()
    {
        var seeds = new List<PolicySeed>();
        foreach (var id in Ids.Where(Known))
        {
            var book = Load(id);
            foreach (var row in book.Cases)
            {
                var caseId = Str(row, "case_id", "id");
                book.Decisions.TryGetValue(caseId, out var decision);
                var rules = new List<string>();
                foreach (var alertId in Strings(row, "alert_ids"))
                {
                    if (book.Alerts.TryGetValue(alertId, out var alert))
                    {
                        var rule = Str(alert, "rule_id");
                        if (rule.Length > 0 && !rules.Contains(rule)) rules.Add(rule);
                    }
                }
                _scores.TryGetValue(caseId, out var risk);
                seeds.Add(new PolicySeed(
                    id,
                    caseId,
                    decision is null ? "" : Str(decision, "verdict"),
                    decision is null ? "" : Str(decision, "reason_code"),
                    decision is null ? "" : Str(decision, "reason"),
                    decision is null ? [] : Strings(decision, "evidence"),
                    rules,
                    risk?.PClose,
                    risk?.PRfi,
                    risk?.PEscalate));
            }
        }
        return seeds;
    }

    public void Reload(string? institution = null)
    {
        lock (_books)
        {
            if (string.IsNullOrWhiteSpace(institution)) _books.Clear();
            else _books.Remove(institution);
        }
        _linkReady = false;
    }

    public (IReadOnlyList<string> Alerts, IReadOnlyList<string> Evidence) Facts(string institution, string caseId)
    {
        if (!Known(institution)) return ([], []);
        var book = Load(institution);
        var row = book.Cases.FirstOrDefault(item => Str(item, "case_id", "id") == caseId);
        var alerts = row is null ? [] : Strings(row, "alert_ids");
        var evidence = book.Decisions.TryGetValue(caseId, out var decision) ? Strings(decision, "evidence") : [];
        return (alerts, evidence);
    }

    public IReadOnlyList<RelatedCase> Related(string institution, string caseId, int limit = 8)
    {
        EnsureLinks();
        var key = institution + ":" + caseId;
        if (!_caseKeys.TryGetValue(key, out var keys)) return [];
        var found = new Dictionary<string, RelatedCase>();
        foreach (var token in keys)
        {
            if (!_linkMap.TryGetValue(token, out var hits)) continue;
            var kind = token.Split(':', 2)[0];
            if (kind == "party" && hits.Count > 25) continue;
            var via = token.Split(':', 2)[1];
            foreach (var hit in hits)
            {
                var other = hit.Institution + ":" + hit.CaseId;
                if (other == key || found.ContainsKey(other)) continue;
                found[other] = new RelatedCase(hit.Institution, hit.CaseId, hit.CustomerName, hit.Verdict, kind, via);
                if (found.Count >= limit) return found.Values.ToList();
            }
        }
        return found.Values.ToList();
    }

    public CaseDetail? Detail(string institution, string caseId, CaseWork? work, IReadOnlyList<AuditRow>? trail)
    {
        if (!Known(institution)) return null;
        var book = Load(institution);
        var row = book.Cases.FirstOrDefault(item => Str(item, "case_id", "id") == caseId);
        if (row is null) return null;
        var folder = Path.Combine(BookDir, institution);
        var customerId = Str(row, "customer_id");
        book.Customers.TryGetValue(customerId, out var customer);
        var declared = customer?["declared"] as JsonObject;
        double? expected = declared is null ? null : Num(declared, "monthly_income_gbp");
        if (expected is null && declared is not null && Num(declared, "annual_turnover_gbp") is double annual && annual > 0)
            expected = Math.Round(annual / 12.0, 2);

        var cited = new HashSet<string>();
        DecisionDto? decision = null;
        if (book.Decisions.TryGetValue(caseId, out var decided))
        {
            foreach (var id in Strings(decided, "evidence")) cited.Add(id);
            decision = new DecisionDto(
                Str(decided, "verdict"),
                Str(decided, "reason_code"),
                Str(decided, "reason"),
                Strings(decided, "evidence"));
        }

        var alerts = new List<AlertDto>();
        var timeline = new List<TxnDto>();
        var seen = new HashSet<string>();
        foreach (var alertId in Strings(row, "alert_ids"))
        {
            if (!book.Alerts.TryGetValue(alertId, out var alert)) continue;
            var txnIds = Strings(alert, "transaction_ids");
            alerts.Add(new AlertDto(alertId, Str(alert, "rule_id"), Str(alert, "rule_name", "typology"), Str(alert, "message", "narrative"), txnIds));
            foreach (var txnId in txnIds)
            {
                if (!book.Transactions.TryGetValue(txnId, out var txn) || !seen.Add(txnId)) continue;
                timeline.Add(ToTxn(txn, true));
            }
        }
        foreach (var txn in book.Transactions.Values)
        {
            if (Str(txn, "customer_id") != customerId) continue;
            var txnId = Str(txn, "transaction_id", "id");
            if (seen.Add(txnId)) timeline.Add(ToTxn(txn, false));
        }
        timeline.Sort((a, b) => string.Compare(a.Timestamp, b.Timestamp, StringComparison.Ordinal));

        var evidence = new List<EvidenceDto>();
        if (book.EvidenceByCustomer.TryGetValue(customerId, out var docs))
        {
            foreach (var doc in docs)
            {
                var id = Str(doc, "doc_id", "evidence_id", "id");
                var text = ReadInside(folder, Str(doc, "file", "path"));
                evidence.Add(new EvidenceDto(id, Str(doc, "title", "name"), Str(doc, "type", "kind"), Str(doc, "dated"), text, cited.Contains(id)));
            }
        }

        var reviews = book.ReviewsByCustomer.GetValueOrDefault(customerId)?
            .Select(item => new ReviewDto(Str(item, "review_id", "id"), Str(item, "reviewed_on", "date"), Str(item, "rule_id"), Str(item, "verdict"), Str(item, "note", "summary", "text")))
            .ToList() ?? [];

        return new CaseDetail(
            caseId,
            institution,
            new CustomerDto(
                customerId,
                customer is null ? "" : Str(customer, "name"),
                customer is null ? "" : Str(customer, "kind"),
                customer is null ? "" : Str(customer, "date_of_birth", "dob"),
                customer is null ? "" : Str(customer, "occupation", "business_activity"),
                customer is null ? "" : Str(customer, "risk_rating"),
                expected),
            Str(row, "opened_at"),
            Str(row, "held_payment_id"),
            alerts,
            timeline,
            evidence,
            reviews,
            decision,
            _scores.GetValueOrDefault(caseId),
            work ?? new CaseWork("New", "", false, "", "", ""),
            trail ?? [],
            Related(institution, caseId));
    }

    private CaseSummary Summarise(string institution, InstBook book, JsonObject row, Func<string, string, CaseWork>? workOf)
    {
        var caseId = Str(row, "case_id", "id");
        var customerId = Str(row, "customer_id");
        book.Customers.TryGetValue(customerId, out var customer);
        book.Decisions.TryGetValue(caseId, out var decision);
        var name = customer is null ? customerId : Str(customer, "name", "full_name");
        var alertIds = Strings(row, "alert_ids");
        double amount = 0;
        var rules = new List<string>();
        foreach (var alertId in alertIds)
        {
            if (!book.Alerts.TryGetValue(alertId, out var alert)) continue;
            var rule = Str(alert, "rule_id");
            if (rule.Length > 0 && !rules.Contains(rule)) rules.Add(rule);
            foreach (var txnId in Strings(alert, "transaction_ids"))
            {
                if (book.Transactions.TryGetValue(txnId, out var txn))
                    amount += Num(txn, "amount_gbp", "amount") ?? 0;
            }
        }
        var work = workOf?.Invoke(institution, caseId) ?? new CaseWork("New", "", false, "", "", "");
        var opened = Str(row, "opened_at");
        _scores.TryGetValue(caseId, out var risk);
        var pClose = risk?.PClose ?? 0;
        var pRfi = risk?.PRfi ?? 0;
        var pEscalate = risk?.PEscalate ?? 0;
        var band = pEscalate >= 0.5 ? "high" : pClose >= 0.7 ? "low" : "review";
        return new CaseSummary(
            caseId, institution, customerId, name,
            decision is null ? "" : Str(decision, "verdict"),
            decision is null ? "" : Str(decision, "reason_code"),
            decision is null ? "" : Str(decision, "reason"),
            amount == 0 ? null : Math.Round(amount, 2),
            alertIds.Count, opened, string.Join(" ", rules),
            Sla(opened), pClose, pRfi, pEscalate, band,
            work.Status, work.Assignee, work.RfiSent, work.DecidedVerdict);
    }

    private static int Sla(string opened)
    {
        if (!DateTime.TryParse(opened, out var when)) return 0;
        var days = (DateTime.UtcNow - when.ToUniversalTime()).TotalDays;
        return days < 0 ? 0 : (int)days;
    }

    private bool _linkReady;
    private readonly Dictionary<string, List<LinkHit>> _linkMap = new();
    private readonly Dictionary<string, List<string>> _caseKeys = new();
    private static readonly Regex DeviceId = new(@"\b[A-Z][0-9]-[0-9]{3,}\b", RegexOptions.Compiled);

    private void EnsureLinks()
    {
        if (_linkReady) return;
        lock (_linkMap)
        {
            if (_linkReady) return;
            _linkMap.Clear();
            _caseKeys.Clear();
            foreach (var id in Ids.Where(Known))
            {
                var book = Load(id);
                var folder = Path.Combine(BookDir, id);
                var listed = new Dictionary<string, string>();
                foreach (var entry in ReadJsonl(Path.Combine(folder, "internal_list.jsonl")))
                {
                    var entryId = Str(entry, "entry_id");
                    var entryName = Norm(Str(entry, "name"));
                    if (entryId.Length > 0 && entryName.Length > 0) listed[entryName] = entryId;
                }
                foreach (var row in book.Cases)
                {
                    var caseId = Str(row, "case_id", "id");
                    var customerId = Str(row, "customer_id");
                    book.Customers.TryGetValue(customerId, out var customer);
                    var name = customer is null ? customerId : Str(customer, "name");
                    var verdict = book.Decisions.TryGetValue(caseId, out var decision) ? Str(decision, "verdict") : "";
                    var keys = new List<string>();
                    void Add(string token)
                    {
                        if (token.Length < 8 || keys.Contains(token)) return;
                        keys.Add(token);
                    }
                    Add("customer:" + customerId);
                    if (customer is not null)
                    {
                        foreach (var account in Strings(customer, "account_ids")) Add("account:" + account);
                        var listedName = Norm(name);
                        if (listed.TryGetValue(listedName, out var entryId)) Add("list:" + entryId + " " + name);
                    }
                    foreach (var alertId in Strings(row, "alert_ids"))
                    {
                        if (!book.Alerts.TryGetValue(alertId, out var alert)) continue;
                        foreach (var txnId in Strings(alert, "transaction_ids"))
                        {
                            if (!book.Transactions.TryGetValue(txnId, out var txn)) continue;
                            var party = Norm(Str(txn, "counterparty_name"));
                            if (party.Length >= 4) Add("party:" + party);
                            var account = Str(txn, "counterparty_account", "account_id");
                            if (account.Length > 0) Add("account:" + account);
                            if (party.Length >= 4 && listed.TryGetValue(party, out var entryId)) Add("list:" + entryId + " " + Str(txn, "counterparty_name"));
                        }
                    }
                    if (book.EvidenceByCustomer.TryGetValue(customerId, out var docs))
                    {
                        foreach (var doc in docs)
                        {
                            if (Str(doc, "type") != "device_export") continue;
                            var text = ReadInside(folder, Str(doc, "file"));
                            foreach (Match match in DeviceId.Matches(text)) Add("device:" + match.Value);
                        }
                    }
                    _caseKeys[id + ":" + caseId] = keys;
                    var hit = new LinkHit(id, caseId, name, verdict);
                    foreach (var token in keys)
                    {
                        if (!_linkMap.TryGetValue(token, out var list))
                        {
                            list = [];
                            _linkMap[token] = list;
                        }
                        list.Add(hit);
                    }
                }
            }
            _linkReady = true;
        }
    }

    private static string Norm(string value)
    {
        var text = value.ToLowerInvariant();
        foreach (var token in new[] { " ltd", " limited", " plc", " llp", " inc", " co" })
            text = text.Replace(token, " ", StringComparison.Ordinal);
        return string.Join(' ', text.Split(' ', StringSplitOptions.RemoveEmptyEntries));
    }

    public string OutputPath(string institution) => Path.Combine(Root, "output", institution + ".jsonl");
    public string Folder(string institution) => Path.Combine(BookDir, institution);

    private InstBook Load(string institution)
    {
        lock (_books)
        {
            if (_books.TryGetValue(institution, out var cached)) return cached;
            var folder = Path.Combine(BookDir, institution);
            var book = new InstBook
            {
                Customers = Index(Path.Combine(folder, "customers.jsonl"), "customer_id", "id"),
                Alerts = Index(Path.Combine(folder, "alerts.jsonl"), "alert_id", "id"),
                Transactions = Index(Path.Combine(folder, "transactions.jsonl"), "transaction_id", "id"),
                Decisions = Index(OutputPath(institution), "case_id"),
                Cases = ReadJsonl(Path.Combine(folder, "cases.jsonl")).ToList(),
            };
            foreach (var row in ReadJsonl(Path.Combine(folder, "evidence.jsonl")))
                book.EvidenceByCustomer.GetOrAdd(Str(row, "customer_id")).Add(row);
            foreach (var row in ReadJsonl(Path.Combine(folder, "previous_reviews.jsonl")))
                book.ReviewsByCustomer.GetOrAdd(Str(row, "customer_id")).Add(row);
            _books[institution] = book;
            return book;
        }
    }

    private static TxnDto ToTxn(JsonObject txn, bool inAlert) => new(
        Str(txn, "transaction_id", "id"),
        Str(txn, "booked_at", "timestamp", "date"),
        Num(txn, "amount_gbp", "amount") ?? 0,
        Str(txn, "currency") is { Length: > 0 } currency ? currency : "GBP",
        Str(txn, "direction"),
        Str(txn, "channel"),
        Str(txn, "counterparty_name", "counterparty"),
        Str(txn, "counterparty_country", "country"),
        Str(txn, "reference"),
        inAlert);

    private static string ReadInside(string root, string relative)
    {
        if (string.IsNullOrWhiteSpace(relative) || relative.Contains("..", StringComparison.Ordinal)) return "";
        var full = Path.GetFullPath(Path.Combine(root, relative));
        var baseFull = Path.GetFullPath(root + Path.DirectorySeparatorChar);
        if (!full.StartsWith(baseFull, StringComparison.Ordinal) || !File.Exists(full)) return "";
        return File.ReadAllText(full);
    }

    private static Dictionary<string, JsonObject> Index(string path, params string[] keys)
    {
        var map = new Dictionary<string, JsonObject>();
        foreach (var row in ReadJsonl(path))
        {
            var id = Str(row, keys);
            if (id.Length > 0) map[id] = row;
        }
        return map;
    }

    private static IEnumerable<JsonObject> ReadJsonl(string path)
    {
        if (!File.Exists(path)) yield break;
        foreach (var line in File.ReadLines(path))
        {
            if (string.IsNullOrWhiteSpace(line)) continue;
            if (JsonNode.Parse(line) is JsonObject obj) yield return obj;
        }
    }

    internal static string Str(JsonObject obj, params string[] keys)
    {
        foreach (var key in keys)
        {
            if (!obj.TryGetPropertyValue(key, out var node) || node is null) continue;
            var text = StringOf(node);
            if (text.Length > 0) return text;
        }
        return "";
    }

    private static string StringOf(JsonNode node)
    {
        if (node is JsonValue value)
        {
            if (value.TryGetValue<string>(out var text) && text is not null) return text;
            if (value.TryGetValue<int>(out var integer)) return integer.ToString(CultureInfo.InvariantCulture);
            if (value.TryGetValue<long>(out var longer)) return longer.ToString(CultureInfo.InvariantCulture);
            if (value.TryGetValue<double>(out var number)) return number.ToString(System.Globalization.CultureInfo.InvariantCulture);
        }
        return "";
    }

    private static List<string> Strings(JsonObject obj, params string[] keys)
    {
        foreach (var key in keys)
        {
            if (!obj.TryGetPropertyValue(key, out var node) || node is null) continue;
            if (node is JsonArray array)
                return array.Select(item => item is null ? "" : StringOf(item)).Where(item => item.Length > 0).ToList();
            var single = StringOf(node);
            if (single.Length > 0) return [single];
        }
        return [];
    }

    private static double? Num(JsonObject obj, params string[] keys)
    {
        foreach (var key in keys)
        {
            if (!obj.TryGetPropertyValue(key, out var node) || node is not JsonValue value) continue;
            if (value.TryGetValue<double>(out var number)) return number;
            if (value.TryGetValue<int>(out var integer)) return integer;
            if (value.TryGetValue<long>(out var longer)) return longer;
        }
        return null;
    }

    private sealed class InstBook
    {
        public Dictionary<string, JsonObject> Customers { get; init; } = new();
        public Dictionary<string, JsonObject> Alerts { get; init; } = new();
        public Dictionary<string, JsonObject> Transactions { get; init; } = new();
        public Dictionary<string, JsonObject> Decisions { get; init; } = new();
        public List<JsonObject> Cases { get; init; } = [];
        public Dictionary<string, List<JsonObject>> EvidenceByCustomer { get; } = new();
        public Dictionary<string, List<JsonObject>> ReviewsByCustomer { get; } = new();
    }
}

file static class DictExt
{
    public static List<T> GetOrAdd<T>(this Dictionary<string, List<T>> map, string key)
    {
        if (!map.TryGetValue(key, out var list))
        {
            list = [];
            map[key] = list;
        }
        return list;
    }
}

public sealed record ReasonCount(string Code, int Count);
public sealed record InstitutionSummary(string Id, string Label, string Book, int Cases, int Close, int Rfi, int Escalate, IReadOnlyList<ReasonCount> Reasons);
public sealed record CaseSummary(string CaseId, string Institution, string CustomerId, string CustomerName, string Verdict, string ReasonCode, string Reason, double? Amount, int AlertCount, string OpenedAt, string Rules, int SlaDays, double PClose, double PRfi, double PEscalate, string RiskBand, string Status, string Assignee, bool RfiSent, string DecidedVerdict);
public sealed record CasePage(int Total, IReadOnlyList<CaseSummary> Cases);
public sealed record DashboardDto(int Cases, int Open, int Close, int Rfi, int Escalate, int Decided, int InReview, int New, int Escalated, int Ageing, int WrongfulCloseRisk, int Sla0, int Sla1, int Sla2, int Sla3, string SyncedAt);
public sealed record RelatedCase(string Institution, string CaseId, string CustomerName, string Verdict, string Link, string Via);
public sealed record LinkHit(string Institution, string CaseId, string CustomerName, string Verdict);
public sealed record CustomerDto(string Id, string Name, string Kind, string Dob, string Occupation, string Risk, double? ExpectedMonthly);
public sealed record AlertDto(string Id, string RuleId, string RuleName, string Message, IReadOnlyList<string> TransactionIds);
public sealed record TxnDto(string Id, string Timestamp, double Amount, string Currency, string Direction, string Channel, string Counterparty, string Country, string Reference, bool InAlert);
public sealed record EvidenceDto(string Id, string Title, string Kind, string Dated, string Text, bool Cited);
public sealed record ReviewDto(string Id, string Date, string RuleId, string Verdict, string Text);
public sealed record DecisionDto(string Verdict, string ReasonCode, string Reason, IReadOnlyList<string> Evidence);
public sealed record RiskDto(double PClose, double PRfi, double PEscalate, IReadOnlyDictionary<string, double> Groups);
public sealed record CaseDetail(
    string CaseId,
    string Institution,
    CustomerDto Customer,
    string OpenedAt,
    string HeldPaymentId,
    IReadOnlyList<AlertDto> Alerts,
    IReadOnlyList<TxnDto> Timeline,
    IReadOnlyList<EvidenceDto> Evidence,
    IReadOnlyList<ReviewDto> Reviews,
    DecisionDto? Decision,
    RiskDto? Risk,
    CaseWork Work,
    IReadOnlyList<AuditRow> Trail,
    IReadOnlyList<RelatedCase> Related);
