type BoxProps = {
  x: number;
  y: number;
  width: number;
  height: number;
  title: string;
  lines?: string[];
  tone: string;
  fill?: string;
  model?: boolean;
};

function Box({
  x,
  y,
  width,
  height,
  title,
  lines = [],
  tone,
  fill = "var(--white)",
  model = false,
}: BoxProps) {
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        rx={10}
        fill={fill}
        stroke={tone}
        strokeWidth={model ? 2 : 3}
        strokeDasharray={model ? "8 6" : undefined}
      />
      {model ? (
        <g>
          <rect x={x + width - 72} y={y + 10} width={60} height={24} rx={12} fill="var(--light)" />
          <text x={x + width - 42} y={y + 27} textAnchor="middle" className="md-tag">
            model
          </text>
        </g>
      ) : null}
      <text x={x + 16} y={y + 30} className="md-title">
        {title}
      </text>
      {lines.map((line, index) => (
        <text key={line} x={x + 16} y={y + 54 + index * 19} className="md-line">
          {line}
        </text>
      ))}
    </g>
  );
}

function Diamond({
  cx,
  cy,
  hw,
  hh,
  lines,
}: {
  cx: number;
  cy: number;
  hw: number;
  hh: number;
  lines: string[];
}) {
  const top = cy - ((lines.length - 1) * 19) / 2 + 6;
  return (
    <g>
      <path
        d={`M${cx} ${cy - hh} L${cx + hw} ${cy} L${cx} ${cy + hh} L${cx - hw} ${cy} Z`}
        fill="var(--white)"
        stroke="var(--secondary)"
        strokeWidth={2.5}
        strokeLinejoin="round"
      />
      {lines.map((line, index) => (
        <text key={line} x={cx} y={top + index * 19} textAnchor="middle" className="md-title">
          {line}
        </text>
      ))}
    </g>
  );
}

function Arrow({
  d,
  dashed = false,
  head = true,
}: {
  d: string;
  dashed?: boolean;
  head?: boolean;
}) {
  return (
    <path
      d={d}
      fill="none"
      stroke="var(--black)"
      strokeWidth={2}
      strokeDasharray={dashed ? "6 5" : undefined}
      markerEnd={head ? "url(#md-arrow)" : undefined}
    />
  );
}

function Label({
  x,
  y,
  text,
  anchor = "start",
}: {
  x: number;
  y: number;
  text: string;
  anchor?: "start" | "end" | "middle";
}) {
  return (
    <text x={x} y={y} textAnchor={anchor} className="md-branch">
      {text}
    </text>
  );
}

export function ModelDiagram() {
  return (
    <div className="model-diagram">
      <svg
        viewBox="0 0 960 806"
        role="img"
        aria-labelledby="md-heading md-desc"
        xmlns="http://www.w3.org/2000/svg"
      >
        <title id="md-heading">How a case is decided</title>
        <desc id="md-desc">
          A case goes to the policy engine, which follows the written SOP. If there are signs of
          crime the case is escalated to the MLRO. If not, and a named document explains every
          alert, the case is closed; otherwise Forge asks for the missing document. All three
          outcomes go to the submission file, which is scored, and to the analyst desk and audit
          log. A model cross-check flags disagreements on the desk but never changes the verdict. An
          optional language-model reviewer, off by default, can only make a verdict more cautious.
        </desc>
        <defs>
          <marker
            id="md-arrow"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="8"
            markerHeight="8"
            orient="auto-start-reverse"
          >
            <path d="M0 0 L10 5 L0 10 z" fill="var(--black)" />
          </marker>
        </defs>

        <Box
          x={40}
          y={16}
          width={220}
          height={124}
          title="Case"
          lines={["Alerts", "Transactions", "Documents", "Customer profile"]}
          tone="var(--blue)"
        />
        <Arrow d="M260 78 H362" />
        <Box
          x={370}
          y={16}
          width={260}
          height={124}
          title="Policy engine"
          lines={["Rule-based expert system", "Follows the written SOP", "Same case, same answer"]}
          tone="var(--blue)"
        />
        <Arrow d="M700 78 H638" dashed />
        <Box
          x={700}
          y={16}
          width={240}
          height={124}
          title="LLM reviewer"
          lines={[
            "Optional, off by default",
            "grok-4 (x.ai or OpenRouter)",
            "Can only add caution",
          ]}
          tone="var(--secondary)"
          model
        />

        <Arrow d="M500 140 V158" />
        <Diamond cx={500} cy={205} hw={110} hh={45} lines={["Signs of crime?"]} />
        <text x={160} y={236} className="md-note">
          Fraud report on file,
        </text>
        <text x={160} y={255} className="md-note">
          split payments, confirmed
        </text>
        <text x={160} y={274} className="md-note">
          list match
        </text>

        <Arrow d="M390 205 H140 V418" />
        <Label x={372} y={196} text="Yes" anchor="end" />
        <Arrow d="M500 250 V272" />
        <Label x={512} y={268} text="No" />

        <Diamond
          cx={500}
          cy={335}
          hw={150}
          hh={55}
          lines={["A named document", "explains every alert?"]}
        />
        <Arrow d="M650 335 H820 V418" />
        <Label x={668} y={326} text="Yes" />
        <Arrow d="M500 390 V418" />
        <Label x={512} y={410} text="No" />

        <Box
          x={40}
          y={420}
          width={200}
          height={80}
          title="Escalate"
          lines={["to the MLRO"]}
          tone="var(--red)"
          fill="var(--red-tint)"
        />
        <Box
          x={370}
          y={420}
          width={260}
          height={80}
          title="Request information"
          lines={["Ask for the missing document"]}
          tone="var(--orange)"
          fill="var(--orange-tint)"
        />
        <Box
          x={720}
          y={420}
          width={200}
          height={80}
          title="Close"
          lines={["Every alert explained"]}
          tone="var(--green)"
          fill="var(--green-tint)"
        />

        <Arrow d="M140 500 V528 H820 V500" head={false} />
        <Arrow d="M500 500 V528" head={false} />
        <Arrow d="M220 528 V553" />
        <Arrow d="M720 528 V553" />

        <Box
          x={40}
          y={555}
          width={360}
          height={80}
          title="Submission file"
          lines={["From system/run. This is what is scored"]}
          tone="var(--black)"
        />
        <Box
          x={520}
          y={555}
          width={400}
          height={80}
          title="Analyst desk + audit log"
          lines={["Every recommendation and every change"]}
          tone="var(--black)"
        />

        <Arrow d="M720 690 V643" dashed />
        <Label x={708} y={672} text="Flags disagreements, never changes the verdict" anchor="end" />
        <Box
          x={520}
          y={690}
          width={400}
          height={104}
          title="Model cross-check"
          lines={[
            "Two-stage boosted trees (LightGBM)",
            "Close or not, then ask or escalate",
            "77 facts that mean the same at any firm",
          ]}
          tone="var(--secondary)"
          model
        />

        <path d="M40 724 H96" stroke="var(--black)" strokeWidth={2} />
        <text x={108} y={729} className="md-line">
          Scored path
        </text>
        <path d="M40 758 H96" stroke="var(--black)" strokeWidth={2} strokeDasharray="6 5" />
        <text x={108} y={763} className="md-line">
          Models that advise
        </text>
      </svg>
    </div>
  );
}
