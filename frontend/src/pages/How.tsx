import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ModelDiagram } from "../components/ModelDiagram";

type Summary = {
  expected_cost: number;
  wrongful_close_rate: number;
  macro_f1?: number;
  per_class_f1?: Record<string, number>;
  confusion?: { labels: string[]; counts: number[][] };
  n?: number;
  gap?: { mean_train_expected_cost: number; mean_validation_expected_cost: number };
};

type FoldStat = { cost_mean: number; cost_std: number; agreement_mean?: number };

type Review = {
  raw_features: number;
  model_features: number;
  desk_features?: number;
  dropped_groups: string[];
  folds: string;
  models: Record<string, FoldStat & { better_than_best_single?: boolean }>;
  preferred: string;
  held_out: { expected_cost: number; agreement: number; wrongful_closes: number };
  leave_one_institution_out: Record<string, number>;
  reason_code: { agreement_mean: number; agreement_std: number };
  label_noise: { flip_5: number; flip_10: number };
  calibration_note?: string;
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
  calibration?: {
    used?: string;
    note?: string;
    isotonic_expected_cost?: number;
    raw_expected_cost?: number;
  };
  review?: Review;
  link_features?: {
    kept: boolean;
    expected_cost_without: number;
    expected_cost_with: number;
    note: string;
  };
  outer_folds?: number;
  leave_one_institution_out?: Record<string, Summary>;
  desk_model?: DeskModel;
};

type DeskModel = {
  used: boolean;
  features: number;
  cases_it_cannot_close: number;
  policy_closes_without_document: number;
  out_of_fold: Summary;
  leave_one_institution_out: Record<string, Summary>;
  unseen_firm_all: Summary;
  unseen_firm_all_previous: Summary;
  test_once: Summary;
};

const FIRMS: Record<string, string> = {
  bank: "Bank",
  emoney: "E-money",
  investment: "Investment",
  payments_fx: "Payments & FX",
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

  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "model" ? "model" : "overview";

  function choose(next: "overview" | "model") {
    const nextParams = new URLSearchParams(params);
    if (next === "model") nextParams.set("tab", "model");
    else nextParams.delete("tab");
    setParams(nextParams, { replace: true });
  }

  return (
    <div className="overview how">
      <p className="crumbs">Forge / How it works</p>
      <h1>How Forge works</h1>
      <div className="how-tabs" role="tablist" aria-label="How it works">
        <button
          type="button"
          role="tab"
          id="how-tab-overview"
          aria-selected={tab === "overview"}
          aria-controls="how-panel"
          onClick={() => choose("overview")}
        >
          Overview
        </button>
        <button
          type="button"
          role="tab"
          id="how-tab-model"
          aria-selected={tab === "model"}
          aria-controls="how-panel"
          onClick={() => choose("model")}
        >
          Model and accuracy
        </button>
      </div>
      <div id="how-panel" role="tabpanel" aria-labelledby={`how-tab-${tab}`}>
        {tab === "overview" ? <Overview /> : <ModelTab report={report} />}
      </div>
    </div>
  );
}

function Overview() {
  return (
    <>
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
    </>
  );
}

function ModelTab({ report }: { report: Report | null }) {
  const desk = report?.desk_model;
  return (
    <>
      <p className="lede">
        The policy engine writes every recommendation. A separate model is trained to reproduce it
        and runs on the desk as a cross-check.
      </p>
      <ModelDiagram />

      <h2>What the figures mean</h2>
      <p>
        The labels are the policy engine’s own verdicts. There is no hidden answer key. The figures
        below measure how faithfully a model can reproduce the written rules, and how well that
        carries over to a firm it has not seen. They do not say whether the rules are right.
      </p>
      <p>
        Validation is 5-fold StratifiedGroupKFold, grouped by customer, so one customer’s cases
        never sit on both sides of a split. Tree settings are tuned inside each training fold only.
        Before any of that, 20% of customers are set aside and scored once at the end.
      </p>
      <p>
        To test a firm the model has not seen, it is trained on three firms and scored on the
        fourth, in turn. The four results are pooled. This is the hardest of the three checks.
      </p>
      <p>
        Errors are weighted by a scoring matrix. A wrong close costs 10, a missed close costs 3, and
        swapping a request for information with an escalation costs 2. Expected cost is the average
        per case.
      </p>

      {desk?.used ? (
        <>
          <h2>Headline figures</h2>
          <div className="kpis">
            <Tile label="Known firms, out of fold" block={desk.out_of_fold} />
            <Tile label="Held-out customers" block={desk.test_once} />
            <Tile label="A firm not seen in training" block={desk.unseen_firm_all} />
            <article className="kpi escalate">
              <p className="kpi-label">Wrong closes, unseen firm</p>
              <p className="kpi-value nums">{percent(desk.unseen_firm_all.wrongful_close_rate)}</p>
              <p className="kpi-note">
                Was {percent(desk.unseen_firm_all_previous.wrongful_close_rate)} with the previous
                model
              </p>
            </article>
          </div>
          {desk.unseen_firm_all.confusion ? (
            <Confusion confusion={desk.unseen_firm_all.confusion} />
          ) : null}
        </>
      ) : null}

      {report?.review ? <ModelTable review={report.review} /> : null}

      {report?.review ? (
        <ReviewProse review={report.review} calibration={report.calibration?.note} />
      ) : null}
      {report?.desk_model?.used && report.leave_one_institution_out ? (
        <UnseenFirm desk={report.desk_model} previous={report.leave_one_institution_out} />
      ) : null}
      {report ? (
        <>
          <p>{report.why}</p>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Check</th>
                  <th className="num">Cost</th>
                  <th className="num">On the training customers</th>
                  <th className="num">On the held-aside fold</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(report.comparison_on_train_oof).map(([name, block]) => (
                  <tr key={name}>
                    <td>{plainName(name)}</td>
                    <td className="num nums">{block.expected_cost.toFixed(3)}</td>
                    <td className="num nums">
                      {block.gap ? block.gap.mean_train_expected_cost.toFixed(3) : "—"}
                    </td>
                    <td className="num nums">
                      {block.gap ? block.gap.mean_validation_expected_cost.toFixed(3) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Group</th>
                  <th className="num">Cost increase when removed</th>
                  <th>Kept</th>
                </tr>
              </thead>
              <tbody>
                {report.group_ablation.map((item) => (
                  <tr key={item.group}>
                    <td>{item.group.replaceAll("_", " ")}</td>
                    <td className="num nums">{item.validation_cost_increase.toFixed(3)}</td>
                    <td>{item.earns_place ? "Yes" : "No"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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

function accuracy(block: Summary) {
  const counts = block.confusion?.counts;
  if (!counts) return undefined;
  const total = counts.flat().reduce((sum, value) => sum + value, 0);
  return total ? counts.reduce((sum, row, index) => sum + (row[index] ?? 0), 0) / total : undefined;
}

function Tile({ label, block }: { label: string; block: Summary }) {
  return (
    <article className="kpi">
      <p className="kpi-label">{label}</p>
      <p className="kpi-value nums">{percent(accuracy(block))}</p>
      <p className="kpi-note">
        Accuracy. Macro-F1 {block.macro_f1?.toFixed(3) ?? "—"}
        {block.n ? `, ${block.n.toLocaleString("en-GB")} cases` : ""}
      </p>
    </article>
  );
}

const VERDICTS: Record<string, string> = {
  CLOSE: "Close",
  RFI: "Request information",
  ESCALATE: "Escalate",
};

function Confusion({ confusion }: { confusion: { labels: string[]; counts: number[][] } }) {
  return (
    <>
      <h2>Unseen firm: policy verdict against model</h2>
      <p>
        Each row is the policy engine’s verdict. Each column is what the model chose. Shading shows
        the share of the row.
      </p>
      <div className="table-wrap">
        <table className="data-table confusion">
          <thead>
            <tr>
              <th scope="col">Policy verdict</th>
              {confusion.labels.map((label) => (
                <th key={label} scope="col" className="num">
                  Model: {VERDICTS[label] ?? label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {confusion.counts.map((row, rowIndex) => {
              const total = row.reduce((sum, value) => sum + value, 0) || 1;
              const label = confusion.labels[rowIndex] ?? "";
              return (
                <tr key={label}>
                  <th scope="row">{VERDICTS[label] ?? label}</th>
                  {row.map((value, colIndex) => {
                    const share = value / total;
                    return (
                      <td
                        key={confusion.labels[colIndex]}
                        className={`num nums${rowIndex === colIndex ? " hit" : ""}`}
                        style={{ background: `rgba(29, 112, 184, ${(share * 0.55).toFixed(3)})` }}
                      >
                        {value.toLocaleString("en-GB")}
                        <span className="share">{(share * 100).toFixed(1)}%</span>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}

const MODEL_NAMES: Record<string, string> = {
  lightgbm: "Gradient boosting",
  lightgbm_ablated: "Gradient boosting, fewer facts",
  two_stage: "Two-stage gradient boosting",
  xgboost: "XGBoost",
  extra_trees: "Extra trees",
  stack: "Stack of tree models",
  logistic: "Logistic regression",
};

function ModelTable({ review }: { review: Review }) {
  return (
    <>
      <h2>Models compared</h2>
      <p>Expected cost on known firms, mean and spread across the 5 folds. Lower is better.</p>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Model</th>
              <th className="num">Cost</th>
              <th className="num">Agreement</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(review.models).map(([name, stat]) => (
              <tr key={name} className={name === review.preferred ? "in-use" : undefined}>
                <td>{MODEL_NAMES[name] ?? plainName(name)}</td>
                <td className="num nums">
                  {stat.cost_mean.toFixed(3)} ± {stat.cost_std.toFixed(3)}
                </td>
                <td className="num nums">{percent(stat.agreement_mean)}</td>
                <td>{name === review.preferred ? <strong>In use</strong> : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {review.preferred === "two_stage" ? (
        <p>
          The two-stage model reads only the {review.desk_features} facts that mean the same at
          every firm. That matters most on a firm it has not seen, which is why it is the one in
          use.
        </p>
      ) : null}
    </>
  );
}

function ReviewProse({ review, calibration }: { review: Review; calibration?: string }) {
  const firm = review.leave_one_institution_out;
  return (
    <>
      <p>
        On the held-out customers the cost is {review.held_out.expected_cost.toFixed(3)}, agreement
        is {(review.held_out.agreement * 100).toFixed(1)}%, and wrongful closes are{" "}
        {review.held_out.wrongful_closes}. Leaving one firm out costs {firm.bank?.toFixed(2)} for
        the bank, {firm.emoney?.toFixed(2)} for e-money, {firm.investment?.toFixed(2)} for the
        investment firm, and {firm.payments_fx?.toFixed(2)} for payments.{" "}
        {calibration ?? "Raw probabilities are used."} A separate check of the reason code agrees{" "}
        {(review.reason_code.agreement_mean * 100).toFixed(1)}% of the time, with a spread of{" "}
        {(review.reason_code.agreement_std * 100).toFixed(1)} points. Flipping 5% of the labels
        raises the cost to {review.label_noise.flip_5.toFixed(3)}. Flipping 10% raises it to{" "}
        {review.label_noise.flip_10.toFixed(3)}.
      </p>
    </>
  );
}

function UnseenFirm({ desk, previous }: { desk: DeskModel; previous: Record<string, Summary> }) {
  const all = desk.unseen_firm_all;
  const before = desk.unseen_firm_all_previous;
  return (
    <>
      <h2>A firm the model has not seen</h2>
      <p>
        The desk model is trained on three firms and scored on the fourth, in turn. It leaves out
        counts and sizes, which move with each firm’s book, and folds every document type into a
        kind such as invoice, statement or takings record. It first decides close or not, then ask
        or escalate. It picks the verdict with the lowest expected cost under the scoring matrix,
        and it may not close a case with no supporting document on file. That blocks a close on{" "}
        {desk.cases_it_cannot_close.toLocaleString("en-GB")} cases, and{" "}
        {desk.policy_closes_without_document === 0
          ? "none of the recommended closes are among them"
          : `${desk.policy_closes_without_document} recommended closes are among them`}
        .
      </p>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Firm left out</th>
              <th className="num">Cost before</th>
              <th className="num">Cost now</th>
              <th className="num">Wrong closes before</th>
              <th className="num">Wrong closes now</th>
              <th className="num">Macro F1 before</th>
              <th className="num">Macro F1 now</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(desk.leave_one_institution_out).map(([firm, block]) => (
              <tr key={firm}>
                <td>{FIRMS[firm] ?? firm}</td>
                <td className="num nums">{previous[firm]?.expected_cost.toFixed(2) ?? "—"}</td>
                <td className="num nums">{block.expected_cost.toFixed(2)}</td>
                <td className="num nums">{percent(previous[firm]?.wrongful_close_rate)}</td>
                <td className="num nums">{percent(block.wrongful_close_rate)}</td>
                <td className="num nums">{previous[firm]?.macro_f1?.toFixed(3) ?? "—"}</td>
                <td className="num nums">{block.macro_f1?.toFixed(3) ?? "—"}</td>
              </tr>
            ))}
            <tr className="total">
              <td>All four</td>
              <td className="num nums">{before.expected_cost.toFixed(2)}</td>
              <td className="num nums">{all.expected_cost.toFixed(2)}</td>
              <td className="num nums">{percent(before.wrongful_close_rate)}</td>
              <td className="num nums">{percent(all.wrongful_close_rate)}</td>
              <td className="num nums">{before.macro_f1?.toFixed(3) ?? "—"}</td>
              <td className="num nums">{all.macro_f1?.toFixed(3) ?? "—"}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <h2>F1 by verdict</h2>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Scored on</th>
              <th className="num">Close</th>
              <th className="num">Request info</th>
              <th className="num">Escalate</th>
              <th className="num">Macro</th>
            </tr>
          </thead>
          <tbody>
            {(
              [
                ["Known firms, out of fold", desk.out_of_fold],
                ["Held-out customers", desk.test_once],
                ["A firm left out", all],
              ] as const
            ).map(([label, block]) => (
              <tr key={label}>
                <td>{label}</td>
                <td className="num nums">{block.per_class_f1?.CLOSE?.toFixed(3) ?? "—"}</td>
                <td className="num nums">{block.per_class_f1?.RFI?.toFixed(3) ?? "—"}</td>
                <td className="num nums">{block.per_class_f1?.ESCALATE?.toFixed(3) ?? "—"}</td>
                <td className="num nums">{block.macro_f1?.toFixed(3) ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function percent(rate: number | undefined) {
  return rate === undefined ? "—" : `${(rate * 100).toFixed(1)}%`;
}

function plainName(name: string) {
  return name.replaceAll("_", " ");
}
