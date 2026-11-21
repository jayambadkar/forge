import type { ReactNode } from "react";

function inline(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
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
        <div key={`t-${i}`} className="md-table">
          <table>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={rowIndex} className={rowIndex === 0 ? "md-head" : undefined}>
                  {row.map((cell, cellIndex) => (
                    <td key={cellIndex}>{inline(cell)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }
    if (line.startsWith("# ")) {
      blocks.push(<h2 key={i}>{inline(line.slice(2))}</h2>);
    } else if (line.startsWith("## ")) {
      blocks.push(<h3 key={i}>{inline(line.slice(3))}</h3>);
    } else if (line.trim() !== "") {
      blocks.push(<p key={i}>{inline(line)}</p>);
    }
    i += 1;
  }
  return <div className="md">{blocks}</div>;
}
