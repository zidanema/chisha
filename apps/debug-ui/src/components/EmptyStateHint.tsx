// Shown when trace_store is empty AND no Live run has happened yet.
// D-079 cleanup: 删 mock 之后必须由真实环境(apps/web)产生 trace.

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
        flexDirection: "column",
        gap: 8,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ fontFamily: "var(--mono)", color: "var(--accent)", fontWeight: 600 }}>#</span>
        <strong>trace_store 是空的 · 没有可 Replay 的历史</strong>
      </div>
      <div style={{ paddingLeft: 22, lineHeight: 1.6 }}>
        debug-ui 只 Replay 真实环境写入的 trace。两种方式产生数据:
      </div>
      <ul style={{ paddingLeft: 44, margin: 0, lineHeight: 1.6 }}>
        <li>
          <strong>推荐</strong>: 在 apps/web (用户视图 :5173) 跑 1-2 次推荐 →
          POST /api/recommend → 真实 trace 落盘
        </li>
        <li>
          <strong>临时</strong>: 点左侧 <strong>⚡ Live 试跑</strong> →
          /api/debug_recommend (本次只显示, 不落盘, 关 tab 即丢)
        </li>
      </ul>
    </div>
  );
}
