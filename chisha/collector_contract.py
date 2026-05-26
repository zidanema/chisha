"""collector 输出契约校验器 (窄契约, fail-loud).

生产端 waimai_data collector 的 output/*.json → chisha 消费前的**边界校验**。把
"字段改名 / 类型漂移 / 版本不匹配 / 采址 provenance 缺失"从静默出错变响亮报错
(ContractViolation)。契约权威 = waimai `OUTPUT_CONTRACT.md` + 本文件。

不进 high-risk 13 白名单 (纯边界校验器, 无推荐链路逻辑); 见 docs/CONTRACTS.md。

设计 (Codex 设计 review 收敛, D1-D5):
- **窄契约**: required 字段 + 类型校验, extra="allow" → producer 加非破坏字段不阻断消费。
- **strict=True**: 不做隐式类型强转 (price 给字符串 → fail, 不被 pydantic 静默转成 float)。
  实测 A4 真 office 数据全部干净 (price 全 float / menu_count 全 int / rating float|None)。
- **provenance 字段 required-nullable** (D1): location.observed_* 三字段 key 必须在 (值可 null);
  缺 key = 采址 provenance 被删 → fail-loud (Codex Q4 blocker)。
- **版本闸门**: schema_version 必须 == SUPPORTED_SCHEMA_VERSION; normalized_name_version
  必须 == 调用方传入的 chisha SHOP_NAME_VERSION (归一化单边漂移 → 稳定 id mis-join, D-099)。
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

# envelope schema 版本 (== waimai extractor.SCHEMA_VERSION)。破坏性 envelope 变更 → 两端
# 同步 bump + 升级本校验器 + 走跨 repo 迁移。新增非破坏字段 (extra) 不用 bump。
SUPPORTED_SCHEMA_VERSION = 1

# 价格/费用/评分既可能 int(10) 又可能 float(10.5); strict 下用 union 接两者 (bool 不匹配)。
_Number = float | int


class ContractViolation(Exception):
    """collector 输出违反窄契约 (字段缺失/类型漂移/版本不匹配/provenance 缺失)。fail-loud。"""


class _Contract(BaseModel):
    # strict: 不隐式强转类型; extra=allow: 允许 producer 新增非破坏字段。
    model_config = ConfigDict(strict=True, extra="allow")


class MenuItemContract(_Contract):
    name: str
    price: _Number
    # 下游 _build_dishes 实际消费的: name/price (必) + monthly_sales/category (参考)。
    category: str | None = None
    monthly_sales: str | None = None
    # 注: collector 的 `image` 字段实测是 bool 标记 (非 URL), 且下游不消费 →
    # 不进契约, 交给 extra="allow" 放行 (窄契约只约束消费的字段, 不替 producer 定型)。


class RestaurantContract(_Contract):
    name: str                              # 非空由下游 normalize 再校验 (这里只保证是 str)
    menu: list[MenuItemContract]
    # 以下下游 normalize 用 .get() 带默认消费, 缺失可容忍; 若 present 则类型须对 (防漂移)。
    rating: _Number | None = None
    monthly_sales: str | None = None
    distance: str | None = None
    delivery_time: str | None = None
    delivery_fee: _Number | None = None
    min_order: _Number | None = None
    menu_count: int | None = None
    menu_status: str | None = None
    category: str | None = None


class LocationContract(_Contract):
    name: str
    label: str
    # D1 provenance: key 必须存在 (值可 null=unobserved); 缺 key = provenance 被删 → fail。
    # 无默认 = required-but-nullable (pydantic v2: str|None 无默认 → 必填但允许 None)。
    observed_address_text: str | None
    address_observed_at: str | None
    # 值域锁 observed/unobserved (软版只这两态); 非法值 (如 verified/unknown) → fail (Codex S-1)。
    address_observation_status: Literal["observed", "unobserved"] | None


class CollectorOutputContract(_Contract):
    schema_version: int
    normalized_name_version: int
    location: LocationContract
    restaurants: list[RestaurantContract]
    # 分析维度, 缺失可容忍。
    app: str | None = None
    collected_at: str | None = None


def validate_collector_output(
    raw: Any, *, expected_norm_version: int
) -> CollectorOutputContract:
    """校验 collector 输出, fail-loud。返回校验后的 contract 对象 (一般调用方丢弃, 取其副作用)。

    raise ContractViolation 当: raw 非 dict / 违反窄契约 (字段/类型/provenance) /
    schema_version 不支持 / normalized_name_version != expected_norm_version。
    """
    if not isinstance(raw, dict):
        raise ContractViolation(
            f"collector 输出顶层不是 dict (得到 {type(raw).__name__})")
    try:
        doc = CollectorOutputContract.model_validate(raw)
    except ValidationError as e:
        raise ContractViolation(f"collector 输出违反窄契约:\n{e}") from e
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
