import { useState } from "react";

export function CopyBtn({
  text,
  label = "copy",
}: {
  text?: string;
  label?: string;
}) {
  const [done, setDone] = useState(false);
  return (
    <button
      className="copy-btn"
      onClick={() => {
        if (text != null && navigator.clipboard) {
          navigator.clipboard.writeText(text).catch(() => {});
        }
        setDone(true);
        setTimeout(() => setDone(false), 900);
      }}
    >
      {done ? "✓ copied" : label}
    </button>
  );
}
