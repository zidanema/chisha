// Workspace 顶栏 (V12 DAG). V1.0 后 B · 沙盒模拟已独立为 apps/sandbox-lab :5175,
// 这里只剩 A · 分析 trace. 视觉 1:1 搬自 chisha-debug/project/wa-app.jsx.

export function WorkspaceSwitch({ active }: { active: "A" }) {
  return (
    <div className="workspace-switch">
      <button className={`ws ${active === "A" ? "active" : ""}`}>
        <span className="glyph">▣</span>
        <span>分析</span>
        <span className="sub">trace</span>
      </button>
    </div>
  );
}
