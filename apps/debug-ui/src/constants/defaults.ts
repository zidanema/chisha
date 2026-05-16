// Defaults extracted from App.tsx to keep that file under the 400-line cap.

export const DEFAULT_PROFILE_OVERRIDE = `{
  "protein_floor_g": 22,
  "oil_avoid": ["high"],
  "budget_per_meal": 80,
  "weights": {
    "fit_diet": 0.18,
    "protein_density": 0.14
  }
}`;

export const DEFAULT_REFINE_TEXT = "想喝汤，别给我面食";

export const TODAY_ISO = (): string => new Date().toISOString().slice(0, 10);
