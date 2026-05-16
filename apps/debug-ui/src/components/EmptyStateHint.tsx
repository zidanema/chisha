// First-launch hint shown above the panels when no real run has happened.
// Extracted from App.tsx in Phase 7.

export function EmptyStateHint() {
  return (
    <div
      style={{
        margin: "12px 16px",
        padding: "14px 16px",
        border: "1px dashed var(--accent)",
        background: "var(--bg-2)",
        borderRadius: 4,
        fontSize: 12,
        color: "var(--t-1)",
        display: "flex",
        alignItems: "center",
        gap: 12,
      }}
    >
      <span style={{ fontFamily: "var(--mono)", color: "var(--accent)", fontWeight: 600 }}>#</span>
      <span>
        空 session · 当前是 mock 数据.{" "}
        <strong>点 ▶ 触发首轮推荐</strong> (或 ⌘Enter / Ctrl+Enter) 来跑一次真实链路.
      </span>
    </div>
  );
}
