"""共享 pytest fixtures."""
import datetime as dt
import pytest


@pytest.fixture(autouse=True)
def _isolate_state_root(tmp_path, monkeypatch):
    """D-102 Step2: 测试里把 state_root 的**默认落点**钉到本测试 tmp_path。

    机制 = monkeypatch `state_root.default_state_root` (只在 root=None / root==包目录
    时命中), **不动** env、**不覆盖**显式传入的 root —— 所以:
    - 传 root=tmp_path / 多 root 隔离测试: 各自显式 root 仍被尊重 (隔离不变);
    - None-root / 包目录-root (如 clock(None) / 生产式调用): 落 tmp_path, **绝不污染
      真实 ~/.chisha/ 或 repo** (Commit B 翻默认后尤其关键);
    - 同时 delenv 防真实环境 CHISHA_STATE_ROOT 泄漏进测试。
    要验"默认解析到 ~/.chisha"的测试可自行 monkeypatch.setattr 复原或走 env。
    """
    from chisha import state_root
    monkeypatch.delenv("CHISHA_STATE_ROOT", raising=False)
    monkeypatch.setattr(state_root, "default_state_root", lambda: tmp_path)


def make_dish(
    dish_id: str = "d_001_001",
    restaurant_id: str = "r_001",
    raw_name: str = "测试菜",
    canonical_name: str | None = None,
    price: float = 30.0,
    monthly_sales: int = 100,
    cuisine: str = "湘菜",
    main_ingredient_type: str = "红肉",
    cooking_method: str = "煮",
    oil_level: int = 2,
    protein_grams_estimate: int = 30,
    vegetable_ratio_estimate: float = 0.2,
    is_complete_meal: bool = False,
    spicy_level: int = 1,
    tags: list[str] | None = None,
    is_available: bool = True,
    # V2 新字段 (D-032 v3 schema, 与 chisha/schemas.py 对齐).
    # 默认 include_v2=True 让 V2 测试能直接用; test_schemas 老的 V1 校验需 include_v2=False.
    include_v2: bool = True,
    dish_role: str = "主菜",        # 主菜/主食/配菜/汤/小食/饮品/套餐
    processed_meat_flag: bool = False,
    sweet_sauce_level: int = 0,      # 0-3 (0=无甜味, 2=红烧/糖醋, 3=蜜汁/拔丝)
    wetness: int = 1,                # 1-3 (1=干煸/凉拌, 2=卤水浸泡, 3=可喝汤底)
    grain_type: str = "无",          # 白米/糙米杂粮/精制面/全麦面/粗粮/粥/无
) -> dict:
    np = {
        "main_ingredient_type": main_ingredient_type,
        "cooking_method": cooking_method,
        "oil_level": oil_level,
        "protein_grams_estimate": protein_grams_estimate,
        "vegetable_ratio_estimate": vegetable_ratio_estimate,
        "is_complete_meal": is_complete_meal,
        "spicy_level": spicy_level,
        "tags": tags or [],
    }
    if include_v2:
        np.update({
            "dish_role": dish_role,
            "processed_meat_flag": processed_meat_flag,
            "sweet_sauce_level": sweet_sauce_level,
            "wetness": wetness,
            "grain_type": grain_type,
        })
    return {
        "dish_id": dish_id,
        "restaurant_id": restaurant_id,
        "raw_name": raw_name,
        "canonical_name": canonical_name or raw_name,
        "price": price,
        "monthly_sales": monthly_sales,
        "cuisine": cuisine,
        "nutrition_profile": np,
        "metadata": {
            "tagged_at": "2026-05-11T00:00:00",
            "tag_version": "test",
            "is_available": is_available,
        },
    }


def make_restaurant(
    rid: str = "r_001",
    name: str = "测试餐厅",
    brand: str | None = None,
    category: str = "湘菜",
    rating: float = 4.5,
    monthly_orders: int = 500,
) -> dict:
    return {
        "id": rid,
        "name": name,
        "brand": brand or name,
        "category": category,
        "city": "深圳",
        "office_zone": "test",
        "rating": rating,
        "monthly_orders": monthly_orders,
        "distance_m": 500,
        "delivery_eta_min": 20,
        "delivery_fee": 3.0,
        "min_order": 20.0,
    }


@pytest.fixture
def basic_profile():
    return {
        "basics": {"name": "test", "city": "深圳", "office_zone": "test"},
        "plate_rule": {
            "must_have_vegetable": True,
            "min_vegetable_dishes": 1,
            "min_protein_g": 25,
            "prefer_oil_level_at_most": 3,
            "hard_max_oil_level": 5,
        },
        "preferences": {
            "liked_cuisines": ["湘菜", "潮汕"],
            "disliked_cuisines": ["饮品甜品"],
            "avoid_dishes": ["红烧肉"],
            "spicy_tolerance": 2,
        },
        "diversity": {
            "no_same_restaurant_within_days": 7,
            "no_same_main_ingredient_within_days": 3,
        },
        "recall": {"top_n": 100, "per_restaurant_max": 3,
                   "min_monthly_sales": 10},
        "scoring_weights": {
            # D-092: floor 死维度已移除, 此 fixture 同步
            "low_oil": 0.8,
            "popularity": 0.4,
            "cuisine_preference": 0.5,
            "variety_bonus": 0.3,
        },
    }


# D-078: 异步 L1 抽取 settle 等待 — 监 last_l1_extraction.at 翻新而非
# status, 避免上一轮 ok → 下一轮 ok→ok 过渡的瞬间被误判.
def wait_l1_settle(client, prev_at: str | None = None,
                    timeout: float = 4.0) -> tuple[str, str | None]:
    """等 last_l1_extraction.at 比 prev_at 新且 status ∈ {ok, failed}.

    Returns (status, new_at). 超时返回 ("timeout", prev_at).
    """
    import time as _t
    deadline = _t.time() + timeout
    while _t.time() < deadline:
        s = client.get("/api/sandbox/state").json()
        ext = s.get("last_l1_extraction") or {}
        cur_at = ext.get("at")
        if (cur_at and cur_at != prev_at
                and ext.get("status") in ("ok", "failed")):
            return ext.get("status"), cur_at
        _t.sleep(0.05)
    return "timeout", prev_at


@pytest.fixture
def wait_l1_settle_fixture():
    """pytest fixture 包装. 用法: status, at = wait_l1_settle_fixture(c, prev_at)."""
    return wait_l1_settle
