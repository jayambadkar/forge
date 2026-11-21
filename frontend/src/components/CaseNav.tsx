import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { fetchCases } from "../api";
import { labelFor } from "../format";

type Ref = { institution: string; caseId: string };

function queueParams(institution: string) {
  let saved: string;
  try {
    saved = sessionStorage.getItem("forge.queue") ?? "";
  } catch {
    saved = "";
  }
  const params = new URLSearchParams(saved);
  if (!saved) params.set("institution", institution);
  return params;
}

export function CaseNav({ institution, caseId }: Ref) {
  const navigate = useNavigate();
  const [list, setList] = useState<Ref[]>([]);
  const [scope, setScope] = useState("");

  useEffect(() => {
    const params = queueParams(institution);
    const query: Record<string, string> = {};
    params.forEach((value, key) => {
      query[key] = value;
    });
    fetchCases({ ...query, sort: query.sort || "sla", limit: 5000 })
      .then((page) => {
        setList(page.cases.map((row) => ({ institution: row.institution, caseId: row.caseId })));
        const firm = params.get("institution");
        const filtered = Object.keys(query).some((key) => key !== "institution" && key !== "sort");
        setScope(`${firm ? labelFor(firm) : "All firms"}${filtered ? ", filtered" : ""}`);
      })
      .catch(() => setList([]));
  }, [institution]);

  const index = list.findIndex((row) => row.caseId === caseId && row.institution === institution);
  const prev = index > 0 ? list[index - 1] : null;
  const next = index >= 0 && index < list.length - 1 ? list[index + 1] : null;

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const tag = (event.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      const target = event.key === "j" ? next : event.key === "k" ? prev : null;
      if (target) {
        event.preventDefault();
        void navigate(`/cases/${target.institution}/${target.caseId}`);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [next, prev, navigate]);

  if (index < 0) return null;
  return (
    <nav className="case-nav" aria-label="Move between cases">
      {prev ? (
        <Link to={`/cases/${prev.institution}/${prev.caseId}`} className="button-link">
          ← Previous
        </Link>
      ) : (
        <span className="button-link disabled">← Previous</span>
      )}
      <span className="case-pos">
        Case {(index + 1).toLocaleString("en-GB")} of {list.length.toLocaleString("en-GB")} ·{" "}
        {scope} · <kbd>k</kbd> / <kbd>j</kbd>
      </span>
      {next ? (
        <Link to={`/cases/${next.institution}/${next.caseId}`} className="button-link">
          Next →
        </Link>
      ) : (
        <span className="button-link disabled">Next →</span>
      )}
    </nav>
  );
}
