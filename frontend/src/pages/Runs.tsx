import { useEffect, useState } from "react";
import { fetchJobs, startRun } from "../api";
import { VerdictPill } from "../components/Verdict";
import { labelFor, when } from "../format";
import type { Job, RunEvent, Verdict } from "../types";

type Arrived = { caseId: string; verdict: Verdict; reasonCode: string; reason: string };

export function Runs() {
  const [institution, setInstitution] = useState("bank");
  const [running, setRunning] = useState(false);
  const [log, setLog] = useState<string[]>([]);
  const [arrived, setArrived] = useState<Arrived[]>([]);
  const [counts, setCounts] = useState({ CLOSE: 0, RFI: 0, ESCALATE: 0 });
  const [error, setError] = useState("");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobId, setJobId] = useState("");

  function refresh() {
    fetchJobs()
      .then(setJobs)
      .catch(() => undefined);
  }

  useEffect(() => {
    refresh();
  }, []);

  async function go(mode: "run" | "replay") {
    setRunning(true);
    setError("");
    setLog([]);
    setArrived([]);
    setCounts({ CLOSE: 0, RFI: 0, ESCALATE: 0 });
    try {
      const handle = await startRun(institution, mode);
      setJobId(handle.id);
      const source = new EventSource(`/api/runs/${handle.id}/events`);
      source.onmessage = (message) => {
        const event = JSON.parse(String(message.data)) as RunEvent;
        if (event.kind === "status" || event.kind === "log" || event.kind === "error") {
          setLog((current) => [...current, event.text ?? event.kind].slice(-8));
        }
        if (event.kind === "case" && event.caseId && event.verdict) {
          const verdict = event.verdict;
          const caseId = event.caseId;
          setArrived((current) =>
            [
              { caseId, verdict, reasonCode: event.reasonCode ?? "", reason: event.reason ?? "" },
              ...current,
            ].slice(0, 6),
          );
          if (verdict === "CLOSE" || verdict === "RFI" || verdict === "ESCALATE") {
            setCounts((current) => ({ ...current, [verdict]: current[verdict] + 1 }));
          }
        }
        if (event.kind === "done" || event.kind === "error") {
          source.close();
          setRunning(false);
          refresh();
        }
      };
      source.onerror = () => {
        source.close();
        setRunning(false);
        refresh();
      };
    } catch (err) {
      setRunning(false);
      setError(err instanceof Error ? err.message : "The batch failed");
    }
  }

  const seen = counts.CLOSE + counts.RFI + counts.ESCALATE;

  return (
    <>
      <p className="crumbs">Forge / Runs</p>
      <h1>Batch runs</h1>
      <p className="lede">
        Score one firm, or replay the decisions already on file. Jobs stay in the history below.
      </p>
      {error ? (
        <div className="banner escalate" role="alert">
          {error}
        </div>
      ) : null}
      <div className="toolbar">
        <select
          aria-label="Institution"
          value={institution}
          onChange={(event) => setInstitution(event.target.value)}
        >
          {["bank", "emoney", "investment", "payments_fx"].map((id) => (
            <option key={id} value={id}>
              {labelFor(id)}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="primary"
          disabled={running}
          onClick={() => {
            void go("run");
          }}
        >
          {running ? "Running" : "Start batch run"}
        </button>
        <button
          type="button"
          disabled={running}
          onClick={() => {
            void go("replay");
          }}
        >
          Replay stored output
        </button>
      </div>
      <div className="bar" aria-hidden="true" style={{ marginBottom: 15 }}>
        <span
          style={{ width: `${Math.min(100, (seen / 1000) * 100)}%`, background: "var(--blue)" }}
        />
      </div>
      <div className="stat-grid">
        {(["CLOSE", "RFI", "ESCALATE"] as const).map((verdict) => (
          <article className="stat" key={verdict}>
            <p className="caption">
              {verdict === "CLOSE" ? "Close" : verdict === "RFI" ? "RFI" : "Escalate"}
            </p>
            <strong>{counts[verdict].toLocaleString("en-GB")}</strong>
          </article>
        ))}
        <article className="stat">
          <p className="caption">Job</p>
          <strong className="nums">{jobId || "—"}</strong>
        </article>
      </div>
      <div className="cards">
        {arrived.map((item) => (
          <article className={`case-card ${item.verdict.toLowerCase()}`} key={item.caseId}>
            <div className="card-top">
              <h2 className="nums">
                {item.caseId} <VerdictPill verdict={item.verdict} />
              </h2>
            </div>
            <p className="reason-line">
              {(item.reason || item.reasonCode).split(/(?<=[.!?])\s/)[0]}
            </p>
            <span className="code-tag">{item.reasonCode}</span>
          </article>
        ))}
      </div>
      {log.length ? (
        <section className="panel">
          <h2>Job log</h2>
          <ul>
            {log.map((line, index) => (
              <li key={`${index}-${line}`}>{line}</li>
            ))}
          </ul>
        </section>
      ) : null}
      <h2>History</h2>
      {jobs.length === 0 ? (
        <p>No batch jobs yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Job</th>
              <th>Firm</th>
              <th>Mode</th>
              <th>Started</th>
              <th>Finished</th>
              <th>Status</th>
              <th>Cases</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.id}>
                <td className="nums">{job.id}</td>
                <td>{labelFor(job.institution)}</td>
                <td>{job.mode}</td>
                <td>{when(job.startedAt)}</td>
                <td>{job.finishedAt ? when(job.finishedAt) : "—"}</td>
                <td>{job.status}</td>
                <td className="nums">{job.cases.toLocaleString("en-GB")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
