// D-093 S-02 RecCard
// 骨架与 apps/web/src/components/RecCard.tsx 1:1 (rank chip + tags row + title +
// summary + price + reasoning + meta + 双 action). 沙箱版只 *叠加* 调试层:
//   - L3 chip (showDebug)
//   - L1/L2/L3 数字行 (showDebug, 替代 user why)
//   - conflict pill (rec.conflict 命中时)
//   - 探索 tag (rec.explore=true)
// 不改骨架, 不"美化".
import type { Rec } from "../types/sandbox";

export interface RecCardProps {
  rec: Rec;
  selected?: boolean;
  showDebug?: boolean;
  onSelect?: () => void;
  onEat?: () => void;
  onDetail?: () => void;
}

export function RecCard({
  rec,
  selected = false,
  showDebug = false,
  onSelect,
  onEat,
  onDetail,
}: RecCardProps) {
  const hasConflict = rec.conflict != null;
  const conflictReason = rec.conflict?.reason ?? "";
  return (
    <div
      className={`rec-card ${hasConflict ? "conflict" : ""} ${selected ? "selected" : ""}`}
      onClick={onSelect}
      role="button"
      tabIndex={0}
    >
      <div className="rec-head">
        <span className="rec-rank">
          #<span className="num">{rec.rank}</span>
        </span>
        {rec.explore && <span className="tag explore">⊕ 探索</span>}
        {rec.l1Hits.slice(0, 2).map((h) => (
          <span key={h} className="tag benefit">
            ✓ {h}
          </span>
        ))}
        {hasConflict && <span className="tag danger">⚠ 含辣</span>}
        {showDebug && (
          <span className="rec-score">
            <span className="l3-label">L3</span>
            <span className="l3">{rec.l3}</span>
          </span>
        )}
        <span className="rec-price">¥{rec.price}</span>
      </div>

      <div className="rec-title">
        {rec.name}
        <span className="rec-title-venue">({rec.venue})</span>
      </div>
      <div className="rec-sub">{rec.dishes ? rec.dishes.join(" + ") : rec.venue}</div>

      <div className="rec-why">
        <span className="why-ico">💬</span>
        <span className="why-text">
          {showDebug ? (
            <>
              L1 命中{" "}
              {rec.l1Hits.map((h, i) => (
                <span key={h}>
                  <em className="dbg-hit">{h}</em>
                  {i < rec.l1Hits.length - 1 ? " · " : ""}
                </span>
              ))}
              {"  ·  L2 "}
              <em className="dbg-num mono">{rec.l2.toFixed(2)}</em>
              {"  ·  L3 "}
              <em className="dbg-num pos mono">+{rec.boost}</em>
              {" ← intent "}
              <em className="dbg-intent">{rec.intent}</em>
            </>
          ) : (
            rec.why
          )}
        </span>
      </div>

      {hasConflict && (
        <div className="rec-conflict">
          <span>⚠</span>
          <span>{conflictReason}</span>
        </div>
      )}

      <div className="rec-meta">
        <span className="m-item">{rec.meta.eta}</span>
        <span className="m-item">{rec.meta.dist}</span>
        <span className="m-item good">蛋白 {rec.meta.protein}g</span>
        <span className="m-item">油 {rec.meta.oil}</span>
        <div className="m-actions">
          <button
            className="card-btn"
            onClick={(e) => {
              e.stopPropagation();
              onDetail?.();
            }}
          >
            查看详情
          </button>
          <button
            className="card-btn primary"
            onClick={(e) => {
              e.stopPropagation();
              onEat?.();
            }}
          >
            就这个 →
          </button>
        </div>
      </div>
    </div>
  );
}
