"""collector 输出契约校验器 (窄契约, fail-loud).

生产端 waimai_data collector 的 output/*.json → chisha 消费前的**边界校验**。把
"字段改名 / 类型漂移 / 版本不匹配 / 采址 provenance 缺失"从静默出错变响亮报错
(ContractViolation)。契约权威 = waimai `OUTPUT_CONTRACT.md` + 本文件。

不进 high-risk 白名单 (纯边界校验器, 无推荐链路逻辑); 见 docs/CONTRACTS.md。

设计 (Codex 设计 review 收敛, D1-D5):
- **窄契约**: required 字段 + 类型校验, extra 容忍 → producer 加非破坏字段不阻断消费。
- **strict**: 不做隐式类型强转 (price 给字符串 → fail, 不静默转成 float)。
  实测 A4 真 office 数据全部干净 (price 全 float / menu_count 全 int / rating float|None)。
- **provenance 字段 required-nullable** (D1): location.observed_* 三字段 key 必须在 (值可 null);
  缺 key = 采址 provenance 被删 → fail-loud (Codex Q4 blocker)。
- **版本闸门**: schema_version 必须 == SUPPORTED_SCHEMA_VERSION; normalized_name_version
  必须 == 调用方传入的 chisha SHOP_NAME_VERSION (归一化单边漂移 → 稳定 id mis-join, D-099)。

D-105 (形态B 自包含 skill): 砍 pydantic 依赖 → 纯 dataclass + 手写 strict 校验, 让 core
运行期零 pydantic (唯一第三方依赖 = vendored pyyaml)。手写校验**逐层复刻**原 pydantic
strict + extra=allow 语义 (与旧行为对拍: tests/test_collector_contract.py + golden fixture):
- **required-but-nullable**: 无默认值字段的 key 必须存在 (缺 key → fail), 但值可为 None。
  dataclass `= None` 会让 missing key 静默通过 → 用 _MISSING 哨兵区分"缺 key"与"值=null"。
- **bool 泄漏**: 数值校验前置 `not isinstance(v, bool)` (bool 是 int 子类, strict 拒 bool)。
- **值域枚举**: address_observation_status 锁 observed/unobserved (软版两态)。
- **extra 容忍**: 未知字段不报错 (不 carry — 下游消费 raw dict, 见 loader NOTE)。
- **检查顺序**: 非 dict → 结构/类型校验 (raise "违反窄契约") → schema_version 闸门 →
  norm_version 闸门 (与旧 pydantic validate_collector_output 完全一致)。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# envelope schema 版本 (== waimai extractor.SCHEMA_VERSION)。破坏性 envelope 变更 → 两端
# 同步 bump + 升级本校验器 + 走跨 repo 迁移。新增非破坏字段 (extra) 不用 bump。
SUPPORTED_SCHEMA_VERSION = 1

# observed/unobserved 软版两态 (非法值如 verified/unknown → fail, Codex S-1)。
_STATUS_CHOICES = ("observed", "unobserved")

# 哨兵: 区分 "key 缺失" 与 "key 存在但值为 None" (required-but-nullable 语义关键)。
_MISSING = object()


class ContractViolation(Exception):
    """collector 输出违反窄契约 (字段缺失/类型漂移/版本不匹配/provenance 缺失)。fail-loud。"""


# ───────────────────────────── strict 类型谓词 ─────────────────────────────
# 复刻 pydantic strict: 不隐式强转; bool 不算 number/int (bool 是 int 子类)。

def _is_str(v: Any) -> bool:
    return isinstance(v, str)


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_number(v: Any) -> bool:
    # _Number = float | int union: 接受 int 或 float, 拒 bool。
    return isinstance(v, (int, float)) and not isinstance(v, bool)


_KIND_PRED = {"str": _is_str, "int": _is_int, "number": _is_number}
_KIND_DESC = {"str": "str", "int": "int", "number": "number (int|float)"}


def _check_scalar(
    container: dict,
    key: str,
    *,
    kind: str,
    nullable: bool,
    required: bool,
    path: str,
    choices: tuple | None = None,
) -> Any:
    """校验一个标量字段, 返回值 (或缺失时 _MISSING)。raise ContractViolation。

    - required + key 缺失 → fail (required-but-nullable: 缺 key 也 fail, 即便可 None)。
    - 非 required + key 缺失 → 放行 (返回 _MISSING)。
    - 值为 None: nullable → 放行; 否则 fail。
    - 类型不符 kind → fail (strict, 含 bool 泄漏拒绝)。
    - choices 非空 → 值必须在枚举内。
    """
    fq = f"{path}.{key}"
    if key not in container:
        if required:
            raise ContractViolation(f"{fq}: 缺失必填字段 (required key 必须存在)")
        return _MISSING
    v = container[key]
    if v is None:
        if nullable:
            return None
        raise ContractViolation(f"{fq}: 值为 null 但该字段不可为 null")
    if not _KIND_PRED[kind](v):
        raise ContractViolation(
            f"{fq}: 类型漂移 — 期望 {_KIND_DESC[kind]}, 得到 "
            f"{type(v).__name__}={v!r} (strict, 不隐式强转)"
        )
    if choices is not None and v not in choices:
        raise ContractViolation(
            f"{fq}: 非法枚举值 {v!r} (允许: {', '.join(map(repr, choices))})"
        )
    return v


# ───────────────────────────── dataclass 结构 ─────────────────────────────
# 仅声明被消费/校验的字段 (窄契约); 返回对象一般被调用方丢弃 (loader 用 raw dict)。

@dataclass
class MenuItemContract:
    name: str
    price: float | int
    category: str | None = None
    monthly_sales: str | None = None


@dataclass
class RestaurantContract:
    name: str
    menu: list[MenuItemContract]
    rating: float | int | None = None
    monthly_sales: str | None = None
    distance: str | None = None
    delivery_time: str | None = None
    delivery_fee: float | int | None = None
    min_order: float | int | None = None
    menu_count: int | None = None
    menu_status: str | None = None
    category: str | None = None


@dataclass
class LocationContract:
    name: str
    label: str
    # required-but-nullable: key 必须在 (值可 null=unobserved)。
    observed_address_text: str | None = _MISSING  # type: ignore[assignment]
    address_observed_at: str | None = _MISSING  # type: ignore[assignment]
    address_observation_status: str | None = _MISSING  # type: ignore[assignment]


@dataclass
class CollectorOutputContract:
    schema_version: int
    normalized_name_version: int
    location: LocationContract
    restaurants: list[RestaurantContract]
    app: str | None = None
    collected_at: str | None = None


# ───────────────────────────── 逐层手写校验 ───────────────────────────────

def _validate_menu_item(raw: Any, path: str) -> MenuItemContract:
    if not isinstance(raw, dict):
        raise ContractViolation(
            f"{path}: 期望 dict (menu item), 得到 {type(raw).__name__}")
    name = _check_scalar(raw, "name", kind="str", nullable=False, required=True, path=path)
    price = _check_scalar(raw, "price", kind="number", nullable=False, required=True, path=path)
    category = _check_scalar(raw, "category", kind="str", nullable=True, required=False, path=path)
    monthly = _check_scalar(raw, "monthly_sales", kind="str", nullable=True, required=False, path=path)
    return MenuItemContract(
        name=name, price=price,
        category=None if category is _MISSING else category,
        monthly_sales=None if monthly is _MISSING else monthly,
    )


def _validate_restaurant(raw: Any, path: str) -> RestaurantContract:
    if not isinstance(raw, dict):
        raise ContractViolation(
            f"{path}: 期望 dict (restaurant), 得到 {type(raw).__name__}")
    name = _check_scalar(raw, "name", kind="str", nullable=False, required=True, path=path)
    if "menu" not in raw:
        raise ContractViolation(f"{path}.menu: 缺失必填字段 (required key 必须存在)")
    menu_raw = raw["menu"]
    if not isinstance(menu_raw, list):
        raise ContractViolation(
            f"{path}.menu: 期望 list, 得到 {type(menu_raw).__name__}")
    menu = [_validate_menu_item(it, f"{path}.menu[{i}]") for i, it in enumerate(menu_raw)]
    opt = {
        "rating": "number", "delivery_fee": "number", "min_order": "number",
        "menu_count": "int", "monthly_sales": "str", "distance": "str",
        "delivery_time": "str", "menu_status": "str", "category": "str",
    }
    vals = {}
    for k, kind in opt.items():
        r = _check_scalar(raw, k, kind=kind, nullable=True, required=False, path=path)
        vals[k] = None if r is _MISSING else r
    return RestaurantContract(name=name, menu=menu, **vals)


def _validate_location(raw: Any, path: str) -> LocationContract:
    if not isinstance(raw, dict):
        raise ContractViolation(
            f"{path}: 期望 dict (location), 得到 {type(raw).__name__}")
    name = _check_scalar(raw, "name", kind="str", nullable=False, required=True, path=path)
    label = _check_scalar(raw, "label", kind="str", nullable=False, required=True, path=path)
    # D1 provenance: 三字段 required-but-nullable (缺 key → fail, 值可 null)。
    obs_text = _check_scalar(raw, "observed_address_text", kind="str",
                             nullable=True, required=True, path=path)
    obs_at = _check_scalar(raw, "address_observed_at", kind="str",
                           nullable=True, required=True, path=path)
    status = _check_scalar(raw, "address_observation_status", kind="str",
                           nullable=True, required=True, path=path, choices=_STATUS_CHOICES)
    return LocationContract(
        name=name, label=label,
        observed_address_text=obs_text, address_observed_at=obs_at,
        address_observation_status=status,
    )


def _validate_structure(raw: dict) -> CollectorOutputContract:
    """结构 + 类型校验 (复刻 pydantic model_validate)。raise ContractViolation。"""
    schema_version = _check_scalar(raw, "schema_version", kind="int",
                                   nullable=False, required=True, path="$")
    norm_version = _check_scalar(raw, "normalized_name_version", kind="int",
                                 nullable=False, required=True, path="$")
    if "location" not in raw:
        raise ContractViolation("$.location: 缺失必填字段 (required key 必须存在)")
    location = _validate_location(raw["location"], "$.location")
    if "restaurants" not in raw:
        raise ContractViolation("$.restaurants: 缺失必填字段 (required key 必须存在)")
    rest_raw = raw["restaurants"]
    if not isinstance(rest_raw, list):
        raise ContractViolation(
            f"$.restaurants: 期望 list, 得到 {type(rest_raw).__name__}")
    restaurants = [
        _validate_restaurant(r, f"$.restaurants[{i}]") for i, r in enumerate(rest_raw)
    ]
    app = _check_scalar(raw, "app", kind="str", nullable=True, required=False, path="$")
    collected = _check_scalar(raw, "collected_at", kind="str", nullable=True, required=False, path="$")
    return CollectorOutputContract(
        schema_version=schema_version, normalized_name_version=norm_version,
        location=location, restaurants=restaurants,
        app=None if app is _MISSING else app,
        collected_at=None if collected is _MISSING else collected,
    )


def validate_collector_output(
    raw: Any, *, expected_norm_version: int
) -> CollectorOutputContract:
    """校验 collector 输出, fail-loud。返回校验后的 contract 对象 (一般调用方丢弃, 取其副作用)。

    raise ContractViolation 当: raw 非 dict / 违反窄契约 (字段/类型/provenance) /
    schema_version 不支持 / normalized_name_version != expected_norm_version。

    检查顺序与旧 pydantic 版本一致: 非 dict → 结构/类型 → schema_version → norm_version。
    """
    if not isinstance(raw, dict):
        raise ContractViolation(
            f"collector 输出顶层不是 dict (得到 {type(raw).__name__})")
    doc = _validate_structure(raw)
    if doc.schema_version != SUPPORTED_SCHEMA_VERSION:
        raise ContractViolation(
            f"schema_version={doc.schema_version} 不受支持 "
            f"(本消费端支持 {SUPPORTED_SCHEMA_VERSION})。破坏性 envelope 变更需"
            "同步升级本校验器 + 走跨 repo 迁移, 不要静默放行。")
    if doc.normalized_name_version != expected_norm_version:
        raise ContractViolation(
            f"normalized_name_version={doc.normalized_name_version} != "
            f"chisha SHOP_NAME_VERSION={expected_norm_version}。归一化规则单边漂移会让"
            "稳定 id 全面 mis-join (D-099)。两端必须同版 + 走 scripts/migrate_stable_ids。")
    return doc
