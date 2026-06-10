"""D-104 Step 1a: agent-only core 的 card / session 格式化 helper (从 api 抽出).

这些是 agent cards 真正需要的纯函数, 与 recommend_meal 全链路 / rich trace 渲染解耦。
零 debug/web/自调LLM 依赖: 仅用 stdlib + lazy core (clock / recall.dish_price)。
函数体与原 api.py 逐字一致 (D-104 行为 0-diff)。
"""
from __future__ import annotations

import secrets

# Codex PR-2 DEFER #5: schema 与 trace_store 序列化严格一致的单一权威源
# (D-104 Step1a: 从 api 挪来, 消除 trace_store→api 的 core→extras 隐边).
_SCORING_NUTRITION_KEYS = {
    "oil_level", "spicy_level", "wetness", "sweet_sauce_level", "processed_meat_flag",
    "main_ingredient_type", "vegetable_ratio_estimate", "protein_grams_estimate",
    "cooking_method", "dish_role", "grain_type", "is_complete_meal", "tags",
}


def _gen_session_id(meal_type: str) -> str:
    """生成 session_id. D-079 Codex FIX-NOW: 随机段从 16-bit (4hex) 扩到 64-bit
    (16hex) 防并发 sid 撞名 + tmp 文件竞态. 单用户场景 Phase 0 实际不会撞,
    但 token_hex(8) 几乎零代价让 PR-2/Phase 1 多端访问也安全.
    """
    from chisha import clock
    today = clock.now().strftime("%Y%m%d")
    return f"{today}_{meal_type}_{secrets.token_hex(8)}"


def _format_candidate(rank: int, c: dict) -> dict:
    rest = c["restaurant"]
    dishes = c["dishes"]
    dish_objs = [
        {
            "dish_id": d["dish_id"],
            "canonical_name": d["canonical_name"],
            "price": d["price"],
            "main_ingredient_type":
                d["nutrition_profile"]["main_ingredient_type"],
            "oil_level": d["nutrition_profile"]["oil_level"],
        }
        for d in dishes
    ]
    from chisha.recall import dish_price
    total_price = sum(dish_price(d) for d in dishes)
    avg_oil = round(
        sum(d["nutrition_profile"]["oil_level"] for d in dishes)
        / max(1, len(dishes)), 1
    )
    veg_count = sum(
        1 for d in dishes
        if d["nutrition_profile"]["main_ingredient_type"] == "纯素"
        or d["nutrition_profile"]["vegetable_ratio_estimate"] >= 0.6
    )
    total_protein = sum(
        d["nutrition_profile"]["protein_grams_estimate"] for d in dishes
    )
    return {
        "rank": rank,
        "is_explore": False,
        "summary": " + ".join(d["canonical_name"] for d in dishes),
        "restaurant": {
            "id": rest["id"],
            "name": rest["name"],
            "distance_m": rest.get("distance_m", -1),
            "eta_min": rest.get("delivery_eta_min", -1),
        },
        "dishes": dish_objs,
        "total_price": round(total_price, 1),
        "vegetable_dish_count": veg_count,
        "estimated_total_oil": avg_oil,
        "estimated_total_protein_g": total_protein,
        "score": round(c["score"], 3),
        "reason_one_line": c.get("reason_one_line", ""),
    }


def _resolve_zone(profile: dict, meal_type: str) -> str:
    """优先用 basics.zones.{meal_type}, 退化到 basics.office_zone."""
    zones = profile.get("basics", {}).get("zones") or {}
    if meal_type in zones:
        return zones[meal_type]
    return profile["basics"]["office_zone"]


def _format_v2_candidate(rank: int, c: dict) -> dict:
    """V2 candidate 格式化: 复用 _format_candidate 字段, 加上 rerank 字段."""
    base = _format_candidate(rank, c)
    base["rank"] = c.get("rank", rank)
    base["is_explore"] = bool(c.get("is_explore", False))
    base["fit_score"] = c.get("fit_score")
    base["health_flags"] = c.get("health_flags") or {}
    base["taste_match"] = c.get("taste_match")
    base["risk_flags"] = c.get("risk_flags") or []
    base["reason_one_line"] = c.get("one_line_reason") or c.get("reason_one_line", "")
    # 前端 (apps/web) 的 Candidate.id: 用 combo_index + restaurant.id 合成稳定 key
    rest_id = (c.get("restaurant") or {}).get("id", "?")
    combo_idx = c.get("combo_index", rank)
    base["id"] = f"c_{combo_idx}_{rest_id}"
    return base


# 暴露给 web_api / 外部调用方:
format_v2_candidate = _format_v2_candidate


def _format_final_minimal(rank: int, c: dict) -> dict:
    """D-104 Step1b: trace["final"] 的 core 最小格式化 (供 slim core 发最小功能 trace).

    刻意镜像 debug_recommend._format_final_candidate 的字段口径 (行为 parity):
    - dish 用 key "name" (= canonical_name), 让 trace_store._extract_top1_summary 不退化;
    - **刻意不带 dish cuisine** —— _format_final_candidate 也不带, 不能让 slim 下
      reference_resolver 的 `similar` 关系从"现状恒 no-op"变成按 cuisine 生效 (Codex blocker);
    - 不含 _combo_signature (那是 debug_recommend/extras 专属, reference refine 不消费)。
    reference refine 实际只读 final[].restaurant.id (similar_but_different_venue)。
    """
    rest = c.get("restaurant", {})
    return {
        "rank": rank,
        "combo_index": c.get("combo_index"),
        "is_explore": bool(c.get("is_explore", False)),
        "restaurant": {
            "id": rest.get("id"),
            "name": rest.get("name"),
            "distance_m": rest.get("distance_m", -1),
            "eta_min": rest.get("delivery_eta_min", -1),
        },
        "dishes": [
            {
                "dish_id": d.get("dish_id"),
                "name": d.get("canonical_name"),
                "price": d.get("price"),
                "main_ingredient_type":
                    d["nutrition_profile"].get("main_ingredient_type"),
                "oil_level": d["nutrition_profile"].get("oil_level"),
            }
            for d in c.get("dishes", [])
        ],
        "total_price": round(
            sum(d.get("price", 0) for d in c.get("dishes", [])), 1
        ),
        "score": round(c.get("score", 0), 3),
        "fit_score": c.get("fit_score"),
        "health_flags": c.get("health_flags") or {},
        "risk_flags": c.get("risk_flags") or [],
        "taste_match": c.get("taste_match"),
        "one_line_reason":
            c.get("one_line_reason") or c.get("reason_one_line", ""),
    }


# ───────────────── M3: region 状态 + profile_status 派生 ─────────────────
# 设计 (codex 触点 sign-off): profile_status **派生** 不存盘 — region friendly_name 单一源
# = manifest (load_zones), 不在 profile 存以防漂移. ready 回包带派生快照 (写进 _write_ready
# 供 continue 幂等回放, 不在 replay 时重新派生). 节 3c 回包结构 + §5.5 coming_soon 契约.

_METHODOLOGY_FRIENDLY = {"harvard_plate": "哈佛餐盘"}

_TASTE_EMPTY_NOTICE = {
    "kind": "taste_empty",
    "message": ("我还不了解你的口味，这轮先按哈佛餐盘和通用多样性推荐。"
                "你可以直接说“爱吃辣/不吃海鲜/少米饭”，我会记进画像；"
                "想一次配好可以说“配一下画像”。"),
    # D-112 Step1: urgency 调宿主语气 (low = 软邀请、once_per_session、不催);
    # 预留 "one_time" 给未来一次性提示。surfacing 频率由 once_key 去重保证 (见下).
    "urgency": "low",
}


def resolve_region(zone_id: str, root) -> dict:
    """zone_id → region 状态 (单一权威源 = manifest). 返回 {state, zone, eatable}.

    state: available | coming_soon | deprecated | unsupported | unversioned.
    eatable: 能否进 recall/score (仅 available / unversioned).

    G2 (codex): 缺 manifest (未版本化 bundle) **不**当 unsupported — 放行走原 load_zone_data
    行为 (zone 数据真缺才 ZoneNotFoundError); manifest 损坏 → parse_zones raise 上抛 (错误态,
    不伪装成待上线). 只有"manifest 存在但 zone 不在清单"才是 unsupported。
    """
    from chisha import manifest
    data = manifest.read_manifest(root)
    if data is None:
        return {"state": "unversioned", "zone": None, "eatable": True}
    for z in manifest.parse_zones(data, manifest.manifest_path(root)):
        if z["zone_id"] == zone_id or zone_id in z["slug"]:
            return {"state": z["status"], "zone": z, "eatable": z["status"] == "available"}
    return {"state": "unsupported", "zone": None, "eatable": False}


def _taste_is_empty(profile: dict) -> bool:
    taste = profile.get("taste_description")
    return taste is None or (isinstance(taste, str) and not taste.strip())


def build_profile_status(profile: dict, zone_id: str, region: dict) -> dict:
    """派生 ready/coming_soon 回包的 profile_status (节 3c 回包结构). 纯派生, 不读存储节。"""
    st = region["state"]
    zobj = region.get("zone")
    if st == "unsupported":
        region_block = {"state": "unsupported", "zone_id": None, "friendly_name": None}
    elif st in ("available", "unversioned"):
        region_block = {
            "state": "set", "zone_id": zone_id,
            "friendly_name": zobj["friendly_name"] if zobj else zone_id,
        }
    else:  # coming_soon | deprecated
        region_block = {
            "state": st, "zone_id": zone_id,
            "friendly_name": zobj["friendly_name"] if zobj else zone_id,
        }
    taste_empty = _taste_is_empty(profile)
    taste = profile.get("taste_description")
    meth = profile.get("methodology") or "harvard_plate"
    return {
        "region": region_block,
        "taste": {
            "state": "empty" if taste_empty else "set",
            "summary": None if taste_empty else taste.strip()[:80],
        },
        "methodology": {
            "state": "default", "name": meth,
            "friendly_name": _METHODOLOGY_FRIENDLY.get(meth, meth),
        },
    }


def build_profile_notice(profile_status: dict, *, sid: str | None = None) -> dict | None:
    """taste 为空 → taste_empty 提示 (软性邀请补全); 否则 None (节 3c / D-112 Step1)。

    D-112 Step1 (surfacing 可靠化): 带 `once_key` (per-session 去重键) + `urgency`。
    once_key = `taste_empty:{sid}` —— **session = sid**: refine 续轮经 `--from` 复用同
    sid → 同 once_key, 宿主按 SKILL.md 硬规则"同 once_key 每 session 至多念一次"去重;
    新开一餐 = 新 sid = 新 once_key → 重新念一次 (once_per_session)。把"别催"从软性
    "可跳过"重定义为协议级"每 session 至多一次"。sid 缺省 (防御) 时省略 once_key。
    """
    if profile_status.get("taste", {}).get("state") == "empty":
        notice = dict(_TASTE_EMPTY_NOTICE)
        if sid:
            notice["once_key"] = f"taste_empty:{sid}"
        return notice
    return None


def build_coming_soon_response(zone_id: str, region: dict, profile: dict) -> dict:
    """unsupported / coming_soon region 的 eat 终态回包 (§5.5).

    G3 (codex): cards=[] + **无 do_llm / step_token** + 调用方**不建 round** — host 看 status
    =coming_soon 即终止, 不再调 continue, 不污染 agent_round_store (只支持 pending/resolved)。
    """
    st = region["state"]
    zobj = region.get("zone")
    profile_status = build_profile_status(profile, zone_id, region)
    if st == "unsupported":
        reason = "unsupported_region"
        message = ("你所在区域暂未覆盖，已先装好 chisha；该 region 数据上线后即可推荐。")
    else:  # coming_soon | deprecated
        reason = "region_coming_soon"
        fname = (zobj or {}).get("friendly_name") or zone_id
        message = f"{fname} 即将上线，敬请期待；已装好 chisha，数据上线后即可推荐。"
    return {
        "ok": True,
        "status": "coming_soon",
        "reason": reason,
        "message": message,
        "profile_status": profile_status,
        "cards": [],
    }
