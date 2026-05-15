import { useMemo } from "react";

// D-053: 偏好页默认 = 只读 YAML 视图（行号 + 语法着色）。
// 编辑只在用户主动点 "编辑" 时进入表单态。

function YamlLine({ text }: { text: string }) {
  const commentIdx = text.indexOf("#");
  let body = text;
  let comment = "";
  if (commentIdx >= 0 && !/^\s*#/.test(text)) {
    body = text.slice(0, commentIdx);
    comment = text.slice(commentIdx);
  } else if (/^\s*#/.test(text)) {
    return <span style={{ color: "var(--muted)" }}>{text}</span>;
  }
  const m = body.match(/^(\s*)(-?\s*)([^:]+?):(\s*)(.*)$/);
  if (m) {
    const [, indent, dash, key, sp, val] = m;
    let valEl: React.ReactNode = null;
    if (val) {
      if (val === "|" || val === ">")
        valEl = <span style={{ color: "var(--muted)" }}>{val}</span>;
      else if (val === "null" || /^(true|false)$/.test(val))
        valEl = <span style={{ color: "var(--info)" }}>{val}</span>;
      else if (/^-?\d+(\.\d+)?$/.test(val))
        valEl = <span style={{ color: "var(--accent)" }}>{val}</span>;
      else if (val.startsWith("[") && val.endsWith("]"))
        valEl = <span style={{ color: "var(--good)" }}>{val}</span>;
      else if (val.startsWith('"') && val.endsWith('"'))
        valEl = <span style={{ color: "var(--good)" }}>{val}</span>;
      else valEl = <span style={{ color: "var(--fg)" }}>{val}</span>;
    }
    return (
      <>
        <span>{indent}</span>
        {dash && <span style={{ color: "var(--accent)" }}>{dash}</span>}
        <span style={{ color: "var(--info)" }}>{key}</span>
        <span>:{sp}</span>
        {valEl}
        {comment && <span style={{ color: "var(--muted)" }}>{comment}</span>}
      </>
    );
  }
  if (/^\s*-\s/.test(body))
    return (
      <span style={{ color: "var(--fg)" }}>
        {body}
        {comment && <span style={{ color: "var(--muted)" }}>{comment}</span>}
      </span>
    );
  return (
    <span style={{ color: "var(--fg)" }}>
      {body}
      {comment && <span style={{ color: "var(--muted)" }}>{comment}</span>}
    </span>
  );
}

export function YamlViewer({ source }: { source: string }) {
  const lines = useMemo(() => source.split("\n"), [source]);
  return (
    <pre
      className="rounded-lg border border-[color:var(--border)] bg-[color:var(--surface)] p-4 overflow-x-auto text-[12.5px] leading-[1.65] font-mono"
      style={{ tabSize: 2 }}
    >
      {lines.map((ln, i) => (
        <div key={i} className="flex">
          <span className="select-none w-9 shrink-0 text-right pr-3 text-[color:var(--muted)] opacity-50 tabular-nums">
            {i + 1}
          </span>
          <code>
            <YamlLine text={ln} />
          </code>
        </div>
      ))}
    </pre>
  );
}
