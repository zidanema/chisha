// D-093 S-02 RefineModal: handoff 保留, S-02 仅静态. S-03 接业务.
import { useEffect, useState } from "react";

const PRESETS = ["戒辣", "今天想喝汤", "不想吃肉", "少油少盐", "便宜点"];

export interface RefineModalProps {
  open: boolean;
  onClose?: () => void;
  onApply?: (text: string) => void;
}

export function RefineModal({ open, onClose, onApply }: RefineModalProps) {
  const [text, setText] = useState("");
  useEffect(() => {
    if (!open) setText("");
  }, [open]);

  if (!open) return null;
  return (
    <div className="modal-mask open" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>refine 这一顿</h3>
        <p>用一句话约束这一顿的推荐(不影响其他顿)。</p>
        <textarea
          autoFocus
          placeholder="例如:今天想吃清淡点的,带点汤水"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <div className="refine-modal-chips">
          {PRESETS.map((p) => (
            <button key={p} className="chip refine-modal-chip" onClick={() => setText(p)}>
              {p}
            </button>
          ))}
        </div>
        <div className="modal-actions">
          <button className="tbtn" onClick={onClose}>
            取消
          </button>
          <button
            className="tbtn primary"
            disabled={!text.trim()}
            onClick={() => {
              onApply?.(text.trim());
              onClose?.();
            }}
          >
            重推
          </button>
        </div>
      </div>
    </div>
  );
}
