// D-079: Live mode banner. /api/debug_recommend 永不写盘 (Codex +1, DESIGN §7.4).
// 仅在 Live mode 显示, 提示用户当前查看的是临时实验, 不会进 Replay history.

export type LiveBannerProps = {
  llmCalled?: boolean;
  onExit: () => void;
};

export function LiveBanner({ llmCalled, onExit }: LiveBannerProps) {
  return (
    <div className="live-banner" role="status">
      <div className="lb-left">
        <span className="lb-tag">Live</span>
        <span>
          临时试跑 · <span className="dim mono">no trace persistence</span>
          {llmCalled === true && (
            <span className="dim mono" style={{ marginLeft: 8 }}>
              · L3 LLM called
            </span>
          )}
          {llmCalled === false && (
            <span className="dim mono" style={{ marginLeft: 8 }}>
              · fallback only
            </span>
          )}
        </span>
      </div>
      <button className="lb-exit" onClick={onExit} title="退出 Live, 回到 Replay">
        ✕ 退出 Live
      </button>
    </div>
  );
}
