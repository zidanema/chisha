// Mappings between numeric dimension values returned by backend
// (chisha/score.py) and human-readable Chinese labels for the debug UI.
//
// Source of truth: chisha/score.py grep oil_level / wetness / sweet_sauce_level / spicy_level
//  - oil_level: 1..5 (1=极少油 → 5=高油). 阈值 prefer_oil_level_at_most 通常 3.
//  - sweet_sauce_level: 1..3 (低/中/高).
//  - wetness: 1=干 / 2=卤水 / 3=汤底.
//  - spicy_level: 0..N (>=2 触发惩罚).
//  - main_ingredient_type / cooking_method / grain_type 已是中文字符串.

export type DimKey =
  | "oil_level"
  | "sweet_sauce_level"
  | "wetness"
  | "spicy_level";

const OIL_LEVELS: Record<number, string> = {
  1: "极少油",
  2: "少油",
  3: "中等",
  4: "偏油",
  5: "高油",
};

const SWEET_LEVELS: Record<number, string> = {
  0: "无甜",
  1: "低甜",
  2: "中甜",
  3: "高甜",
};

const WETNESS_LEVELS: Record<number, string> = {
  1: "干",
  2: "卤水",
  3: "汤底",
};

const SPICY_LEVELS: Record<number, string> = {
  0: "无辣",
  1: "微辣",
  2: "中辣",
  3: "重辣",
  4: "巨辣",
};

export function labelForDim(key: DimKey, value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "string") return value;
  if (typeof value !== "number") return String(value);
  switch (key) {
    case "oil_level":         return OIL_LEVELS[value] ?? `lvl ${value}`;
    case "sweet_sauce_level": return SWEET_LEVELS[value] ?? `lvl ${value}`;
    case "wetness":           return WETNESS_LEVELS[value] ?? `lvl ${value}`;
    case "spicy_level":       return SPICY_LEVELS[value] ?? `lvl ${value}`;
  }
}
