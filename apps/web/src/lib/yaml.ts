// Minimal YAML serializer for the read-only profile preview.
// Lifted from the prototype components.jsx (toYaml). Not a general-purpose
// serializer — only handles the shapes profile.yaml actually uses (scalars,
// arrays of scalars, nested maps, multi-line literal blocks via `|`).

function yamlEscapeScalar(s: string): string {
  if (s === "") return '""';
  if (/^[-+0-9{}\[\],&*?!|>%@`#"']/.test(s)) return JSON.stringify(s);
  return s;
}

export function toYaml(obj: unknown, indent = 0): string {
  const pad = "  ".repeat(indent);
  const lines: string[] = [];
  if (obj == null || typeof obj !== "object") {
    return String(obj);
  }
  for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
    if (v === null || v === undefined) {
      lines.push(`${pad}${k}: null`);
      continue;
    }
    if (typeof v === "string") {
      if (v.includes("\n")) {
        lines.push(`${pad}${k}: |`);
        v.replace(/\n+$/, "")
          .split("\n")
          .forEach((ln) => lines.push(`${pad}  ${ln}`));
      } else {
        lines.push(`${pad}${k}: ${yamlEscapeScalar(v)}`);
      }
    } else if (typeof v === "number" || typeof v === "boolean") {
      lines.push(`${pad}${k}: ${v}`);
    } else if (Array.isArray(v)) {
      if (v.length === 0) {
        lines.push(`${pad}${k}: []`);
        continue;
      }
      const allScalar = v.every(
        (x) =>
          typeof x === "string" || typeof x === "number" || typeof x === "boolean"
      );
      if (allScalar) {
        const inner = v
          .map((x) => (typeof x === "string" ? yamlEscapeScalar(x) : x))
          .join(", ");
        lines.push(`${pad}${k}: [${inner}]`);
      } else {
        lines.push(`${pad}${k}:`);
        v.forEach((item) => {
          if (typeof item === "object" && item !== null) {
            const sub = toYaml(item, indent + 1).split("\n");
            sub[0] = `${pad}  - ` + sub[0].slice((indent + 1) * 2);
            lines.push(sub.join("\n"));
          } else {
            lines.push(`${pad}  - ${item}`);
          }
        });
      }
    } else if (typeof v === "object") {
      lines.push(`${pad}${k}:`);
      lines.push(toYaml(v, indent + 1));
    }
  }
  return lines.join("\n");
}
