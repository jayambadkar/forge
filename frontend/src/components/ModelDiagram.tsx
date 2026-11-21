type BoxProps = {
  x: number;
  y: number;
  width?: number;
  height: number;
  title: string;
  lines: string[];
  tone: string;
  dashed?: boolean;
};

function Box({ x, y, width = 200, height, title, lines, tone, dashed = false }: BoxProps) {
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        fill="var(--white)"
        stroke={tone}
        strokeWidth={dashed ? 2 : 3}
        strokeDasharray={dashed ? "8 6" : undefined}
      />
      {dashed ? null : <rect x={x} y={y} width={width} height={6} fill={tone} />}
      <text x={x + 14} y={y + 32} className="md-title">
        {title}
      </text>
      {lines.map((line, index) => (
        <text key={line} x={x + 14} y={y + 56 + index * 20} className="md-line">
          {line}
        </text>
      ))}
    </g>
  );
}

function Arrow({ d, dashed = false }: { d: string; dashed?: boolean }) {
  return (
    <path
      d={d}
      fill="none"
      stroke="var(--black)"
      strokeWidth={2}
      strokeDasharray={dashed ? "6 5" : undefined}
      markerEnd="url(#md-arrow)"
    />
  );
}

export function ModelDiagram() {
  return (
    <div className="model-diagram">
      <svg
        viewBox="0 0 960 560"
        role="img"
        aria-labelledby="md-heading md-desc"
        xmlns="http://www.w3.org/2000/svg"
      >
        <title id="md-heading">How a case moves through Forge</title>
        <desc id="md-desc">
          The institution folder goes to the policy engine, which writes the output file. The output
          file is scored and feeds the analyst desk and audit log. Separately, case facts feed a
          two-stage model and a cost-aware decision, which appears on the desk as a cross-check
          only. An optional language-model reviewer sits between the policy engine and the output
          file and cannot close a case the rules did not.
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

        <rect x={250} y={14} width={460} height={28} fill="var(--green-tint)" />
        <text x={480} y={34} textAnchor="middle" className="md-band">
          Scored path: this writes the submission
        </text>

        <Box
          x={20}
          y={50}
          height={120}
          title="Institution folder"
          lines={["cases, alerts,", "transactions, documents,", "policy"]}
          tone="var(--blue)"
        />
        <Box
          x={260}
          y={50}
          height={120}
          title="Policy engine"
          lines={["written SOP rules", "deterministic"]}
          tone="var(--blue)"
        />
        <Box
          x={500}
          y={50}
          height={120}
          title="Output file"
          lines={["system/run", "the scored submission"]}
          tone="var(--green)"
        />
        <Box
          x={740}
          y={50}
          height={120}
          title="Analyst desk"
          lines={["+ audit log", "every action appended"]}
          tone="var(--blue)"
        />
        <Arrow d="M220 110 H256" />
        <Arrow d="M460 110 H496" />
        <Arrow d="M700 110 H736" />

        <Box
          x={300}
          y={220}
          width={360}
          height={100}
          title="Language-model reviewer (optional)"
          lines={["off by default", "cannot close a case the rules did not"]}
          tone="var(--secondary)"
          dashed
        />
        <Arrow d="M340 170 V216" dashed />
        <Arrow d="M620 220 V174" dashed />

        <Box
          x={20}
          y={360}
          height={150}
          title="Case facts"
          lines={[
            "firm-independent: rules,",
            "document kinds,",
            "coverage, own-account,",
            "profile",
          ]}
          tone="var(--orange)"
        />
        <Box
          x={260}
          y={360}
          height={150}
          title="Two-stage model"
          lines={["1: close or not", "2: request vs escalate"]}
          tone="var(--orange)"
        />
        <Box
          x={500}
          y={360}
          height={150}
          title="Cost-aware decision"
          lines={["scoring matrix", "no close without a", "supporting document"]}
          tone="var(--orange)"
        />
        <Box
          x={740}
          y={360}
          height={150}
          title="Model cross-check"
          lines={["shown on the desk", "flags disagreements", "never changes the output"]}
          tone="var(--orange)"
        />
        <Arrow d="M120 170 V356" />
        <Arrow d="M220 430 H256" />
        <Arrow d="M460 430 H496" />
        <Arrow d="M700 430 H736" />
        <Arrow d="M840 360 V174" />
        <text x={850} y={270} className="md-line">
          flags only
        </text>

        <text x={20} y={540} className="md-note">
          Not scored. The model is trained on the policy engine’s verdicts and checks them.
        </text>
      </svg>
    </div>
  );
}
