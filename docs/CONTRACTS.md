# chisha · Agent 契约速查

> 主读者：Coding agent（Claude Code / Codex）每次会话。
> 装什么：**跨文件隐含约束** + **反直觉规则** + **系统级 invariant**——这些改错代码局部看不出，但会让管道静默错误或破坏产品行为。
> 不装：字段表 / schema keyset / prompt 行号 / 参数值 / 测试覆盖——这些 grep 代码就有。
> 决策原因看 [decisions.md](decisions.md)。当前文件只说"必须这样"，不解释"为什么"。

---

## 推荐链路 (L1 / L2 / L3)

### L1 召回
- **`hard_max_*` 和 `prefer_max_*` 不能混。** `hard_max_*` 真硬过滤超就砍；`prefer_max_*` 是软偏好进 L2 打分。改 `recall.py` 把任一软约束升级成硬过滤前，必须在 decisions.md 加一条说明（参 D-041）。
- **combo 数量 (2/3/4 道) 由 `profile.recall` 注入，不在代码 hardcode。** 改 combo 生成时不要写魔术数字（参 D-040）。

### L2 打分
- **`apply_caps()` 只返回 head 段，不带 tail。** brand cap=2 真正生效在 L2，**不能下放到 L3 prompt**（"输入里可能含多变体请择优"是错的方向，会让 cap 失效，参 D-049）。
- **改 `score.py` / `methodology.py` / spec yaml 前后必跑回归：** `uv run python -m scripts.baseline_l2_snapshot --out-dir tmp/baseline_traces`（改前）+ 改后再跑 + `compare_traces`。top60 顺序 + 16 维 breakdown `|delta| < 1e-6` 才允许 commit（参 D-072.1）。
- **methodology spec 只搬运不改逻辑。** 改打分逻辑 / 调权重 / 加新维度走 `score.py` + decisions 修订，**不走 spec**。spec 是 yaml 化的 `V2_DEFAULT_WEIGHTS`，不是新接口（参 D-072）。

### L3 精排
- **L3 输入 = top60。** 不是 40 / 100。如果输入大小要改，先看 D-046 的边界论证再动。
- **`config_error` 必须 hard-fail，不能被外层 `except Exception` 吞成 fallback。** 否则用户以为在跑 L3 实际没跑。改 `_resolve_provider` / `_run_llm_rerank` 时保持 `status="config_error"` + `resolved_provider=None` 透传到 trace（参 D-048）。
- **`_patch_system_prompt_for_cli` 找不到 `# 输出方式` 段必须 ValueError。** 防 prompt 改标题层级后 CLI 静默继续用 tool_use schema（CLI 不支持，会全失败）。
- **L3 一次性 retry-with-feedback，二次失败立刻走规则 fallback。** 不动不动重跑（CLI 成本敏感，参 D-050）。
- **`enforce_brand_unique` 在 L3 出口保留兜底**：同 brand 不同分店不能同时出现在最终 5 条。

### Provider 抽象
- **CLI provider 不支持 tool_use。** rerank 层做分流：`anthropic / openrouter` 走 tool_use forced schema；`claude_code_cli` 走 prompt + JSON 解析。不要试图统一 schema（参 D-038/D-048）。
- **`fallback_rerank` 规则路径必须永远可调用。** V1 简化路径已删 (D-049)，V2 是唯一推荐链路，但 V2 翻车时降级靠的是 fallback_rerank，不是恢复 V1。

---

## Refine / Mood

- **`infer_refine_mood` 只服务 `want_soup`。** 不许扩为通用 mood parser。新心情维度走 refine 自由文本或 L3 prompt，**绝不在前端加 mood chip**（参 D-071）。单测 `test_refine_mood.py` 有 8 case 守门。
- **explore 默认开启（top 5 中 1-2 个），refine 路径关闭。** 用户已主动给方向就不要再 explore（参 D-015）。

---

## Profile / 学习

- **`personal_offsets` 粒度 = `(cuisine, cooking, ingredient)`，不是 `店::菜`。** 改 offsets 写入 / 读取时不要回退到单菜粒度（参 D-025）。
- **`learned_profile` 用统计聚合，不用 LLM 蒸馏。** 如果要做 LLM 推理，输出只能作为 prompt 上下文，**不能作为 source of truth**（参 D-026）。
- **`taste_description` 自然语言字段，不要结构化拆分。** 想加结构化字段先看 D-014 为什么砍（仅 oil_level / protein_g 这种打分硬维度可结构化）。

---

## 反馈 (V1.1)

- **已提交 feedback record = 永久 readonly。** 不能 in-place 修改 ratings；后续走 `comments` append-only timeline（参 D-066/D-067）。改 `feedback_store.py` 时如果引入 mutation API 就是 bug。
- **三类信号语义不可混：** `gut`（-1/0/1）/ `calibration`（reason_match, oil_calibration）/ `behavior`（fullness, repurchase_intent）。schema 字段对应固定类别，不要新增字段时跨类（参 D-063~D-065）。
- **`comments` 不直接进打分。** 可作为 LLM 推理上下文，但 numeric ranking signal 只来自 structured ratings。

---

## 数据 / 打标

- **打标 LLM 必须看到价格。** 改 `tag_dishes.md` prompt 不要为了省 token 砍价格字段（参 D-008）。
- **生产打标默认 = `deepseek-v4-flash` (via OpenRouter)。** 想换模型先在 `eval/dish_tagging_eval/` 跑双模型对比，准确率持平再换（参 D-036/D-037）。
- **数据按 office_zone 拆，不混合**（`data/shenzhen-bay/` ≠ `data/home/`），recall 时按 profile.zones 切换。

---

## 调试台

- **调试台 = 独立 FastAPI on `:8765`，与主推荐链路解耦。** 调试逻辑不要混进生产代码 (`chisha/api.py`)。改打分链路时检查 `chisha/debug_recommend.py` 的 instrumented 管道还能跑（参 D-039）。

---

## 范围红线 (Phase 0 内不做)

不要在 Phase 0 内启动以下工作（已被推迟到 Phase 1+，避免 scope creep）：
- data zone 拆包发布 PyPI
- OpenClaw / Hermes 接入（待 D-074 草稿落定）
- screener 设计 / 同事推广前的注册流
- 第二份 methodology spec（减脂 / 糖控变体）
- 调试台 React 化

如果某 PR 触及上面任一项，先回头读 ROADMAP + decisions.md 确认是否真的要提前。
