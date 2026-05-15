// mockApi.ts — pure browser mock for /api/* (D-049 dev/preview).
// Ports the v0 prototype data.js exactly, including pool, scoring, session
// store, and the simulated 900ms latency for recommend/refine (real backend
// is 15-60s — UI must still use skeleton, see DESIGN_NOTES §4 加载态).

import type {
  Candidate,
  FeedbackPayload,
  FeedbackRecord,
  FeedbackSession,
  HistoryItem,
  MealType,
  Mood,
  Profile,
  RecentFeedback,
  RecommendResponse,
  SkipReason,
  UnfedSession,
} from "./types";
import type { ChishaApi } from "./api";
import { PROFILE_DEFAULTS } from "./profileDefaults";

type PoolCandidate = Omit<Candidate, "rank"> & {
  mood_affinity: Partial<Record<Mood, number>>;
};

const POOL: PoolCandidate[] = [
  {
    id: "c_001",
    is_explore: false,
    summary: "S 级招牌烤鸡+牛肉套餐 + 清炒油菜芯 每份/90g + 低 GI 主食：黑米饭一份",
    restaurant: { id: "r_222", name: "Super Model 超模厨房（深圳科技园店）", distance_m: 3500, eta_min: 30 },
    dishes: [
      { dish_id: "d_222_005", canonical_name: "S 级招牌烤鸡+牛肉套餐", price: 32.8, main_ingredient_type: "白肉", oil_level: 3 },
      { dish_id: "d_222_026", canonical_name: "清炒油菜芯 每份/90g", price: 6.0, main_ingredient_type: "纯素", oil_level: 2 },
      { dish_id: "d_222_028", canonical_name: "低 GI 主食：黑米饭一份", price: 3.0, main_ingredient_type: "主食", oil_level: 1 },
    ],
    total_price: 41.8, vegetable_dish_count: 1, estimated_total_oil: 2.0, estimated_total_protein_g: 45,
    score: 2.879, fit_score: 0.82, taste_match: 0.60,
    reason_one_line: "Super Model 多变体中蔬菜最实（清炒油菜芯），烤鸡+牛肉蛋白足，结构最符合哈佛餐盘",
    health_flags: { veg_ok: true, protein_ok: true, oil_ok: true, processed_meat: false, sweet_sauce: false, wetness: false },
    risk_flags: [],
    mood_affinity: { neutral: 1, want_clean: 1, want_light: 0.6 },
  },
  {
    id: "c_002",
    is_explore: false,
    summary: "酸菜黑鱼片营养套餐 + 丝瓜闷土鸡蛋 + 黑米饭",
    restaurant: { id: "r_018", name: "醉湘楼·家宴（南山店）", distance_m: 4100, eta_min: 35 },
    dishes: [
      { dish_id: "d_018_003", canonical_name: "酸菜黑鱼片营养套餐", price: 24.8, main_ingredient_type: "海鲜", oil_level: 3 },
      { dish_id: "d_018_032", canonical_name: "丝瓜闷土鸡蛋", price: 29.9, main_ingredient_type: "蛋", oil_level: 3 },
      { dish_id: "d_018_075", canonical_name: "黑米饭", price: 3.5, main_ingredient_type: "主食", oil_level: 1 },
    ],
    total_price: 58.2, vegetable_dish_count: 1, estimated_total_oil: 2.3, estimated_total_protein_g: 45,
    score: 2.887, fit_score: 0.79, taste_match: 0.75,
    reason_one_line: "酸菜黑鱼+丝瓜蛋+黑米饭，湘菜风格命中你口味，比 Super Model 多汤水和蔬菜层次",
    health_flags: { veg_ok: true, protein_ok: true, oil_ok: true, processed_meat: false, sweet_sauce: false, wetness: true },
    risk_flags: [],
    mood_affinity: { neutral: 1, want_soup: 0.9, want_indulgent: 0.6 },
  },
  {
    id: "c_003",
    is_explore: false,
    summary: "双拼鲜牛腩牛杂单人煲 + 招牌鲜牛杂单人煲 + 萝卜",
    restaurant: { id: "r_077", name: "粤牛·化州剪牛腩（牛杂煲·科技园店）", distance_m: 2100, eta_min: 15 },
    dishes: [
      { dish_id: "d_077_001", canonical_name: "双拼鲜牛腩牛杂单人煲", price: 24.0, main_ingredient_type: "红肉", oil_level: 2 },
      { dish_id: "d_077_002", canonical_name: "招牌鲜牛杂单人煲", price: 22.4, main_ingredient_type: "红肉", oil_level: 2 },
      { dish_id: "d_077_010", canonical_name: "萝卜", price: 4.0, main_ingredient_type: "纯素", oil_level: 1 },
    ],
    total_price: 50.4, vegetable_dish_count: 1, estimated_total_oil: 2.3, estimated_total_protein_g: 50,
    score: 2.71, fit_score: 0.88, taste_match: 0.82,
    reason_one_line: "牛腩牛杂炖煲带汤，'解馋'心情首选，比清粥类满足感高两档",
    health_flags: { veg_ok: true, protein_ok: true, oil_ok: true, processed_meat: false, sweet_sauce: false, wetness: true },
    risk_flags: [],
    mood_affinity: { want_indulgent: 1, want_soup: 0.9, neutral: 0.7 },
  },
  {
    id: "c_004",
    is_explore: true,
    summary: "杭椒煎牛肉 1 人份 + 鸡汤石磨老豆腐 1 人份 + 腐皮鸡毛菜 1 人份",
    restaurant: { id: "r_182", name: "钱塘潮·精致江浙菜（高新店）", distance_m: 1100, eta_min: 15 },
    dishes: [
      { dish_id: "d_182_009", canonical_name: "杭椒煎牛肉 1 人份", price: 39.0, main_ingredient_type: "红肉", oil_level: 3 },
      { dish_id: "d_182_010", canonical_name: "鸡汤石磨老豆腐 1 人份", price: 19.0, main_ingredient_type: "豆制品", oil_level: 2 },
      { dish_id: "d_182_013", canonical_name: "腐皮鸡毛菜 1 人份", price: 23.0, main_ingredient_type: "纯素", oil_level: 2 },
    ],
    total_price: 81.0, vegetable_dish_count: 1, estimated_total_oil: 2.3, estimated_total_protein_g: 50,
    score: 2.146, fit_score: 0.64, taste_match: 0.78,
    reason_one_line: "江浙菜本周首次，杭椒煎牛肉辣1+锅气，鸡汤豆腐补汤水，1.1km 最近",
    health_flags: { veg_ok: true, protein_ok: true, oil_ok: true, processed_meat: false, sweet_sauce: false, wetness: true },
    risk_flags: [],
    mood_affinity: { neutral: 0.7, want_indulgent: 0.7 },
  },
  {
    id: "c_005",
    is_explore: true,
    summary: "酸辣椒炒土猪肉 + 基地蔬菜-应季特惠 + 自制酸腌菜炒小笋+米饭 + 自制篙子粑粑",
    restaurant: { id: "r_191", name: "湖南老灶台（科兴店）", distance_m: 2400, eta_min: 27 },
    dishes: [
      { dish_id: "d_191_014", canonical_name: "酸辣椒炒土猪肉", price: 58.0, main_ingredient_type: "红肉", oil_level: 3 },
      { dish_id: "d_191_003", canonical_name: "基地蔬菜-应季特惠 一人份", price: 6.0, main_ingredient_type: "纯素", oil_level: 2 },
      { dish_id: "d_191_008", canonical_name: "自制酸腌菜炒小笋+米饭 单人份", price: 43.25, main_ingredient_type: "纯素", oil_level: 3 },
      { dish_id: "d_191_049", canonical_name: "自制篙子粑粑", price: 22.0, main_ingredient_type: "主食", oil_level: 1 },
    ],
    total_price: 129.2, vegetable_dish_count: 2, estimated_total_oil: 2.2, estimated_total_protein_g: 40,
    score: 1.962, fit_score: 0.58, taste_match: 0.88,
    reason_one_line: "酸辣椒炒土猪肉是你口味描述最直接命中；过去妥协清淡太久，本次探索一次重口",
    health_flags: { veg_ok: true, protein_ok: true, oil_ok: true, processed_meat: false, sweet_sauce: false, wetness: false },
    risk_flags: ["价格偏高¥129", "距离较远"],
    mood_affinity: { want_indulgent: 1, neutral: 0.5 },
  },
  {
    id: "c_006",
    is_explore: false,
    summary: "番茄滑蛋牛肉饭 + 凉拌青瓜 + 紫菜蛋花汤",
    restaurant: { id: "r_055", name: "霸碗盖码饭（粤海店）", distance_m: 1100, eta_min: 22 },
    dishes: [
      { dish_id: "d_055_001", canonical_name: "番茄滑蛋牛肉饭", price: 26.0, main_ingredient_type: "红肉", oil_level: 3 },
      { dish_id: "d_055_011", canonical_name: "凉拌青瓜", price: 6.0, main_ingredient_type: "纯素", oil_level: 1 },
      { dish_id: "d_055_022", canonical_name: "紫菜蛋花汤", price: 8.0, main_ingredient_type: "蛋", oil_level: 1 },
    ],
    total_price: 40.0, vegetable_dish_count: 1, estimated_total_oil: 2.1, estimated_total_protein_g: 38,
    score: 2.30, fit_score: 0.76, taste_match: 0.70,
    reason_one_line: "霸碗番茄滑蛋这家做得清爽，蔬菜分量小但配冷拌青瓜补一下，22min 最快到",
    health_flags: { veg_ok: true, protein_ok: true, oil_ok: true, processed_meat: false, sweet_sauce: false, wetness: true },
    risk_flags: [],
    mood_affinity: { neutral: 0.9, want_light: 0.7, want_soup: 0.5 },
  },
  {
    id: "c_007",
    is_explore: false,
    summary: "汽锅鸡套餐 + 凉拌折耳根 + 玫瑰花饭",
    restaurant: { id: "r_104", name: "云海肴·云南菜（深圳湾店）", distance_m: 2000, eta_min: 31 },
    dishes: [
      { dish_id: "d_104_001", canonical_name: "汽锅鸡套餐", price: 36.0, main_ingredient_type: "白肉", oil_level: 1 },
      { dish_id: "d_104_007", canonical_name: "凉拌折耳根", price: 12.0, main_ingredient_type: "纯素", oil_level: 1 },
      { dish_id: "d_104_015", canonical_name: "玫瑰花饭", price: 6.0, main_ingredient_type: "主食", oil_level: 1 },
    ],
    total_price: 54.0, vegetable_dish_count: 1, estimated_total_oil: 1.3, estimated_total_protein_g: 42,
    score: 2.41, fit_score: 0.78, taste_match: 0.62,
    reason_one_line: "汽锅清蒸法油最低，'清淡'心情顶配。折耳根有 4 星记录",
    health_flags: { veg_ok: true, protein_ok: true, oil_ok: true, processed_meat: false, sweet_sauce: false, wetness: true },
    risk_flags: [],
    mood_affinity: { want_clean: 1, want_light: 0.9, neutral: 0.7 },
  },
  {
    id: "c_008",
    is_explore: false,
    summary: "水煮牛肉(微辣) + 蒜蓉空心菜 + 白米饭",
    restaurant: { id: "r_133", name: "蜀地源·川菜（科技园店）", distance_m: 1400, eta_min: 27 },
    dishes: [
      { dish_id: "d_133_002", canonical_name: "水煮牛肉(微辣)", price: 42.0, main_ingredient_type: "红肉", oil_level: 4 },
      { dish_id: "d_133_010", canonical_name: "蒜蓉空心菜", price: 14.0, main_ingredient_type: "纯素", oil_level: 3 },
      { dish_id: "d_133_020", canonical_name: "白米饭", price: 3.0, main_ingredient_type: "主食", oil_level: 1 },
    ],
    total_price: 59.0, vegetable_dish_count: 1, estimated_total_oil: 3.4, estimated_total_protein_g: 48,
    score: 2.32, fit_score: 0.71, taste_match: 0.86,
    reason_one_line: "水煮可备注少红油，蛋白和辣度都顶到位",
    health_flags: { veg_ok: true, protein_ok: true, oil_ok: false, processed_meat: false, sweet_sauce: false, wetness: true },
    risk_flags: ["油偏高 3.4/5"],
    mood_affinity: { want_indulgent: 0.95, neutral: 0.6 },
  },
  {
    id: "c_009",
    is_explore: false,
    summary: "三文鱼牛油果碗 + 羽衣甘蓝沙拉 + 藜麦",
    restaurant: { id: "r_211", name: "Wagas (后海店)", distance_m: 2400, eta_min: 35 },
    dishes: [
      { dish_id: "d_211_001", canonical_name: "三文鱼牛油果碗", price: 52.0, main_ingredient_type: "海鲜", oil_level: 2 },
      { dish_id: "d_211_005", canonical_name: "羽衣甘蓝沙拉", price: 22.0, main_ingredient_type: "纯素", oil_level: 1 },
      { dish_id: "d_211_007", canonical_name: "藜麦", price: 8.0, main_ingredient_type: "主食", oil_level: 1 },
    ],
    total_price: 82.0, vegetable_dish_count: 1, estimated_total_oil: 1.4, estimated_total_protein_g: 46,
    score: 2.18, fit_score: 0.69, taste_match: 0.55,
    reason_one_line: "Omega-3 + 慢碳，下午精神好；口味契合偏低，仅在'轻食'心情下推",
    health_flags: { veg_ok: true, protein_ok: true, oil_ok: true, processed_meat: false, sweet_sauce: false, wetness: false },
    risk_flags: ["价格偏高 ¥82"],
    mood_affinity: { want_light: 1, want_clean: 0.8 },
  },
  {
    id: "c_010",
    is_explore: true,
    summary: "鸡胸藜麦碗 + 烤时蔬 + 油醋汁",
    restaurant: { id: "r_244", name: "SaladPower 沙拉力（深圳湾店）", distance_m: 2100, eta_min: 28 },
    dishes: [
      { dish_id: "d_244_001", canonical_name: "鸡胸藜麦碗", price: 32.0, main_ingredient_type: "白肉", oil_level: 1 },
      { dish_id: "d_244_005", canonical_name: "烤时蔬", price: 14.0, main_ingredient_type: "纯素", oil_level: 2 },
      { dish_id: "d_244_009", canonical_name: "油醋汁", price: 0.0, main_ingredient_type: "纯素", oil_level: 1 },
    ],
    total_price: 46.0, vegetable_dish_count: 1, estimated_total_oil: 1.3, estimated_total_protein_g: 52,
    score: 2.05, fit_score: 0.62, taste_match: 0.52,
    reason_one_line: "本周新店探索。鸡胸 180g，蛋白足；口味契合偏低，吃过两次再判断",
    health_flags: { veg_ok: true, protein_ok: true, oil_ok: true, processed_meat: false, sweet_sauce: false, wetness: false },
    risk_flags: [],
    mood_affinity: { want_light: 1, want_clean: 0.7 },
  },
  {
    id: "c_011",
    is_explore: false,
    summary: "招牌草本汤·番茄牛腩面 + 蔬菜小食",
    restaurant: { id: "r_167", name: "和府捞面（海岸城店）", distance_m: 1500, eta_min: 26 },
    dishes: [
      { dish_id: "d_167_001", canonical_name: "招牌草本汤·番茄牛腩面", price: 36.0, main_ingredient_type: "红肉", oil_level: 3 },
      { dish_id: "d_167_005", canonical_name: "蔬菜小食", price: 12.0, main_ingredient_type: "纯素", oil_level: 2 },
    ],
    total_price: 48.0, vegetable_dish_count: 1, estimated_total_oil: 2.5, estimated_total_protein_g: 32,
    score: 2.01, fit_score: 0.66, taste_match: 0.80,
    reason_one_line: "汤面碳水偏高、蔬菜偏少，但你说想吃带汤水的就只能选它",
    health_flags: { veg_ok: true, protein_ok: true, oil_ok: true, processed_meat: false, sweet_sauce: false, wetness: true },
    risk_flags: [],
    mood_affinity: { want_soup: 1, neutral: 0.5 },
  },
  {
    id: "c_012",
    is_explore: false,
    summary: "豉汁蒸滑鸡 + 白灼菜心 + 白米饭",
    restaurant: { id: "r_088", name: "粤小厨·港式茶餐厅（粤海店）", distance_m: 900, eta_min: 22 },
    dishes: [
      { dish_id: "d_088_001", canonical_name: "豉汁蒸滑鸡", price: 28.0, main_ingredient_type: "白肉", oil_level: 2 },
      { dish_id: "d_088_005", canonical_name: "白灼菜心", price: 14.0, main_ingredient_type: "纯素", oil_level: 1 },
      { dish_id: "d_088_010", canonical_name: "白米饭", price: 3.0, main_ingredient_type: "主食", oil_level: 1 },
    ],
    total_price: 45.0, vegetable_dish_count: 1, estimated_total_oil: 1.4, estimated_total_protein_g: 42,
    score: 2.45, fit_score: 0.81, taste_match: 0.74,
    reason_one_line: "粤式蒸菜油最少，菜心白灼无负担。最近的一家，22min 到",
    health_flags: { veg_ok: true, protein_ok: true, oil_ok: true, processed_meat: false, sweet_sauce: false, wetness: false },
    risk_flags: [],
    mood_affinity: { want_clean: 0.9, neutral: 0.85 },
  },
  {
    id: "c_013",
    is_explore: false,
    summary: "葱姜鸡腿排饭(去皮) + 凉拌菠菜 + 杂粮饭",
    restaurant: { id: "r_209", name: "鸡先生·健康简餐", distance_m: 1800, eta_min: 24 },
    dishes: [
      { dish_id: "d_209_001", canonical_name: "葱姜鸡腿排饭(去皮)", price: 28.0, main_ingredient_type: "白肉", oil_level: 2 },
      { dish_id: "d_209_007", canonical_name: "凉拌菠菜", price: 10.0, main_ingredient_type: "纯素", oil_level: 1 },
      { dish_id: "d_209_010", canonical_name: "杂粮饭", price: 4.0, main_ingredient_type: "主食", oil_level: 1 },
    ],
    total_price: 42.0, vegetable_dish_count: 1, estimated_total_oil: 1.4, estimated_total_protein_g: 40,
    score: 2.20, fit_score: 0.74, taste_match: 0.60,
    reason_one_line: "鸡腿去皮做法，蛋白稳，杂粮饭升级碳水",
    health_flags: { veg_ok: true, protein_ok: true, oil_ok: true, processed_meat: false, sweet_sauce: false, wetness: false },
    risk_flags: [],
    mood_affinity: { low_carb: 0.6, want_clean: 0.85, neutral: 0.75 },
  },
];

const SIM_MS = 900;
const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

interface AcceptedItem {
  session_id: string;
  accepted_rank: number;
  accepted_at: string;
  // V1.1 (D-058): snooze = 软关闭 24h (banner 不催, inbox 仍在);
  // stop = 永久 (banner + inbox 都隐藏, history 仍在)
  snoozed_until: number | null;
  stopped: boolean;
}

const STORE = {
  sessions: {} as Record<string, RecommendResponse>,
  acceptedQueue: [] as AcceptedItem[],
  feedbacks: {} as Record<string, FeedbackRecord>,
  profile: PROFILE_DEFAULTS as Profile,
};

function buildResponse(args: {
  meal_type: MealType;
  mood: Mood;
  refine_input: string | null;
  round: number;
  prevSession?: string;
  picks: PoolCandidate[];
}): RecommendResponse {
  const { meal_type, mood, refine_input, round, prevSession, picks } = args;
  const id = prevSession || `2026${String(Math.floor(Math.random() * 1e6)).padStart(6, "0")}_${meal_type}`;
  return {
    session_id: id,
    meal_type,
    zone: "shenzhen-bay",
    round,
    version: "v2",
    generated_at: new Date().toISOString(),
    context: {
      meal_type,
      zone: "shenzhen-bay",
      now: new Date().toISOString().replace("Z", ""),
      weekday: new Date().getDay(),
      last_meal: null,
      recent_3d_cuisines: {},
      recent_3d_ingredients: {},
      last_feedback: null,
      daily_mood: mood,
      refine_input,
    },
    stats: {
      n_dishes_total: 11123,
      n_combos_recalled: 2467,
      n_combos_after_score: 2467,
      n_returned: picks.length,
    },
    candidates: picks.map((c, i) => ({ ...c, rank: i + 1 })),
  };
}

function pickFive(args: { mood?: Mood; excludeIds?: string[]; round?: number }): PoolCandidate[] {
  const { mood = "neutral", excludeIds = [], round = 1 } = args;
  const m = mood;
  const scored = POOL.filter((c) => !excludeIds.includes(c.id))
    .map((c) => {
      const affinity = c.mood_affinity?.[m] ?? (m === "neutral" ? 0.5 : 0.1);
      const jitter = (Math.sin((round + 1) * (c.id.length + 7)) + 1) * 0.05;
      return { c, final: c.score * 0.6 + affinity * 1.2 + jitter };
    })
    .sort((a, b) => b.final - a.final)
    .map((x) => x.c);

  const exploit = scored.filter((c) => !c.is_explore).slice(0, 3);
  const explore = scored.filter((c) => c.is_explore).slice(0, 2);
  const picks = [...exploit, ...explore].slice(0, 5);
  while (picks.length < 5) {
    const fill = scored.find((c) => !picks.includes(c));
    if (!fill) break;
    picks.push(fill);
  }
  return picks;
}

function storeSession(resp: RecommendResponse) {
  STORE.sessions[resp.session_id] = resp;
}
function markAccepted(session_id: string, accepted_rank: number) {
  STORE.acceptedQueue = STORE.acceptedQueue.filter((x) => x.session_id !== session_id);
  STORE.acceptedQueue.push({
    session_id,
    accepted_rank,
    accepted_at: new Date().toISOString(),
    snoozed_until: null,
    stopped: false,
  });
}
function snoozeItem(session_id: string) {
  const item = STORE.acceptedQueue.find((x) => x.session_id === session_id);
  if (item) item.snoozed_until = Date.now() + 24 * 3600 * 1000;
}
function stopItem(session_id: string) {
  const item = STORE.acceptedQueue.find((x) => x.session_id === session_id);
  if (item) item.stopped = true;
}
function unfedAll(): AcceptedItem[] {
  // 未反馈 + 未 stop。inbox 三段全在这里；snoozed 由调用方按 snoozed_until 分组
  return [...STORE.acceptedQueue]
    .filter((x) => !STORE.feedbacks[x.session_id] && !x.stopped)
    .sort((a, b) => new Date(b.accepted_at).getTime() - new Date(a.accepted_at).getTime());
}
function isSnoozed(item: AcceptedItem): boolean {
  return !!(item.snoozed_until && item.snoozed_until > Date.now());
}
function shapeUnfed(item: AcceptedItem): UnfedSession {
  const resp = STORE.sessions[item.session_id];
  const cand = resp?.candidates?.find((c: Candidate) => c.rank === item.accepted_rank);
  return {
    session_id: item.session_id,
    meal_type: resp?.meal_type || "lunch",
    restaurant_name: cand?.restaurant?.name || "（未知）",
    summary: cand?.summary || "",
    accepted_at: item.accepted_at,
    snoozed: isSnoozed(item),
    stopped: !!item.stopped,
  };
}

export const api: ChishaApi = {
  async recommend(
    { meal_type = "lunch", mood = "neutral" }: { meal_type?: MealType; mood?: Mood } = {}
  ) {
    await sleep(SIM_MS);
    const picks = pickFive({ mood, round: 1 });
    const resp = buildResponse({ meal_type, mood, refine_input: null, round: 1, picks });
    storeSession(resp);
    return resp;
  },
  async refine({
    session_id,
    refine_text,
    meal_type = "lunch",
    mood = "neutral",
    round = 2,
    excludeIds = [],
  }: {
    session_id: string;
    refine_text: string;
    meal_type?: MealType;
    mood?: Mood;
    round?: number;
    excludeIds?: string[];
  }) {
    await sleep(SIM_MS);
    const picks = pickFive({ mood, excludeIds, round });
    const resp = buildResponse({ meal_type, mood, refine_input: refine_text, round, prevSession: session_id, picks });
    storeSession(resp);
    return resp;
  },
  async accept({ session_id, candidate_rank, candidate }) {
    await sleep(120);
    markAccepted(session_id, candidate_rank);
    const slug = encodeURIComponent(candidate?.restaurant?.name || "");
    return { deeplink_url: `dianping://shopdesc?shopId=${candidate?.restaurant?.id}&name=${slug}` };
  },
  async inbox({ include_snoozed = true } = {}): Promise<{ items: UnfedSession[] }> {
    await sleep(60);
    const list = unfedAll();
    const filtered = include_snoozed ? list : list.filter((x) => !isSnoozed(x));
    return { items: filtered.map(shapeUnfed) };
  },
  async snoozeFeedback({ session_id }: { session_id: string }) {
    await sleep(60);
    snoozeItem(session_id);
    return { ok: true };
  },
  async stopFeedback({ session_id }: { session_id: string }) {
    await sleep(60);
    stopItem(session_id);
    return { ok: true };
  },
  async recentFeedbacks({ limit = 6 } = {}): Promise<{ items: RecentFeedback[] }> {
    await sleep(60);
    const items: RecentFeedback[] = Object.entries(STORE.feedbacks)
      .map(([sid, fb]) => {
        const resp = STORE.sessions[sid];
        const queued = STORE.acceptedQueue.find((x) => x.session_id === sid);
        const cand =
          fb.accepted_rank != null && resp
            ? resp.candidates.find((c: Candidate) => c.rank === fb.accepted_rank)
            : null;
        return {
          session_id: sid,
          meal_type: resp?.meal_type || "lunch",
          restaurant_name: cand?.restaurant?.name || "（都没吃）",
          accepted_at: queued?.accepted_at || resp?.generated_at || fb.submitted_at,
          submitted_at: fb.submitted_at,
          rating: fb.rating,
          accepted_rank: fb.accepted_rank,
        };
      })
      .sort((a, b) => new Date(b.submitted_at).getTime() - new Date(a.submitted_at).getTime())
      .slice(0, limit);
    return { items };
  },
  async getFeedbackSession({ session_id }): Promise<FeedbackSession> {
    await sleep(120);
    let resp = STORE.sessions[session_id];
    const queued = STORE.acceptedQueue.find((x) => x.session_id === session_id);
    if (!resp) {
      const picks = pickFive({ mood: "neutral", round: 1 });
      resp = buildResponse({ meal_type: "lunch", mood: "neutral", refine_input: null, round: 1, picks });
      resp.session_id = session_id;
      storeSession(resp);
    }
    return {
      session_id,
      meal_type: resp.meal_type,
      accepted_at: queued?.accepted_at || resp.generated_at,
      accepted_rank: queued?.accepted_rank ?? null,
      candidates: resp.candidates,
    };
  },
  async getFeedback({ session_id }: { session_id: string }): Promise<FeedbackRecord | null> {
    await sleep(80);
    return STORE.feedbacks[session_id] ?? null;
  },
  async feedback(payload: FeedbackPayload) {
    await sleep(180);
    const existing = STORE.feedbacks[payload.session_id];
    STORE.feedbacks[payload.session_id] = {
      ...payload,
      submitted_at: new Date().toISOString(),
      comments: existing?.comments ?? [],
    };
    // eslint-disable-next-line no-console
    console.log("[chisha mock] POST /api/feedback", payload);
    return { ok: true };
  },
  async appendFeedbackComment({ session_id, text }: { session_id: string; text: string }) {
    await sleep(120);
    const fb = STORE.feedbacks[session_id];
    if (!fb) return { ok: false as const, error: "no feedback to append to" };
    fb.comments = fb.comments || [];
    fb.comments.push({
      id: `cmt_${Date.now()}_${Math.floor(Math.random() * 1000)}`,
      text,
      created_at: new Date().toISOString(),
    });
    return { ok: true as const };
  },
  async skipMeal({ session_id, reason }: { session_id: string; reason: SkipReason }) {
    await sleep(120);
    // skip 不入 acceptedQueue (HomePage 在 accept 之前调它), 这里只是兜底语义
    stopItem(session_id);
    // eslint-disable-next-line no-console
    console.log("[chisha mock] POST /api/skip", { session_id, reason });
    return { ok: true };
  },
  async getProfile() {
    await sleep(60);
    return STORE.profile;
  },
  async putProfile(p: Profile) {
    await sleep(120);
    STORE.profile = p;
    return { ok: true };
  },
  async history({ days = 7 } = {}): Promise<{ items: HistoryItem[] }> {
    await sleep(220);
    void days;
    const items: HistoryItem[] = [];
    const moods: Mood[] = ["neutral", "want_clean", "want_indulgent", "want_soup"];
    for (let i = 0; i < 7; i++) {
      const d = new Date();
      d.setDate(d.getDate() - i);
      const isLunch = (i + d.getDate()) % 3 !== 0;
      const meal: MealType = isLunch ? "lunch" : "dinner";
      const picks = pickFive({ mood: moods[i % 4], round: i + 1 });
      items.push({
        session_id: `2026_${d.toISOString().slice(0, 10)}_${meal}`,
        meal_type: meal,
        generated_at: d.toISOString(),
        accepted_rank: i === 0 ? null : i % 4 === 0 ? null : (i % 3) + 1,
        candidates_summary: picks.slice(0, 3).map((c) => c.restaurant.name.split("·")[0]),
        mood: moods[i % 4],
      });
    }
    return { items };
  },
};
