// Zone code → human label mapping for the debug UI.
// Source: chisha/recall.py / profile.yaml. Fallback: raw code.

const ZONE_LABELS: Record<string, string> = {
  "shenzhen-bay": "深圳湾办公区",
  "home": "家附近",
  "qianhai": "前海科创区",
  "houhai": "后海办公区",
  "kejiyuan": "科技园",
};

export function zoneLabel(code: string): string {
  return ZONE_LABELS[code] ?? code;
}
