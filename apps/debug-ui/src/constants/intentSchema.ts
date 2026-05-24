// Intent schema descriptor — drives IntentStrip 渲染.
// Phase 1: 写死字段 (mock 后端). Phase 2a: 后端 GET /api/intent_schema 替代.
// 字段集与 chisha/refine_intent_v2.py RefineIntentV2 schema 一一对应.
//
// 后续扩 V2 schema 字段时, **优先方案**: 在后端 intent_schema endpoint 加条目,
// 不动这里; 这里仅作为 backend 不可用时的 fallback.

import type { IntentFieldDescriptor } from "../types/trace";

export const INTENT_SCHEMA: IntentFieldDescriptor[] = [
  // redirect 块 — 重定向候选 (L1 召回参数改写)
  { key: "redirect.cuisine_want", label: "菜系想", tone: "want", group: "redirect",
    slot_path: ["redirect", "cuisine_want"] },
  { key: "redirect.cuisine_avoid", label: "菜系不想", tone: "avoid", group: "redirect",
    slot_path: ["redirect", "cuisine_avoid"] },
  { key: "redirect.cuisine_candidates_expanded", label: "菜系扩展", tone: "want", group: "redirect",
    slot_path: ["redirect", "cuisine_candidates_expanded"] },
  { key: "redirect.ingredient_want", label: "食材想", tone: "want", group: "redirect",
    slot_path: ["redirect", "ingredient_want"] },
  { key: "redirect.ingredient_avoid", label: "食材不想", tone: "avoid", group: "redirect",
    slot_path: ["redirect", "ingredient_avoid"] },
  { key: "redirect.brand_avoid", label: "品牌拒绝", tone: "avoid", group: "redirect",
    slot_path: ["redirect", "brand_avoid"] },
  { key: "redirect.cooking_method_avoid", label: "烹饪方式拒绝", tone: "avoid", group: "redirect",
    slot_path: ["redirect", "cooking_method_avoid"] },
  // D-094.1: staple_want / staple_avoid (主食偏好自由字符串)
  { key: "redirect.staple_want", label: "主食想", tone: "want", group: "redirect",
    slot_path: ["redirect", "staple_want"] },
  { key: "redirect.staple_avoid", label: "主食不想", tone: "avoid", group: "redirect",
    slot_path: ["redirect", "staple_avoid"] },
  // constrain 块 — 单值约束 (L1/L2 硬过滤 / 软分)
  // D-094.1: oil 枚举扩 {low,normal,high}; 加 wants_soup (bool) + price_band (模糊兜底)
  { key: "constrain.oil", label: "油控", tone: "neutral", group: "constrain",
    slot_path: ["constrain", "oil"], scalar: true },
  { key: "constrain.price_max", label: "价格上限", tone: "neutral", group: "constrain",
    slot_path: ["constrain", "price_max"], scalar: true },
  { key: "constrain.price_band", label: "价格档位", tone: "neutral", group: "constrain",
    slot_path: ["constrain", "price_band"], scalar: true },
  { key: "constrain.wants_soup", label: "想喝汤", tone: "neutral", group: "constrain",
    slot_path: ["constrain", "wants_soup"], scalar: true },
  // meta 块 — 引用 / reject_previous / 自述
  { key: "reference", label: "引用上一轮", tone: "neutral", group: "meta",
    slot_path: ["reference"], scalar: true },
  { key: "reject_previous", label: "否决前轮", tone: "neutral", group: "meta",
    slot_path: ["reject_previous"], scalar: true },
  { key: "raw_understanding", label: "LLM 自述理解", tone: "neutral", group: "meta",
    slot_path: ["raw_understanding"], freeform: true },
  { key: "raw_text", label: "原始输入", tone: "neutral", group: "meta",
    slot_path: ["raw_text"], freeform: true },
];
