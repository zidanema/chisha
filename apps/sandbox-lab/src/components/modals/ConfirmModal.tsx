// D-088 S-02 ConfirmModal: rollback / branch 二次确认.
import { useEffect, useState } from "react";
import type { Meal } from "../../types/sandbox";

export type ConfirmKind = "rollback" | "branch";

export interface ConfirmModalProps {
  open: boolean;
  kind: ConfirmKind | null;
  meal: Meal | null;
  currentIdx: number;
  onClose?: () => void;
  onConfirm?: (branchName: string | null) => void;
}

export function ConfirmModal({
  open,
  kind,
  meal,
  currentIdx,
  onClose,
  onConfirm,
}: ConfirmModalProps) {
  const [branchName, setBranchName] = useState("");
  useEffect(() => {
    if (!open) setBranchName("");
  }, [open]);

  if (!open || !meal || !kind) return null;
  const undoCount = currentIdx - meal.idx;

  return (
    <div className="modal-mask open" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        {kind === "rollback" ? (
          <>
            <h3>
              ↶ 回滚到 D{meal.day} {meal.slot}
            </h3>
            <p>
              撤销 D{meal.day} {meal.slot} 及之后的{" "}
              <strong>{undoCount} 顿</strong>,该格将变为 current,重新开始决策。
              <br />
              <span className="confirm-warn">该操作不可撤销。</span>
            </p>
          </>
        ) : (
          <>
            <h3>
              ⌥ 从 D{meal.day} {meal.slot} 分支
            </h3>
            <p>
              在该点复制当前 session,新分支会继承到 D{meal.day} {meal.slot}{" "}
              的状态。当前 session 保留不动。
            </p>
            <input
              type="text"
              placeholder="新分支名,例如 session-换策略测试"
              value={branchName}
              onChange={(e) => setBranchName(e.target.value)}
              autoFocus
            />
          </>
        )}
        <div className="modal-actions">
          <button className="tbtn" onClick={onClose}>
            取消
          </button>
          <button
            className="tbtn primary"
            disabled={kind === "branch" && !branchName.trim()}
            onClick={() => {
              onConfirm?.(kind === "branch" ? branchName.trim() : null);
              onClose?.();
            }}
          >
            {kind === "rollback" ? "确认回滚" : "创建分支"}
          </button>
        </div>
      </div>
    </div>
  );
}
