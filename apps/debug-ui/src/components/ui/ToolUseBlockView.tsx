// L3 raw-response tool_use block viewer with collapsible nested JSON.
// Extracted from PanelL3.tsx in Phase 7 to keep that file under 400 lines.

import { useState } from "react";
import { CodeBlock } from "./CodeBlock";

const MAX_COLLAPSED_DEPTH = 6;

function CollapsedJson({ value, depth }: { value: unknown; depth: number }) {
  if (depth > MAX_COLLAPSED_DEPTH) {
    return (
      <span className="dim mono" style={{ fontSize: 10 }}>
        …(深度 &gt;{MAX_COLLAPSED_DEPTH}, 展开受限)
      </span>
    );
  }
  if (value === null) return <span className="tok-kw">null</span>;
  if (typeof value === "string") return <span className="tok-str">"{value}"</span>;
  if (typeof value === "number") return <span className="tok-num">{value}</span>;
  if (typeof value === "boolean") return <span className="tok-kw">{String(value)}</span>;
  if (Array.isArray(value)) {
    if (depth >= 1 && value.length > 0) {
      return (
        <details>
          <summary style={{ cursor: "pointer", color: "var(--t-2)" }}>
            [{value.length} items]
          </summary>
          <pre style={{ marginLeft: 12 }}>
            {value.map((v, i) => (
              <div key={i}>
                <span className="tok-num">{i}</span>: <CollapsedJson value={v} depth={depth + 1} />
              </div>
            ))}
          </pre>
        </details>
      );
    }
    return (
      <pre>
        [
        {value.map((v, i) => (
          <div key={i} style={{ marginLeft: 12 }}>
            <CollapsedJson value={v} depth={depth + 1} />
            {i < value.length - 1 ? "," : ""}
          </div>
        ))}
        ]
      </pre>
    );
  }
  if (typeof value === "object") {
    const entries = Object.entries(value);
    if (depth >= 1 && entries.length > 0) {
      return (
        <details>
          <summary style={{ cursor: "pointer", color: "var(--t-2)" }}>
            {`{${entries.length} keys}`}
          </summary>
          <pre style={{ marginLeft: 12 }}>
            {entries.map(([k, v]) => (
              <div key={k}>
                <span className="tok-key">"{k}"</span>:{" "}
                <CollapsedJson value={v} depth={depth + 1} />
              </div>
            ))}
          </pre>
        </details>
      );
    }
    return (
      <pre>
        {`{`}
        {entries.map(([k, v]) => (
          <div key={k} style={{ marginLeft: 12 }}>
            <span className="tok-key">"{k}"</span>:{" "}
            <CollapsedJson value={v} depth={depth + 1} />
          </div>
        ))}
        {`}`}
      </pre>
    );
  }
  return <span>{String(value)}</span>;
}

export function ToolUseBlockView({ input }: { input: unknown }) {
  const [allExpanded, setAllExpanded] = useState(false);
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "flex-end", padding: "2px 8px" }}>
        <button
          className="icon-btn"
          onClick={() => setAllExpanded((v) => !v)}
          style={{ fontSize: 10 }}
        >
          {allExpanded ? "折叠所有" : "全部展开"}
        </button>
      </div>
      {allExpanded ? (
        <CodeBlock text={input} mode="json" />
      ) : (
        <CollapsedJson value={input} depth={0} />
      )}
    </div>
  );
}
