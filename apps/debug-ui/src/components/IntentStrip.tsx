// IntentStrip — schema-driven 渲染 V2 RefineIntent 字段 + want/avoid added 高亮.
// 设计稿 (wa-refine.jsx) 视觉锁定; 字段集走 schema descriptor (Phase 2a 后端 GET
// /api/intent_schema), 未传 schema prop 时 fallback INTENT_SCHEMA 常量.
// 未知字段进 "other" 分组, 不挡 V2 schema 后续扩展.

import { INTENT_SCHEMA } from "../constants/intentSchema";
import type { IntentFieldDescriptor, RoundIntentV2, RoundRecord } from "../types/trace";

type Props = {
  round: RoundRecord;
  prevRound: RoundRecord | null;
  collapsed: boolean;
  setCollapsed: (v: boolean) => void;
  // Optional: backend-driven schema. 未传走 fallback constant.
  schema?: IntentFieldDescriptor[] | null;
};

// 沿 slot_path 取值. 路径不存在 → undefined.
function pickSlot(intent: RoundIntentV2 | null, path: string[]): unknown {
  if (!intent) return undefined;
  let cur: unknown = intent;
  for (const p of path) {
    if (cur && typeof cur === "object" && p in (cur as Record<string, unknown>)) {
      cur = (cur as Record<string, unknown>)[p];
    } else {
      return undefined;
    }
  }
  return cur;
}

function isEmpty(v: unknown): boolean {
  if (v === null || v === undefined || v === "" || v === false) return true;
  if (Array.isArray(v) && v.length === 0) return true;
  if (typeof v === "object" && Object.keys(v as object).length === 0) return true;
  return false;
}

function asArray(v: unknown): string[] {
  if (Array.isArray(v)) return v.filter((x): x is string => typeof x === "string");
  return [];
}

function renderScalar(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "string" || typeof v === "number") return String(v);
  // reference: 紧凑 JSON
  try { return JSON.stringify(v); } catch { return String(v); }
}

function FieldValue({ field, value, prevValue }: {
  field: IntentFieldDescriptor;
  value: unknown;
  prevValue: unknown;
}) {
  if (field.freeform) {
    if (isEmpty(value)) return <span className="empty">—</span>;
    return <>{String(value)}</>;
  }
  if (field.scalar) {
    if (isEmpty(value)) return <span className="empty">—</span>;
    const txt = renderScalar(value);
    const added = renderScalar(prevValue) !== txt;
    return <span className={`ich neutral ${added ? "added" : ""}`}>{txt}</span>;
  }
  const arr = asArray(value);
  if (arr.length === 0) return <span className="empty">—</span>;
  const prevArr = asArray(prevValue);
  return (
    <>
      {arr.map((v, i) => {
        const added = !prevArr.includes(v);
        return (
          <span key={i} className={`ich ${field.tone} ${added ? "added" : ""}`}>{v}</span>
        );
      })}
    </>
  );
}

export function IntentStrip({ round, prevRound, collapsed, setCollapsed, schema }: Props) {
  const intent = round.intent_v2;
  const prev = prevRound?.intent_v2 ?? null;
  const activeSchema = schema && schema.length > 0 ? schema : INTENT_SCHEMA;
  // 拆 freeform 单独放最下方
  const inlineFields = activeSchema.filter((f) => !f.freeform);
  const freeformFields = activeSchema.filter((f) => f.freeform);

  return (
    <div className={`intent-strip ${collapsed ? "collapsed" : ""}`}>
      <div className="head">
        <span className="lbl">intent</span>
        <span className="round">{round.id} · {round.label}</span>
        {round.user_input ? (
          <span className="raw">
            <span className="q">"</span>{round.user_input}<span className="q">"</span>
          </span>
        ) : (
          <span className="raw">
            <span className="q">// </span>首轮 · 来自 profile, 无 refine 输入
          </span>
        )}
        <button className="toggle-btn" onClick={() => setCollapsed(!collapsed)}>
          {collapsed ? "展开 ▾" : "收起 ▴"}
        </button>
      </div>
      {!collapsed && (
        <div className="intent-fields">
          {inlineFields.map((f) => (
            <div className="intent-field" key={f.key}>
              <div className="k">{f.label}</div>
              <div className="v">
                <FieldValue
                  field={f}
                  value={pickSlot(intent, f.slot_path)}
                  prevValue={pickSlot(prev, f.slot_path)}
                />
              </div>
            </div>
          ))}
          {freeformFields.map((f) => (
            <div className="intent-field freeform" key={f.key}>
              <div className="k">{f.label}</div>
              <div className="v">
                <FieldValue
                  field={f}
                  value={pickSlot(intent, f.slot_path)}
                  prevValue={pickSlot(prev, f.slot_path)}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
