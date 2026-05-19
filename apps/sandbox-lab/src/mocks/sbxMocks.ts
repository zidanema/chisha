// D-088 S-02: 从 chidiansha-sandbox/project/sandbox-lab/data.js 1:1 改 TS.
// 改动:
//   - ACTIVE_RULES.ttl 字段删除 (D-088 决议: refine 单 round, 不显示倒计时)
//   - TASTE 删除 color 字段 (APanel 内 TS map 决定 className)
// 其余字段与原型一致.

import type {
  ActiveRule,
  Decision,
  FatigueEntry,
  KeywordEntry,
  Meal,
  Rec,
  SessionMeta,
  TasteEntry,
} from "../types/sandbox";

export const SESSIONS: SessionMeta[] = [
  {
    id: "s_new_l3",
    name: "session-新打分",
    days: 7,
    seed: 42,
    profile: "profile@v2",
    origin: "真实快照",
    status: "running",
    lastUsed: "刚刚",
  },
  {
    id: "s_no_spicy",
    name: "session-戒辣7天",
    days: 7,
    seed: 17,
    profile: "profile@v1.3",
    origin: "空白",
    status: "done",
    lastUsed: "昨天",
  },
  {
    id: "s_cold",
    name: "session-冷启动测试",
    days: 14,
    seed: 5,
    profile: "profile@v2",
    origin: "空白",
    status: "done",
    lastUsed: "3 天前",
  },
];

// 0=D1午, 1=D1晚, 2=D2午, 3=D2晚, current=4 (D3午)
export const HISTORY: Meal[] = [
  {
    idx: 0,
    day: 1,
    slot: "午",
    state: "eat",
    dish: "川味小炒",
    score: 91,
    flags: [],
    altScores: [
      { name: "川味小炒", score: 91, picked: true },
      { name: "潮汕牛肉", score: 86 },
      { name: "寿司拼盘", score: 80 },
      { name: "越南河粉", score: 76 },
      { name: "茶餐厅", score: 72 },
    ],
  },
  {
    idx: 1,
    day: 1,
    slot: "晚",
    state: "eat",
    dish: "潮汕牛肉",
    score: 88,
    flags: [],
    altScores: [
      { name: "潮汕牛肉", score: 88, picked: true },
      { name: "湘菜小厨", score: 85 },
      { name: "寿司拼盘", score: 79 },
      { name: "炒河粉", score: 76 },
      { name: "韩式拌饭", score: 70 },
    ],
  },
  {
    idx: 2,
    day: 2,
    slot: "午",
    state: "skip",
    dish: "—",
    score: null,
    flags: [],
    altScores: [],
  },
  {
    idx: 3,
    day: 2,
    slot: "晚",
    state: "eat",
    dish: "寿司拼盘",
    score: 88,
    flags: ["refine", "conflict"],
    altScores: [
      { name: "麻辣烫", score: 92 },
      { name: "寿司拼盘", score: 88, picked: true },
      { name: "茶餐厅", score: 81 },
      { name: "越南河粉", score: 77 },
      { name: "韩式拌饭", score: 72 },
    ],
  },
];

export const CURRENT_RECS: Rec[] = [
  {
    rank: 1,
    name: "蓉香记",
    venue: "高新店",
    dishes: ["回锅肉", "蒜苗炒腊肉", "蛋花汤"],
    price: 38,
    l2: 0.85,
    l3: 92,
    boost: 7,
    intent: "不油",
    l1Hits: ["香", "家常"],
    explore: false,
    conflict: { rule: "戒辣", reason: "含辣 — 与 active refine 冲突" },
    meta: { eta: "12min", dist: "0.8km", protein: 42, oil: "2.4/5" },
    why: "川菜本周首次,锅气足,0.8km 最近",
  },
  {
    rank: 2,
    name: "海记潮汕牛肉",
    venue: "深圳湾店",
    dishes: ["吊龙伴", "嫩肉", "牛肉丸"],
    price: 62,
    l2: 0.78,
    l3: 88,
    boost: 5,
    intent: "蛋白足",
    l1Hits: ["鲜", "家常"],
    explore: false,
    conflict: null,
    meta: { eta: "18min", dist: "1.4km", protein: 55, oil: "1.8/5" },
    why: "蛋白 55g 充足,鲜+家常双命中",
  },
  {
    rank: 3,
    name: "西贡小馆",
    venue: "科技园店",
    dishes: ["招牌牛肉河粉", "炸春卷 2 个"],
    price: 32,
    l2: 0.71,
    l3: 84,
    boost: 4,
    intent: "清淡",
    l1Hits: ["不油", "带汤水"],
    explore: false,
    conflict: null,
    meta: { eta: "15min", dist: "1.1km", protein: 28, oil: "1.2/5" },
    why: "覆盖不油+带汤水,价低、距离近",
  },
  {
    rank: 4,
    name: "钱塘潮·精致江浙菜",
    venue: "高新店",
    dishes: ["杭椒煎牛肉 1 人份", "鸡汤石磨老豆腐", "腐皮鸡毛菜"],
    price: 81,
    l2: 0.83,
    l3: 84,
    boost: 1,
    intent: "蛋白足",
    l1Hits: ["鲜", "带汤水"],
    explore: true,
    conflict: null,
    meta: { eta: "15min", dist: "1.1km", protein: 50, oil: "2.3/5" },
    why: "江浙菜本周首次,鸡汤豆腐补汤水,1.1km 最近",
  },
  {
    rank: 5,
    name: "SaladPower 沙拉力",
    venue: "深圳湾店",
    dishes: ["鸡胸藜麦碗", "烤时蔬", "油醋汁"],
    price: 46,
    l2: 0.66,
    l3: 79,
    boost: 13,
    intent: "控油",
    l1Hits: ["不油", "蔬菜"],
    explore: true,
    conflict: null,
    meta: { eta: "28min", dist: "2.1km", protein: 52, oil: "1.3/5" },
    why: "本周新店探索,鸡胸 180g 蛋白足;口味契合偏低,吃两次再判断",
  },
];

export const LAST_DECISION: Decision = {
  when: "D2 晚",
  pick: "寿司拼盘",
  rank: 2,
  l3: 88,
  diff: [
    { kind: "add", field: "recent_dishes", value: "+ [寿司拼盘]" },
    { kind: "add", field: "fatigue.寿司", from: "—", to: "1" },
    { kind: "up", field: "taste.日", from: "0.15", to: "0.18", delta: "+0.03" },
    { kind: "ttl", field: 'refine "戒辣" TTL', from: "6", to: "5" },
  ],
  implications: [
    { field: "L2 日料类", text: "+0.03 倾向(下顿生效)" },
    { field: "fatigue.寿司", text: "下顿同菜折 0.95×" },
    { field: 'refine "戒辣"', text: "还剩 5 天有效" },
  ],
};

export const TASTE: TasteEntry[] = [
  { name: "川", v: 0.45, delta: 0.05 },
  { name: "粤", v: 0.28, delta: 0 },
  { name: "日", v: 0.18, delta: 0.03 },
  { name: "东南亚", v: 0.06, delta: 0 },
  { name: "西", v: 0.03, delta: -0.01 },
];

export const KEYWORDS: KeywordEntry[] = [
  { tag: "香", isNew: false },
  { tag: "家常", isNew: false },
  { tag: "不油", isNew: false },
  { tag: "汤水", isNew: true },
];

// D-088 决议: refine 单 round, ttl 字段省略
export const ACTIVE_RULES: ActiveRule[] = [
  {
    kind: "refine",
    label: "戒辣",
    since: "D1",
    conflict: "推荐 #1 川味小炒",
  },
];

export const BLACKLIST: ActiveRule[] = [
  { kind: "blacklist", label: "螺蛳粉", since: "—", reason: "D2 拒×2" },
];

export const RECENT: string[] = [
  "川味小炒",
  "潮汕牛肉",
  "(跳过)",
  "寿司拼盘",
];

export const FATIGUE: FatigueEntry[] = [
  { name: "川味小炒", count: 2, hot: true },
  { name: "潮汕牛肉", count: 1, hot: false },
  { name: "寿司拼盘", count: 1, hot: false },
];

export const CURRENT_IDX = 4;
export const TOTAL_MEALS = 14;


// ════════════════════════════════════════════════════════════════════════════
// S-03 helpers
// ════════════════════════════════════════════════════════════════════════════

import type { Clock } from "../types/sandbox";


function hashStr(s: string): number {
  let h = 0;
  for (const c of s) h = (h * 31 + c.charCodeAt(0)) | 0;
  return Math.abs(h);
}

/**
 * S-03: 推 idx + sessionId 派生新 5 条 mock recs (deterministic shuffle).
 * 修订 G: idx % 3 !== 0 时去掉 conflict (模拟"有时冲突有时无"视觉差).
 */
export function freshRecsForMeal(idx: number, sessionId: string): Rec[] {
  const seed = (idx * 1009 + hashStr(sessionId)) % 5;
  const rotated = [...CURRENT_RECS.slice(seed), ...CURRENT_RECS.slice(0, seed)];
  const stripConflict = idx % 3 !== 0;
  return rotated.map((r, i) => ({
    ...r,
    rank: i + 1,
    conflict: stripConflict ? null : r.conflict,
  }));
}

/**
 * S-03: 仿 S-06b build_decision mock 版. eat 后落 lastDecision.
 */
export function buildDecisionMock(rec: Rec, clock: Clock): Decision {
  return {
    when: `D${clock.day} ${clock.slot}`,
    pick: rec.dishes ? `${rec.name} · ${rec.dishes.join(" + ")}` : rec.name,
    rank: rec.rank,
    l3: rec.l3,
    diff: [
      { kind: "add", field: "recent_dishes", value: `+ [${rec.name}]` },
      { kind: "add", field: `fatigue.${rec.name}`, from: "—", to: "1" },
      { kind: "up", field: "taste.<context>", from: "0.30", to: "0.33", delta: "+0.03" },
    ],
    implications: [
      { field: "L2", text: "+0.03 倾向(下顿生效)" },
      { field: `fatigue.${rec.name}`, text: "下顿同菜折 0.95×" },
    ],
  };
}

/**
 * S-03: skip 路径 mock decision ("跳过未触发学习,下一顿系统状态不变").
 */
export function buildSkipDecisionMock(clock: Clock): Decision {
  return {
    when: `D${clock.day} ${clock.slot}`,
    pick: "(跳过)",
    rank: "—",
    l3: "—",
    diff: [],
    implications: [
      { field: "—", text: "跳过未触发学习,下一顿系统状态不变" },
    ],
  };
}

/**
 * S-03: 把 mock HISTORY (4 顿) 扩展到 totalMeals 顿, 给 done session 用.
 * 循环填模板 + idx/day/slot 正确, dish 后缀加 idx 防 fatigue 直观重复.
 */
export function expandHistoryForDoneSession(totalMeals: number): Meal[] {
  const out: Meal[] = [];
  for (let i = 0; i < totalMeals; i++) {
    const template = HISTORY[i % HISTORY.length];
    const day = Math.floor(i / 2) + 1;
    const slot: "午" | "晚" = i % 2 === 0 ? "午" : "晚";
    out.push({
      ...template,
      idx: i,
      day,
      slot,
      // 简单变 dish 名以体现 done session 多样性
      dish: template.state === "skip" ? "—" : `${template.dish}`,
    });
  }
  return out;
}

