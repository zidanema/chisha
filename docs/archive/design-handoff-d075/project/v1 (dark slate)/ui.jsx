// ui.jsx — shared UI primitives

const { useState, useEffect, useRef, useMemo, useCallback } = React;

function StatusBadge({ status, size = "md" }) {
  const map = {
    ok:           { cls: "green",  text: "OK" },
    fallback:     { cls: "red",    text: "FALLBACK" },
    config_error: { cls: "orange", text: "CONFIG_ERROR" },
    skipped:      { cls: "gray",   text: "SKIPPED" },
    warn:         { cls: "orange", text: "WARN" },
  };
  const m = map[status] || map.skipped;
  return (
    <span className={`badge ${m.cls} ${size === "xl" ? "xl" : size === "lg" ? "lg" : ""}`}>
      <span className="dot"></span>
      {m.text}
    </span>
  );
}

function Pill({ children, tone = "gray" }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

function MiniFunnel({ stages }) {
  // show 5 picked stages: raw → recall passed → top60 → top5
  const picked = [
    { k: "DISHES",    v: stages[0].value.toLocaleString() },
    { k: "PASSED",    v: stages[1].value.toLocaleString() },
    { k: "COMBOS",    v: stages[6].value.toLocaleString() },
    { k: "TOP 60",    v: "60" },
    { k: "TOP 5",     v: "5" },
  ];
  return (
    <div className="mini-funnel">
      {picked.map((s, i) => (
        <React.Fragment key={i}>
          <div className="mini-step">
            <div className="v num">{s.v}</div>
            <div className="k">{s.k}</div>
          </div>
          {i < picked.length - 1 && (
            <div className="mini-arrow">
              <span className="pct num">
                {Math.round(parseInt(picked[i+1].v.replace(/,/g, "")) / parseInt(picked[i].v.replace(/,/g, "")) * 1000) / 10}%
              </span>
            </div>
          )}
        </React.Fragment>
      ))}
    </div>
  );
}

function CopyBtn({ text = "copy", label = "copy" }) {
  const [done, setDone] = useState(false);
  return (
    <button
      className="copy-btn"
      onClick={() => {
        // ignore actual copy — just visual feedback
        setDone(true);
        setTimeout(() => setDone(false), 900);
      }}
    >
      {done ? "✓ copied" : label}
    </button>
  );
}

// trivial JSON pretty + syntax highlighter
function highlightJson(text, options = {}) {
  // returns array of {type, text}
  const tokens = [];
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
      // detect key (followed by :)
      let k = j + 1;
      while (k < text.length && /\s/.test(text[k])) k++;
      if (text[k] === ":") tokens.push({ type: "key", text: str });
      else tokens.push({ type: "str", text: str });
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
      tokens.push({ type: /^(true|false|null)$/.test(word) ? "kw" : "txt", text: word });
      i = j;
    } else {
      tokens.push({ type: "p", text: c });
      i++;
    }
  }
  return tokens;
}

function CodeBlock({ text, mode = "plain", searchTerm = "", highlightCache = false }) {
  // mode: plain | json
  let content;
  if (mode === "json") {
    let pretty = text;
    try {
      pretty = JSON.stringify(typeof text === "string" ? JSON.parse(text) : text, null, 2);
    } catch (e) {
      pretty = typeof text === "string" ? text : JSON.stringify(text, null, 2);
    }
    const tokens = highlightJson(pretty);
    content = tokens.map((t, i) => {
      const cls = { str: "tok-str", num: "tok-num", key: "tok-key", kw: "tok-kw", com: "tok-com" }[t.type];
      if (cls) return <span key={i} className={cls}>{t.text}</span>;
      return <span key={i}>{t.text}</span>;
    });
  } else if (highlightCache) {
    // highlight cache_control markers
    const parts = text.split(/(<!--\s*⚡\s*cache_control[^>]*-->)/);
    content = parts.map((p, i) =>
      /cache_control/.test(p)
        ? <span key={i} className="hl-cache">{p}</span>
        : <span key={i}>{p}</span>
    );
  } else {
    content = text;
  }
  // apply search highlight if provided
  if (searchTerm && typeof text === "string") {
    // we'll skip implementing search-in-tokens for brevity but keep input wired
  }
  return (
    <pre>
      {content}
    </pre>
  );
}

Object.assign(window, { StatusBadge, Pill, MiniFunnel, CopyBtn, CodeBlock });
