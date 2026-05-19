// D-088 S-02 ReviewCard: 回顾模式 (只读) 替代 DecisionArea.
// skip 模式: 极简卡 + "回到决策模式". eat 模式: header + callout + altScores + 跳 trace.
import type { Meal } from "../types/sandbox";

export interface ReviewCardProps {
  meal: Meal | null;
  onOpenTrace?: () => void;
  onExit?: () => void;
}

export function ReviewCard({ meal, onOpenTrace, onExit }: ReviewCardProps) {
  if (!meal) return null;

  if (meal.state === "skip") {
    return (
      <div className="col col-left review">
        <ReviewHeader meal={meal} onExit={onExit} />
        <div className="review-empty">
          <div className="rv-empty-ico">⊘</div>
          <div className="rv-empty-title">该顿被跳过</div>
          <div className="rv-empty-sub">
            时钟前进 + 无学习。recent_dishes / fatigue / taste_profile 均未变。
          </div>
          <button className="card-btn" onClick={onExit}>
            ← 回到决策模式
          </button>
        </div>
      </div>
    );
  }

  const pickedIdx = meal.altScores.findIndex((a) => a.picked);

  return (
    <div className="col col-left review">
      <ReviewHeader meal={meal} onExit={onExit} />

      <div className="review-callout">
        <span className="rc-label">实际选了</span>
        <span className="rc-name">
          #{pickedIdx + 1} {meal.dish}
        </span>
        <span className="rc-score mono">L3 {meal.score}</span>
      </div>

      <div className="review-list">
        {meal.altScores.map((alt, i) => (
          <div
            key={`${alt.name}-${i}`}
            className={`review-row ${alt.picked ? "picked" : ""}`}
          >
            <span className="rv-rank mono">#{i + 1}</span>
            <span className="rv-name">{alt.name}</span>
            {alt.picked && <span className="rv-pick-badge">✓ 选了</span>}
            <span className="rv-score mono">{alt.score}</span>
          </div>
        ))}
      </div>

      <button className="review-trace-btn" onClick={onOpenTrace}>
        <span>🔍</span> 打开这顿的完整 trace
      </button>

      <div className="review-footnote">
        Trace 抽屉显示 L1 / L2 / L3 / 规则过滤的完整链路 · 与时间冻结视图一致
      </div>
    </div>
  );
}

function ReviewHeader({
  meal,
  onExit,
}: {
  meal: Meal;
  onExit?: () => void;
}) {
  const isSkip = meal.state === "skip";
  return (
    <div className="review-head">
      <div>
        <div className="rh-title">
          回顾 ·{" "}
          <strong>
            D{meal.day} {meal.slot}
          </strong>
        </div>
        <div className="rh-sub mono">
          {isSkip
            ? "该顿被跳过 · 系统状态未变"
            : "该顿当时的 5 条推荐 · 实际选择高亮"}
        </div>
      </div>
      <button className="rh-exit" onClick={onExit} title="Esc 也可退出">
        ✕ 回到决策
      </button>
    </div>
  );
}
