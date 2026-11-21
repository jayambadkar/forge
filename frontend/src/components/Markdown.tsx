import type { ReactNode } from "react";

function inline(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={index} className="font-medium text-ink">
          {part.slice(2, -2)}
        </strong>
      );
    }
    return <span key={index}>{part}</span>;
  });
}

export function Markdown({ text }: { text: string }) {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim().startsWith("|") && lines[i + 1]?.includes("|---")) {
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        if (!lines[i].includes("---")) {
          rows.push(
            lines[i]
              .split("|")
              .slice(1, -1)
              .map((cell) => cell.trim()),
          );
        }
        i += 1;
      }
      blocks.push(
        <table key={`t-${i}`} className="my-3 w-full border-collapse text-left text-[12px]">
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={rowIndex} className={rowIndex === 0 ? "text-faint" : "border-t border-line"}>
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex} className="px-2 py-1 align-top">
                    {inline(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>,
      );
      continue;
    }
    if (line.startsWith("# ")) {
      blocks.push(
        <h2 key={i} className="mb-2 text-[15px] font-medium text-ink">
          {inline(line.slice(2))}
        </h2>,
      );
    } else if (line.startsWith("## ")) {
      blocks.push(
        <h3 key={i} className="mt-3 mb-1 text-[13px] font-medium text-copper-2">
          {inline(line.slice(3))}
        </h3>,
      );
    } else if (line.trim() === "") {
      blocks.push(<div key={i} className="h-2" />);
    } else {
      blocks.push(
        <p key={i} className="leading-relaxed text-ink/90">
          {inline(line)}
        </p>,
      );
    }
    i += 1;
  }
  return <div className="font-sans text-[12.5px]">{blocks}</div>;
}
