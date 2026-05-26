"""D-074 Phase 0: AI-friendly agent 协议地基.

宿主 agent 调 chisha CLI 时, chisha 不发任何 LLM 请求 (不持 provider key);
需要智能判断的步骤 (context→intent 抽取 / 候选→排序) 由 chisha 发一个
**机器可读的 `llm_request_spec` 信封**, 宿主 agent 背后的 LLM 执行后按
`correlation_id` 回传, chisha 校验落库.

本模块只管协议地基 (设计 §4):
  - 版本常量 + operation_kind 枚举
  - `CorrelationId` = (recommendation_id, round, operation) 编解码 + 幂等键派生
  - `build_request_spec` 信封 builder (两个 operation 共用 shape)
  - `parse_agent_response` 回传解包 + correlation 校验

**不碰链路逻辑**: spec 的 system/messages/tools/json_schema 内容由 rerank
(build_rerank_spec) / refine_intent_v2 (build_extract_spec) 填, 本模块只负责
把它们包进带版本的信封 + 解开 agent 的回传. 确定性守卫全留在那两个模块.

边界 (设计第一原则): 本模块是"智能请求"的传输协议, 候选生成 / 清洗 / 校验 /
后处理 / fallback / disclosure / trace 组装一律不在这里, 也不在 agent 输出上补偿.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# ─────────────────────────── 版本常量 ───────────────────────────
# protocol_version: 信封 shape 的版本. 改信封字段集 (加/删/重命名 top-level key)
# → bump. 纯扩展某 operation 内部 schema 不 bump 这个 (走 candidate_schema_version).
PROTOCOL_VERSION = "1.0"

# candidate_schema_version: refine intent / candidate 槽位 schema 版本.
# 与 refine_intent_v2.RefineIntentV2.schema_version (D-094.1 "2.1") 对齐 —
# agent 据此知道 extract 该产出哪些 slot. 改 V2 槽位走 D-094.x + 这里同步 bump.
CANDIDATE_SCHEMA_VERSION = "2.1"

OperationKind = Literal["extract", "rerank"]
OutputMode = Literal["tool_use", "text_json"]
FALLBACK_POLICY = "chisha_l2"

_VALID_OPERATIONS: frozenset[str] = frozenset({"extract", "rerank"})
_VALID_OUTPUT_MODES: frozenset[str] = frozenset({"tool_use", "text_json"})

# correlation_id 字符串分隔符. session_id 形如 "20260525_lunch_<hex>" (无冒号,
# 见 api._gen_session_id), round 是 "R{n}", operation 是枚举 → 冒号安全.
_CID_SEP = "::"


# ─────────────────────────── correlation_id ───────────────────────────

@dataclass(frozen=True)
class CorrelationId:
    """(recommendation_id, round, operation) 三元组, 绑定请求与回传 + 支幂等.

    - recommendation_id: 复用 session_id (codex Q3: 已是 session/trace/feedback/
      meal_log 连接键, 不新建映射层). CLI 对外字段名 `recommendation_id`, 值=sid.
    - round: "R{n}" (与 trace_store v3 round_id 对齐).
    - operation: "extract" | "rerank".
    """
    recommendation_id: str
    round: str
    operation: OperationKind

    def __post_init__(self) -> None:
        if self.operation not in _VALID_OPERATIONS:
            raise ValueError(f"invalid operation: {self.operation!r}")
        for fld in (self.recommendation_id, self.round):
            if not fld or _CID_SEP in fld or "/" in fld or ".." in fld:
                raise ValueError(f"invalid correlation_id component: {fld!r}")

    def encode(self) -> str:
        return _CID_SEP.join((self.recommendation_id, self.round, self.operation))

    @classmethod
    def decode(cls, s: str) -> CorrelationId:
        parts = (s or "").split(_CID_SEP)
        if len(parts) != 3:
            raise ValueError(f"malformed correlation_id: {s!r}")
        rid, rnd, op = parts
        return cls(recommendation_id=rid, round=rnd, operation=op)  # type: ignore[arg-type]

    def idempotency_key(self) -> str:
        """幂等键 = correlation_id 编码 (设计 §3: 每步幂等键 = (rid, round, operation)).

        重试同 correlation_id 应返同结果不新建 round (由 trace_store 状态机消费).
        """
        return self.encode()


# ─────────────────────────── 信封 builder ───────────────────────────

@dataclass
class LLMRequestSpec:
    """`llm_request_spec` 信封 (设计 §4). 两个 operation_kind 共用 shape.

    chisha 填好后随 verb 返回; 宿主 agent **只执行** (按 output_mode 翻译成它自己
    LLM 的 tool_use / json 调用), 产出按 correlation_id 回传对应 verb.
    """
    operation_kind: OperationKind
    correlation_id: str                       # CorrelationId.encode()
    output_mode: OutputMode
    system: str
    messages: list[dict[str, Any]]
    # tool_use 模式填 tools (+ tool_choice); text_json 模式填 json_schema.
    tools: list[dict[str, Any]] | None = None
    tool_choice: dict[str, Any] | None = None
    json_schema: dict[str, Any] | None = None
    # required_validation: 告诉 agent chisha 会校验什么 (合约透明, 让 agent 的 LLM
    # 按同一套规则产出 — 设计 §5 "prompt 即契约"). 人读字符串列表, 非机器强约束.
    required_validation: list[str] = field(default_factory=list)
    fallback_policy: str = FALLBACK_POLICY
    protocol_version: str = PROTOCOL_VERSION
    candidate_schema_version: str = CANDIDATE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "protocol_version": self.protocol_version,
            "candidate_schema_version": self.candidate_schema_version,
            "operation_kind": self.operation_kind,
            "correlation_id": self.correlation_id,
            "output_mode": self.output_mode,
            "system": self.system,
            "messages": self.messages,
            "required_validation": self.required_validation,
            "fallback_policy": self.fallback_policy,
        }
        if self.output_mode == "tool_use":
            d["tools"] = self.tools or []
            if self.tool_choice is not None:
                d["tool_choice"] = self.tool_choice
        else:  # text_json
            if self.json_schema is not None:
                d["json_schema"] = self.json_schema
        return d


def build_request_spec(
    *,
    operation_kind: OperationKind,
    correlation_id: CorrelationId,
    output_mode: OutputMode,
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    tool_choice: dict[str, Any] | None = None,
    json_schema: dict[str, Any] | None = None,
    required_validation: list[str] | None = None,
) -> dict[str, Any]:
    """组装 `llm_request_spec` 信封 dict (随 verb 返回给 agent).

    校验: operation/output_mode 枚举; tool_use 必须带 tools; text_json 不带 tools.
    内容 (system/messages/tools/json_schema) 由调用方 (rerank/refine_intent_v2) 准备.
    """
    if operation_kind not in _VALID_OPERATIONS:
        raise ValueError(f"invalid operation_kind: {operation_kind!r}")
    if output_mode not in _VALID_OUTPUT_MODES:
        raise ValueError(f"invalid output_mode: {output_mode!r}")
    if output_mode == "tool_use":
        if not tools:
            raise ValueError("output_mode=tool_use 必须提供 tools")
    else:  # text_json
        if tools:
            raise ValueError("output_mode=text_json 不应带 tools (走 json_schema)")
    spec = LLMRequestSpec(
        operation_kind=operation_kind,
        correlation_id=correlation_id.encode(),
        output_mode=output_mode,
        system=system,
        messages=messages,
        tools=tools,
        tool_choice=tool_choice,
        json_schema=json_schema,
        required_validation=list(required_validation or []),
    )
    return spec.to_dict()


# ─────────────────────────── 回传解包 ───────────────────────────

@dataclass
class AgentResponse:
    """宿主 agent 执行 spec 后的回传 (解包后)."""
    correlation_id: CorrelationId
    payload: dict[str, Any]                   # extract: intent dict; rerank: {candidates, narrative}
    disclosure: dict[str, Any] = field(default_factory=dict)


def parse_agent_response(
    raw: dict[str, Any],
    *,
    expected: CorrelationId,
) -> AgentResponse:
    """解开 agent 回传 + correlation 校验.

    回传 shape (agent 按信封产出):
        {"correlation_id": "<sid>::R1::extract",
         "payload": {...},                  # extract→intent dict / rerank→{candidates,...}
         "disclosure": {...}}               # 可选; extract 的未映射诉求 / rerank 校验状态

    correlation_id **必填** (F4) 且必须与 expected 完全一致 (防错配 round / operation
    串台 + stale payload 套到当前轮). agent 直接回显 llm_request_spec.correlation_id 即可.
    payload 缺失或非 dict → ValueError (调用方决定 fallback).
    """
    if not isinstance(raw, dict):
        raise ValueError(f"agent response must be dict, got {type(raw).__name__}")
    cid_raw = raw.get("correlation_id")
    if cid_raw is None:
        raise ValueError(
            "agent response 缺 correlation_id (F4: 必填, 防旧轮/stale payload 套到"
            "当前 round). 回传须为信封 {correlation_id, payload}, "
            "correlation_id 直接抄 llm_request_spec.correlation_id."
        )
    got = CorrelationId.decode(cid_raw)
    if got != expected:
        raise ValueError(
            f"correlation_id mismatch: got {got.encode()!r}, "
            f"expected {expected.encode()!r}"
        )
    payload = raw.get("payload")
    if not isinstance(payload, dict):
        raise ValueError(
            f"agent response payload must be dict, got {type(payload).__name__}"
        )
    disclosure = raw.get("disclosure")
    if not isinstance(disclosure, dict):
        disclosure = {}
    return AgentResponse(
        correlation_id=expected, payload=payload, disclosure=disclosure
    )
