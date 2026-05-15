import type { Profile } from "./types";

// Mirrors prototype profile-defaults.js. Source of truth for first-load
// before /api/profile responds. Keep in sync with the Python profile.yaml shape.
export const PROFILE_DEFAULTS: Profile = {
  basics: {
    name: "志丹",
    city: "深圳",
    goal: "体重控制+力量训练期（保饱腹感，参考哈佛餐盘法）",
    zones: { lunch: "shenzhen-bay", dinner: "shenzhen-bay" },
  },
  plate_rule: {
    must_have_vegetable: true,
    min_vegetable_dishes: 1,
    min_protein_g: 40,
    prefer_oil_level_at_most: 3,
    hard_max_oil_level: 4,
  },
  taste_description: `=== 健康目标 ===
体重控制 + 力量训练期。哈佛餐盘法（1/2 蔬菜 + 1/4 蛋白 + 1/4 复合碳水）。
关键失败模式（朋友A教训）：极致清淡 + 极致低油 → 当顿满足感弱 →
半夜反弹宵夜，总热量反而更高。
所以不是"这一顿热量最低"，而是"这一顿能撑到下一顿"。

=== 真实口味偏好（不考虑健康约束）===
- 喜欢有锅气的炒菜、味道重的下饭菜——这是核心口味
- 喜欢辣椒炒、酸菜煮、卤味、糖醋、蜜汁、照烧、红烧——口味上都喜欢
- 喜欢汤水/带汁的也行（潮汕牛肉、酸菜鱼、翘脚牛肉、卤粉）
- 能吃重辣（spicy_tolerance=3）`,
  preferences: {
    liked_cuisines: ["湘菜", "川菜", "潮汕", "粤菜", "日式", "轻食健康"],
    disliked_cuisines: ["饮品甜品", "烧烤"],
    banned_cuisines: [],
    banned_processed_meat: false,
    banned_sweet_sauce_level_3: false,
    avoid_dishes: [],
    avoid_main_ingredients: [],
    avoid_cooking_methods: [],
    avoid_restaurants: [],
    spicy_tolerance: 3,
  },
  delivery_constraints: {
    hard_max_eta_min: 45,
    prefer_max_eta_min: 30,
  },
  price_range: {
    hard_max_lunch: 150,
    hard_max_dinner: 150,
    prefer_max_lunch: 120,
    prefer_max_dinner: 120,
  },
  meal_trigger_time: {
    lunch: "11:25",
    dinner: "18:00",
    weekend: false,
  },
  llm: {
    provider: "auto",
    model: {
      claude_code_cli: "sonnet",
      anthropic: "claude-sonnet-4-6",
      openrouter: "anthropic/claude-sonnet-4.6",
    },
  },
};

export const ZONES_OPTS = [
  { id: "shenzhen-bay", label: "深圳湾·科技园" },
  { id: "home", label: "家附近" },
  { id: "futian-cbd", label: "福田 CBD" },
  { id: "other", label: "其它" },
] as const;
