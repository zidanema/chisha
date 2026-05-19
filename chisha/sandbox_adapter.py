"""S-06c: v2 candidate → Rec view-model adapter + mock 5 条数据.

Rec 视图字段 (与 apps/sandbox-lab/src/types/sandbox.ts 一致):
  rank, name, venue, dishes (list[str]), price, l2 (0-1), l3 (0-100), boost (派生),
  intent, l1Hits, explore, conflict, meta {eta, dist, protein, oil}, why

l1Hits / conflict 本任务**简化**: 调用方按需提供, 默认 [] / null.
真实数据从 L1 trace 派生留 S-08 联调时按需扩.
"""
from __future__ import annotations

from typing import Any


def format_v2_to_rec(
    candidate: dict,
    *,
    l1_hits: list[str] | None = None,
    refine_intent: dict | None = None,
    intent_override: str | None = None,
) -> dict:
    """v2 candidate (chisha.api._format_v2_candidate 输出) → Rec view-model.

    Args:
        candidate: format_v2_candidate 输出 dict
        l1_hits: 调用方提供的 top-2 L1 token (默认 [])
        refine_intent: refine 路径携带, 派生 intent 字段
        intent_override: 上层显式 intent ("context-fit" / refine summary)

    Returns:
        Rec dict (前端 src/types/sandbox.ts 形态)
    """
    rest = candidate.get("restaurant") or {}
    dishes_objs = candidate.get("dishes") or []
    dish_names = [d.get("canonical_name", "") for d in dishes_objs if d.get("canonical_name")]

    l2 = candidate.get("score")
    # L3 fit_score 在 candidate 内可能没有 (recommend 链路 reranked 后会改写 score 为综合 score);
    # 用 fit_score 字段优先, 否则用 score
    fit = candidate.get("fit_score")
    if fit is not None:
        l3 = round(float(fit) * 100)
    elif l2 is not None:
        l3 = round(float(l2) * 100)
    else:
        l3 = None
    boost = (l3 or 0) - round(float(l2) * 100) if l2 is not None else 0

    if intent_override is not None:
        intent = intent_override
    elif refine_intent:
        intent = (refine_intent.get("summary_text") or "refine")[:12]
    else:
        intent = "context-fit"

    return {
        "rank": candidate.get("rank") or 0,
        "name": rest.get("name") or "",
        "venue": "",  # backend 无 venue 字段, 留空
        "dishes": dish_names,
        "price": round(float(candidate.get("total_price") or 0)),
        "l2": round(float(l2 or 0), 2),
        "l3": l3 if l3 is not None else 0,
        "boost": boost,
        "intent": intent,
        "l1Hits": l1_hits or [],
        "explore": bool(candidate.get("is_explore")),
        "conflict": None,  # S-08 派生 hard_filter_events
        "meta": {
            "eta": f"{rest.get('eta_min', -1)}min" if rest.get("eta_min", -1) >= 0 else "",
            "dist": f"{(rest.get('distance_m', -1) / 1000):.1f}km" if rest.get("distance_m", -1) >= 0 else "",
            "protein": round(float(candidate.get("estimated_total_protein_g") or 0)),
            "oil": f"{candidate.get('estimated_total_oil', 0):.1f}/5",
        },
        "why": candidate.get("reason_one_line") or "",
        # candidate 原始 id (用于 swap exclude_ids 匹配)
        "id": candidate.get("id") or "",
    }


# ---------- Mock 5 条 ----------
# 复刻 apps/sandbox-lab/src/mocks/sbxMocks.ts CURRENT_RECS

MOCK_CURRENT_RECS: list[dict] = [
    {
        "rank": 1, "name": "蓉香记", "venue": "高新店",
        "dishes": ["回锅肉", "蒜苗炒腊肉", "蛋花汤"], "price": 38,
        "l2": 0.85, "l3": 92, "boost": 7, "intent": "不油",
        "l1Hits": ["香", "家常"], "explore": False,
        "conflict": None,
        "meta": {"eta": "12min", "dist": "0.8km", "protein": 42, "oil": "2.4/5"},
        "why": "川菜本周首次,锅气足,0.8km 最近",
        "id": "mock_rec_1",
    },
    {
        "rank": 2, "name": "海记潮汕牛肉", "venue": "深圳湾店",
        "dishes": ["吊龙伴", "嫩肉", "牛肉丸"], "price": 62,
        "l2": 0.78, "l3": 88, "boost": 5, "intent": "蛋白足",
        "l1Hits": ["鲜", "家常"], "explore": False,
        "conflict": None,
        "meta": {"eta": "18min", "dist": "1.4km", "protein": 55, "oil": "1.8/5"},
        "why": "蛋白 55g 充足,鲜+家常双命中",
        "id": "mock_rec_2",
    },
    {
        "rank": 3, "name": "西贡小馆", "venue": "科技园店",
        "dishes": ["招牌牛肉河粉", "炸春卷 2 个"], "price": 32,
        "l2": 0.71, "l3": 84, "boost": 4, "intent": "清淡",
        "l1Hits": ["不油", "带汤水"], "explore": False,
        "conflict": None,
        "meta": {"eta": "15min", "dist": "1.1km", "protein": 28, "oil": "1.2/5"},
        "why": "覆盖不油+带汤水,价低、距离近",
        "id": "mock_rec_3",
    },
    {
        "rank": 4, "name": "钱塘潮·精致江浙菜", "venue": "高新店",
        "dishes": ["杭椒煎牛肉 1 人份", "鸡汤石磨老豆腐", "腐皮鸡毛菜"], "price": 81,
        "l2": 0.83, "l3": 84, "boost": 1, "intent": "蛋白足",
        "l1Hits": ["鲜", "带汤水"], "explore": True,
        "conflict": None,
        "meta": {"eta": "15min", "dist": "1.1km", "protein": 50, "oil": "2.3/5"},
        "why": "江浙菜本周首次,鸡汤豆腐补汤水,1.1km 最近",
        "id": "mock_rec_4",
    },
    {
        "rank": 5, "name": "SaladPower 沙拉力", "venue": "深圳湾店",
        "dishes": ["鸡胸藜麦碗", "烤时蔬", "油醋汁"], "price": 46,
        "l2": 0.66, "l3": 79, "boost": 13, "intent": "控油",
        "l1Hits": ["不油", "蔬菜"], "explore": True,
        "conflict": None,
        "meta": {"eta": "28min", "dist": "2.1km", "protein": 52, "oil": "1.3/5"},
        "why": "本周新店探索,鸡胸 180g 蛋白足;口味契合偏低,吃两次再判断",
        "id": "mock_rec_5",
    },
]


def mock_recs(*, exclude_ids: list[str] | None = None) -> list[dict]:
    """mock_recommend=1 路径返 5 条固定 Rec, 可选过滤 exclude_ids."""
    excl = set(exclude_ids or [])
    return [dict(r) for r in MOCK_CURRENT_RECS if r["id"] not in excl]


def mock_refine_recs(text: str, *, exclude_ids: list[str] | None = None) -> list[dict]:
    """mock_recommend=1 路径 refine: 返 5 条但 intent 写入用户文本前 8 char."""
    intent_text = (text or "").strip()[:8] or "refine"
    excl = set(exclude_ids or [])
    out = []
    for r in MOCK_CURRENT_RECS:
        if r["id"] in excl:
            continue
        copy = dict(r)
        copy["intent"] = intent_text
        out.append(copy)
    return out
