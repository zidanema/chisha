import { Fragment } from "react";

type Token = { type: "key" | "str" | "num" | "kw" | "txt" | "p" | "com"; text: string };

function highlightJson(text: string): Token[] {
  const tokens: Token[] = [];
  let i = 0;
  while (i < text.length) {
    const c = text[i];
    if (c === '"') {
      let j = i + 1;
      while (j < text.length && text[j] !== '"') {
        if (text[j] === "\\") j++;
        j++;
      }
      const str = text.slice(i, j + 1);
      let k = j + 1;
      while (k < text.length && /\s/.test(text[k])) k++;
      tokens.push({ type: text[k] === ":" ? "key" : "str", text: str });
      i = j + 1;
    } else if (/[0-9.\-]/.test(c)) {
      let j = i;
      while (j < text.length && /[0-9eE.\-+]/.test(text[j])) j++;
      tokens.push({ type: "num", text: text.slice(i, j) });
      i = j;
    } else if (/[a-z]/i.test(c)) {
      let j = i;
      while (j < text.length && /[a-z_]/i.test(text[j])) j++;
      const word = text.slice(i, j);
      tokens.push({
        type: /^(true|false|null)$/.test(word) ? "kw" : "txt",
        text: word,
      });
      i = j;
    } else {
      tokens.push({ type: "p", text: c });
      i++;
    }
  }
  return tokens;
}

const TOKEN_CLASS: Partial<Record<Token["type"], string>> = {
  str: "tok-str",
  num: "tok-num",
  key: "tok-key",
  kw: "tok-kw",
  com: "tok-com",
};

// Escape user input so we can build a safe RegExp.
function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Apply find-in-text highlight to a plain text string. Splits on the search
// term (case-insensitive) and wraps matches in <mark>. Returns the original
// string when query is empty.
function highlightSearch(text: string, query: string): React.ReactNode {
  if (!query) return text;
  const re = new RegExp(`(${escapeRegExp(query)})`, "gi");
  const parts = text.split(re);
  return parts.map((p, i) =>
    re.test(p) ? <mark key={i} className="find-hit">{p}</mark> : <Fragment key={i}>{p}</Fragment>,
  );
}

export function CodeBlock({
  text,
  mode = "plain",
  highlightCache = false,
  searchTerm = "",
}: {
  text: string | unknown;
  mode?: "plain" | "json";
  highlightCache?: boolean;
  searchTerm?: string;
}) {
  let content: React.ReactNode;
  if (mode === "json") {
    let pretty: string;
    try {
      pretty = JSON.stringify(typeof text === "string" ? JSON.parse(text) : text, null, 2);
    } catch {
      pretty = typeof text === "string" ? text : JSON.stringify(text, null, 2);
    }
    const tokens = highlightJson(pretty);
    content = tokens.map((t, i) => {
      const cls = TOKEN_CLASS[t.type];
      return cls ? (
        <span key={i} className={cls}>{t.text}</span>
      ) : (
        <span key={i}>{t.text}</span>
      );
    });
  } else if (highlightCache && typeof text === "string") {
    const parts = text.split(/(<!--\s*⚡\s*cache_control[^>]*-->)/);
    content = parts.map((p, i) =>
      /cache_control/.test(p) ? (
        <span key={i} className="hl-cache">{p}</span>
      ) : (
        <Fragment key={i}>{highlightSearch(p, searchTerm)}</Fragment>
      ),
    );
  } else {
    const raw = typeof text === "string" ? text : JSON.stringify(text, null, 2);
    content = highlightSearch(raw, searchTerm);
  }
  return <pre>{content}</pre>;
}
