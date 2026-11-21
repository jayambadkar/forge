import { useEffect, useState } from "react";

type Summary = {
  expected_cost: number;
  wrongful_close_rate: number;
  gap?: { mean_train_expected_cost: number; mean_validation_expected_cost: number };
};

type Report = {
  why: string;
  inner_winner: string;
  n_cases: number;
  n_atomic_features: number;
  split: { train_n: number; test_n: number; method: string };
  comparison_on_train_oof: Record<string, Summary>;
  group_ablation: { group: string; validation_cost_increase: number; earns_place: boolean }[];
  test_once: Summary & { model: string; policy_expected_cost: number };
  frozen_close_threshold: { threshold: number };
  link_features?: {
    kept: boolean;
    expected_cost_without: number;
    expected_cost_with: number;
    note: string;
  };
  outer_folds?: number;
};

export function How() {
  const [report, setReport] = useState<Report | null>(null);

  useEffect(() => {
    fetch("/api/models")
      .then((response) => (response.ok ? (response.json() as Promise<Report>) : null))
      .then((body) => {
        if (body?.comparison_on_train_oof) setReport(body);
      })
      .catch(() => undefined);
  }, []);

  return (
    <>
      <p className="crumbs">Forge / How it works</p>
      <h1>How Forge works</h1>
      <p className="lede">
        Forge reads one firm’s folder and writes one recommendation per case: close, ask, or
        escalate. That recommendation is what the desk shows and what the submission file contains.
      </p>

      <h2>A case</h2>
      <p>
        A case is every alert for one customer in the review window. Forge closes it only when every
        alert is explained by something on the file: a document that names the party and the amount,
        a statement in the customer’s own name below five times what they declared, a takings sheet
        about their trade, a gift letter, a cancellation, a group chart, or a reverification. If the
        missing piece is a document, Forge asks for that document by name. If the pattern is
        suspicious, including fraud, structuring with no book, an unexplained higher-risk corridor,
        a confirmed list match, or money passed on to a person, Forge escalates and does not ask the
        customer.
      </p>

      <h2>The file</h2>
      <p>
        <span className="nums">system/run</span> takes the institution folder and an output path. It
        does not care which directory you start it from, and it does not call out to the network.
        Two runs of the same folder write the same file. The desk reads that file.
      </p>

      <h2>The audit trail</h2>
      <p>
        Every recommendation and every analyst change is appended. Nothing in the log is edited
        later. A recommendation event records which part of Forge wrote it, the evidence and rules
        it used, and the text of the reason. An analyst event records who acted, the status before
        and after, and the note on an override.
      </p>

      <h2>An optional reviewer</h2>
      <p>
        A language-model reviewer can be switched on with <span className="nums">FORGE_LLM=1</span>.{" "}
        <span className="nums">XAI_API_KEY</span> uses api.x.ai and grok-4.{" "}
        <span className="nums">OPENROUTER_API_KEY</span> uses OpenRouter. If both keys are set,{" "}
        <span className="nums">FORGE_LLM_PROVIDER</span> chooses. With no key, nothing is called and
        the recommendation stands. The reviewer is not allowed to close a case the checks did not
        already close, and <span className="nums">system/run</span> does not call it.
      </p>

      <h2>Checking the recommendation</h2>
      <p>
        The labels used for the check are Forge’s own recommendations, not a hidden answer key.
        Customers are kept together so one person is not split across the check. One fifth of
        customers is held out and looked at once. On the rest, the choice between a tree model, a
        simpler grouped version, and logistic regression is made with 5-fold grouped
        cross-validation. A wrong close is counted as ten times as costly as failing to close a case
        that could have been closed.
      </p>
      {report ? (
        <>
          <p>{report.why}</p>
          <table>
            <thead>
              <tr>
                <th>Check</th>
                <th>Cost</th>
                <th>On the training customers</th>
                <th>On the held-aside fold</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(report.comparison_on_train_oof).map(([name, block]) => (
                <tr key={name}>
                  <td>{plainName(name)}</td>
                  <td className="nums">{block.expected_cost.toFixed(3)}</td>
                  <td className="nums">
                    {block.gap ? block.gap.mean_train_expected_cost.toFixed(3) : "—"}
                  </td>
                  <td className="nums">
                    {block.gap ? block.gap.mean_validation_expected_cost.toFixed(3) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>
            The held-out customers ({report.split.test_n.toLocaleString("en-GB")}) cost{" "}
            {report.test_once.expected_cost.toFixed(3)} for the chosen check, against{" "}
            {report.test_once.policy_expected_cost.toFixed(2)} for the recommendation itself. The
            recommendation is what gets written.
          </p>
          {report.link_features ? (
            <p>
              Counts of linked cases were tried inside the training folds only.{" "}
              {report.link_features.note} Cost without them{" "}
              {report.link_features.expected_cost_without.toFixed(3)}, with them{" "}
              {report.link_features.expected_cost_with.toFixed(3)}.
            </p>
          ) : null}
          <h2>Which groups of facts were useful</h2>
          <table>
            <thead>
              <tr>
                <th>Group</th>
                <th>Cost increase when removed</th>
                <th>Kept</th>
              </tr>
            </thead>
            <tbody>
              {report.group_ablation.map((item) => (
                <tr key={item.group}>
                  <td>{item.group.replaceAll("_", " ")}</td>
                  <td className="nums">{item.validation_cost_increase.toFixed(3)}</td>
                  <td>{item.earns_place ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="meta">
            {report.n_cases.toLocaleString("en-GB")} cases, {report.n_atomic_features} facts,{" "}
            {report.outer_folds ?? 5}-fold check. Chosen on the training customers:{" "}
            {plainName(report.inner_winner)}.
          </p>
        </>
      ) : (
        <p>The check figures are not loaded yet.</p>
      )}
    </>
  );
}

function plainName(name: string) {
  return name.replaceAll("_", " ");
}
