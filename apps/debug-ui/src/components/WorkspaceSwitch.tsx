// Workspace 切换 (A · 分析 trace / B · 沙盒模拟 locked). B 是占位, 点击 toast.
// 视觉 1:1 搬自 chisha-debug/project/wa-app.jsx WorkspaceSwitch.

import { pushToast } from "./Toaster";

export function WorkspaceSwitch({ active }: { active: "A" }) {
  function onLockedClick() {
    pushToast({
      kind: "warn",
      title: "敬待 B workspace · 沙盒模拟",
      detail: "本期只做 A · 分析 trace; B 下个版本".slice(0, 80),
    });
  }
  return (
    <div className="workspace-switch">
      <button className={`ws ${active === "A" ? "active" : ""}`}>
        <span className="glyph">▣</span>
        <span>分析</span>
        <span className="sub">trace</span>
      </button>
      <button className="ws locked" title="B · 沙盒模拟 — 另起 brief" onClick={onLockedClick}>
        <span className="glyph">◌</span>
        <span>模拟</span>
        <span className="sub">敬待</span>
      </button>
    </div>
  );
}
