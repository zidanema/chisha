// D-088 S-02 sandbox-lab 类型定义
// 严格对齐 chidiansha-sandbox/project/sandbox-lab/HANDOFF_PROMPT.md §数据契约 (88-140 行).
// HandoffXxx 类型 = 后端契约严格版; Xxx (无前缀) = sandbox-lab 视图扩展版.

export type Theme = "light" | "dark";

export const ACCENT_VALUES = [
  "#6366f1",
  "#059669",
  "#e11d48",
  "#d97706",
] as const;
export type Accent = (typeof ACCENT_VALUES)[number];

export interface SessionMeta {
  id: string;
  name: string;
  days: number;
  seed: number;
  profile: string;
  origin: "真实快照" | "空白";
  status: "running" | "done";
  lastUsed: string;
}

export type MealState = "eat" | "skip" | "current" | "future";

// handoff §104-112 严格只列两路
export type HandoffMealFlag = "conflict" | "refine";
// sandbox-lab 视图扩展 (timeline cell-badges + mock 用)
export type SbxMealFlag = "swap" | "event";
export type MealFlag = HandoffMealFlag | SbxMealFlag;

export interface AltScore {
  name: string;
  score: number;
  picked?: boolean;
}

// HandoffMeal: 严格 handoff 字段, S-08 adapter 边界校验用
export interface HandoffMeal {
  idx: number;
  day: number;
  slot: "午" | "晚";
  state: MealState;
  dish: string;
  score: number | null;
  flags: HandoffMealFlag[];
  altScores: AltScore[];
}

// Meal: sandbox-lab view-model, flags 联合允许 sandbox 扩展
export interface Meal extends Omit<HandoffMeal, "flags"> {
  flags: MealFlag[];
}

export interface RecMeta {
  eta: string;
  dist: string;
  protein: number;
  oil: string;
}

export interface ConflictInfo {
  rule: string;
  reason: string;
}

export interface Rec {
  rank: number;
  name: string;
  venue: string;
  dishes?: string[];
  price: number;
  l2: number;
  l3: number;
  boost: number;
  intent: string;
  l1Hits: string[];
  explore?: boolean;
  conflict?: ConflictInfo | null;
  meta: RecMeta;
  why: string;
}

// handoff §132-138 完整 5 路 (含 rm); 原型 DiffRow 没 rm 分支 -> S-02 DPanel
// 对 "rm" 走 fallthrough 同 ttl 形态, types 仍保留全集
export type HandoffDiffKind = "add" | "rm" | "up" | "dn" | "ttl";
export type DiffKind = HandoffDiffKind;

export interface DiffEntry {
  kind: DiffKind;
  field: string;
  from?: string;
  to?: string;
  value?: string;
  delta?: string;
}

export interface Implication {
  field: string;
  text: string;
}

export interface Decision {
  when: string;
  pick: string;
  rank: number | "—";
  l3: number | "—";
  diff: DiffEntry[];
  implications: Implication[];
}

export interface ActiveRule {
  kind: "refine" | "blacklist";
  label: string;
  since: string;
  // ttl 字段保留 optional (后端可能传, 但 S-02 D-088 决议: refine 单 round, 不显示倒计时)
  ttl?: number;
  conflict?: string;
  reason?: string;
}

// 不带 color 字段 (Codex Q3 iter2): APanel 用 TS map 决定 className
export interface TasteEntry {
  name: string;
  v: number;
  delta: number;
}

export interface KeywordEntry {
  tag: string;
  isNew: boolean;
}

export interface FatigueEntry {
  name: string;
  count: number;
  hot: boolean;
}

export interface BannerEntry {
  id: string;
  level: "warn" | "danger" | "review" | "info";
  title: string;
  detail: string;
  dismissable: boolean;
}

export interface Clock {
  idx: number;
  day: number;
  slot: "午" | "晚";
  total: number;
}

export interface Tweaks {
  timelineVariant: "bars" | "calendar";
  rightDensity: 0 | 1;
  showDebugLayer: boolean;
  accent: Accent;
  theme: Theme;
}

export type ConfirmKind = "rollback" | "branch";

// FullSnapshot stub: S-02 不直接使用 (mock 喂分段数据), 留给 S-06a/S-08 adapter.
export interface FullSnapshot {
  meta: SessionMeta;
  clock: Clock;
  history: Meal[];
  currentRecs: Rec[];
  lastDecision: Decision | null;
  activeRules: { refine: ActiveRule[]; blacklist: ActiveRule[] };
  taste: TasteEntry[];
  keywords: KeywordEntry[];
  recent: string[];
  fatigue: FatigueEntry[];
}
