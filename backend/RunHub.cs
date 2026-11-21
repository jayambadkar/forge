using System.Globalization;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Forge.Api;

public sealed class RunHub
{
    private int _seq;
    private readonly ConcurrentDictionary<string, RunState> _runs = new();
    private readonly Catalog _catalog;
    private readonly WorkStore _work;

    public RunHub(Catalog catalog, WorkStore work)
    {
        _catalog = catalog;
        _work = work;
    }

    public RunHandle Start(string institution, string mode)
    {
        if (!_catalog.Known(institution)) throw new ArgumentException("Unknown institution.");
        var id = Interlocked.Increment(ref _seq).ToString("0000", CultureInfo.InvariantCulture);
        var state = new RunState(id, institution, mode);
        _runs[id] = state;
        _work.StartJob(id, institution, mode);
        _ = Task.Run(() => Execute(state));
        return new RunHandle(id, institution, mode);
    }

    public async Task Stream(string id, HttpResponse response, CancellationToken cancel)
    {
        if (!_runs.TryGetValue(id, out var state))
        {
            response.StatusCode = StatusCodes.Status404NotFound;
            return;
        }
        response.Headers.ContentType = "text/event-stream";
        response.Headers.CacheControl = "no-cache";
        response.Headers.Append("X-Accel-Buffering", "no");
        var seen = 0;
        while (!cancel.IsCancellationRequested)
        {
            var (batch, done) = state.TakeFrom(seen);
            foreach (var evt in batch)
            {
                await response.WriteAsync($"data: {evt.ToJsonString()}\n\n", cancel);
                await response.Body.FlushAsync(cancel);
            }
            seen += batch.Length;
            if (done && seen >= state.Count) break;
            await state.Wait(seen, cancel);
        }
    }

    private async Task Execute(RunState state)
    {
        try
        {
            var folder = _catalog.Folder(state.Institution);
            var output = _catalog.OutputPath(state.Institution);
            Directory.CreateDirectory(Path.GetDirectoryName(output)!);
            if (state.Mode == "run")
            {
                var clock = Stopwatch.StartNew();
                state.Add(Event("status", $"system/run {folder}"));
                var info = new ProcessStartInfo
                {
                    FileName = "python3",
                    WorkingDirectory = _catalog.Root,
                    RedirectStandardError = true,
                    RedirectStandardOutput = true,
                    UseShellExecute = false,
                };
                info.ArgumentList.Add(Path.Combine(_catalog.Root, "system", "run"));
                info.ArgumentList.Add(folder);
                info.ArgumentList.Add(output);
                using var process = new Process { StartInfo = info, EnableRaisingEvents = true };
                process.ErrorDataReceived += (_, args) =>
                {
                    if (!string.IsNullOrWhiteSpace(args.Data)) state.Add(Event("log", args.Data));
                };
                process.Start();
                process.BeginErrorReadLine();
                await process.WaitForExitAsync();
                clock.Stop();
                state.Add(Event("status", $"Scorer exit {process.ExitCode} in {clock.ElapsedMilliseconds} ms. Streaming the decisions."));
            }
            else
            {
                state.Add(Event("status", $"Replaying {output}"));
            }

            if (!File.Exists(output))
            {
                state.Add(Event("status", "No output file was written."));
            }
            else
            {
                foreach (var line in File.ReadLines(output))
                {
                    if (string.IsNullOrWhiteSpace(line)) continue;
                    if (JsonNode.Parse(line) is not JsonObject row) continue;
                    state.Add(new JsonObject
                    {
                        ["kind"] = "case",
                        ["caseId"] = Catalog.Str(row, "case_id"),
                        ["verdict"] = Catalog.Str(row, "verdict"),
                        ["reasonCode"] = Catalog.Str(row, "reason_code"),
                        ["reason"] = Catalog.Str(row, "reason"),
                    });
                    await Task.Delay(18);
                }
            }
            state.Add(Event("done", state.Mode == "run" ? "Batch run complete." : "Replay complete."));
            if (state.Mode == "run")
            {
                _catalog.Reload(state.Institution);
                _work.SyncPolicy(_catalog.Seeds().Where(seed => seed.Institution == state.Institution), _catalog.SyncedAt);
            }
            _work.FinishJob(state.Id, "Complete", state.Cases, state.Institution);
        }
        catch (Exception ex)
        {
            state.Add(Event("error", ex.Message));
            state.Add(Event("done", "Stopped."));
            _work.FinishJob(state.Id, "Failed", state.Cases, state.Institution);
        }
        finally
        {
            state.Finish();
        }
    }

    private static JsonObject Event(string kind, string text) => new()
    {
        ["kind"] = kind,
        ["text"] = text,
    };
}

public sealed record RunHandle(string Id, string Institution, string Mode);

public sealed class RunState
{
    private readonly object _gate = new();
    private readonly List<JsonObject> _events = new();
    private readonly List<TaskCompletionSource> _waiters = new();
    public string Id { get; }
    public string Institution { get; }
    public string Mode { get; }
    public bool Done { get; private set; }
    public int Cases { get; private set; }
    public int Count { get { lock (_gate) return _events.Count; } }

    public RunState(string id, string institution, string mode)
    {
        Id = id;
        Institution = institution;
        Mode = mode;
    }

    public void Add(JsonObject evt)
    {
        lock (_gate)
        {
            _events.Add(evt);
            if (Catalog.Str(evt, "kind") == "case") Cases++;
            Release();
        }
    }

    public void Finish()
    {
        lock (_gate)
        {
            Done = true;
            Release();
        }
    }

    public (JsonObject[] Batch, bool Done) TakeFrom(int seen)
    {
        lock (_gate)
        {
            return (_events.Skip(seen).ToArray(), Done);
        }
    }

    public async Task Wait(int seen, CancellationToken cancel)
    {
        Task task;
        lock (_gate)
        {
            if (_events.Count > seen || Done) return;
            var source = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
            _waiters.Add(source);
            task = source.Task;
        }
        await task.WaitAsync(cancel);
    }

    private void Release()
    {
        foreach (var waiter in _waiters) waiter.TrySetResult();
        _waiters.Clear();
    }
}
