import { useEffect, useState } from "react";

type Summary = {
  expected_cost: number;
  wrongful_close_rate: number;
  macro_f1?: number;
  per_class_f1?: Record<string, number>;
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
        Customers are kept together. The check is 5-fold, grouped by customer, with an inner pass
        for the tree settings and one fifth of customers held out and scored once. A wrong close
        costs ten. Missing a close costs three. Mixing up an ask and an escalation costs two.
        Leaving one firm out, and scoring the model on that firm alone, is much worse than scoring a
        customer the model has not seen at a firm it has seen. The score is not loaded by{" "}
        <span className="nums">system/run</span>.
      </p>
      {report?.review ? (
        <ReviewProse review={report.review} calibration={report.calibration?.note} />
      ) : null}
      {report?.desk_model?.used && report.leave_one_institution_out ? (
        <UnseenFirm desk={report.desk_model} previous={report.leave_one_institution_out} />
      ) : null}
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

function ReviewProse({ review, calibration }: { review: Review; calibration?: string }) {
  const model = review.models;
  const firm = review.leave_one_institution_out;
  return (
    <>
      <p>
        There are {review.raw_features} raw facts. The smaller model keeps {review.model_features}{" "}
        of them and drops the customer, history and list groups. Out of fold, gradient boosting
        costs {band(model.lightgbm)}, XGBoost {band(model.xgboost)}, extra trees{" "}
        {band(model.extra_trees)}, and logistic regression {band(model.logistic)}. A stack of the
        tree models costs {band(model.stack)}
        {model.stack?.better_than_best_single
          ? ", which is better than the best single model."
          : ", which is not better once the spread of the folds is taken into account."}{" "}
        The smaller boosted model costs {band(model.lightgbm_ablated)}.
        {review.preferred === "two_stage" ? (
          <>
            {" "}
            The desk uses a two-stage model on {review.desk_features} facts that read the same at
            every firm. It costs {band(model.two_stage)}.
          </>
        ) : (
          " That is the one the desk uses."
        )}
      </p>
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
      <table>
        <thead>
          <tr>
            <th>Firm left out</th>
            <th>Cost before</th>
            <th>Cost now</th>
            <th>Wrong closes before</th>
            <th>Wrong closes now</th>
            <th>Macro F1 before</th>
            <th>Macro F1 now</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(desk.leave_one_institution_out).map(([firm, block]) => (
            <tr key={firm}>
              <td>{FIRMS[firm] ?? firm}</td>
              <td className="nums">{previous[firm]?.expected_cost.toFixed(2) ?? "—"}</td>
              <td className="nums">{block.expected_cost.toFixed(2)}</td>
              <td className="nums">{percent(previous[firm]?.wrongful_close_rate)}</td>
              <td className="nums">{percent(block.wrongful_close_rate)}</td>
              <td className="nums">{previous[firm]?.macro_f1?.toFixed(3) ?? "—"}</td>
              <td className="nums">{block.macro_f1?.toFixed(3) ?? "—"}</td>
            </tr>
          ))}
          <tr>
            <td>All four</td>
            <td className="nums">{before.expected_cost.toFixed(2)}</td>
            <td className="nums">{all.expected_cost.toFixed(2)}</td>
            <td className="nums">{percent(before.wrongful_close_rate)}</td>
            <td className="nums">{percent(all.wrongful_close_rate)}</td>
            <td className="nums">{before.macro_f1?.toFixed(3) ?? "—"}</td>
            <td className="nums">{all.macro_f1?.toFixed(3) ?? "—"}</td>
          </tr>
        </tbody>
      </table>
      <h2>F1 by verdict</h2>
      <table>
        <thead>
          <tr>
            <th>Scored on</th>
            <th>Close</th>
            <th>Ask</th>
            <th>Escalate</th>
            <th>Macro</th>
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
              <td className="nums">{block.per_class_f1?.CLOSE?.toFixed(3) ?? "—"}</td>
              <td className="nums">{block.per_class_f1?.RFI?.toFixed(3) ?? "—"}</td>
              <td className="nums">{block.per_class_f1?.ESCALATE?.toFixed(3) ?? "—"}</td>
              <td className="nums">{block.macro_f1?.toFixed(3) ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function percent(rate: number | undefined) {
  return rate === undefined ? "—" : `${(rate * 100).toFixed(1)}%`;
}

function band(stat: FoldStat | undefined) {
  if (!stat) return "—";
  return `${stat.cost_mean.toFixed(3)} plus or minus ${stat.cost_std.toFixed(3)}`;
}

function plainName(name: string) {
  return name.replaceAll("_", " ");
}
