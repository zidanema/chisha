// D-088 S-01 scaffold demo shell.
// S-02 起把这个 demo 替换成 TopBar + Banners + Timeline + DecisionArea + 4 panels.
import { useTweaks, ACCENTS } from "./hooks/useTweaks";

export function App() {
  const { tweaks, setTweak } = useTweaks();

  return (
    <div className="demo-shell">
      <header className="demo-header">
        <div className="brand">
          <span className="brand-mark" />
          <span className="brand-title">Sandbox Lab</span>
          <span className="brand-sub">白盒时光机 · /sandbox-lab (S-01 scaffold)</span>
        </div>
        <div className="demo-controls">
          <span className="control-label">主题</span>
          <button
            className={`pill ${tweaks.theme === "light" ? "on" : ""}`}
            onClick={() => setTweak("theme", "light")}
          >
            浅色
          </button>
          <button
            className={`pill ${tweaks.theme === "dark" ? "on" : ""}`}
            onClick={() => setTweak("theme", "dark")}
          >
            深色
          </button>
          <span className="control-label">主色</span>
          {ACCENTS.map((c) => (
            <button
              key={c}
              aria-label={`accent ${c}`}
              data-accent={c}
              className={`swatch ${tweaks.accent === c ? "on" : ""}`}
              onClick={() => setTweak("accent", c)}
            />
          ))}
        </div>
      </header>

      <main className="demo-main">
        <section className="demo-card">
          <h2 className="demo-h">字体 + tokens 验证</h2>
          <p className="demo-p">
            Inter sans-serif + Noto Sans SC 中文混排 — 此句应当字体协调,字重 400。
          </p>
          <p className="demo-p">
            Mono 字号(数字 + trace id):
            <code className="mono"> 0123456789 · tr_D3午_寿司拼盘 · L3=92 </code>
          </p>
          <p className="demo-p demo-p-muted">
            tokens 自检: text-1 / text-2 / text-3 / text-4 应呈现 4 档对比。
          </p>
          <div className="demo-row">
            <button className="btn-primary">就这个 →</button>
            <button className="btn-ghost">查看详情</button>
            <span className="chip">✓ 高蛋白</span>
            <span className="chip warn">⚠ 含辣</span>
          </div>
        </section>

        <section className="demo-card">
          <h2 className="demo-h">accent 切换</h2>
          <p className="demo-p">
            点上方 4 个色块,本卡片所有 accent 派生(按钮 / chip / ring / soft)应整套换。
          </p>
          <div className="demo-row demo-row-tight">
            <span className="dot dot-eat" /> eat
            <span className="dot dot-skip" /> skip
            <span className="dot dot-refine" /> refine
            <span className="dot dot-conflict" /> conflict
            <span className="dot dot-explore" /> explore
          </div>
        </section>
      </main>
    </div>
  );
}
