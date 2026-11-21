import { exportHref } from "../api";

export function ExportMenu({
  params,
  audit = true,
}: {
  params: Record<string, string>;
  audit?: boolean;
}) {
  return (
    <details className="menu">
      <summary>Export</summary>
      <div>
        <a href={exportHref("decisions", "jsonl", params)}>Decisions, JSONL</a>
        <a href={exportHref("decisions", "csv", params)}>Decisions, CSV</a>
        {audit ? <a href={exportHref("audit", "jsonl", params)}>Audit log, JSONL</a> : null}
        {audit ? <a href={exportHref("audit", "csv", params)}>Audit log, CSV</a> : null}
      </div>
    </details>
  );
}
