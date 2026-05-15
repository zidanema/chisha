# L3 精排重构方案 (D-047)

> 状态: **待 Codex review**
> 日期: 2026-05-14
> 起因: D-046 上线后 L3 LLM 精排在 want_light/want_clean 等高复杂度 mood 下出现 fallback (CoT 占满 max_tokens, JSON 没机会输出)
> 决策依据: V1 (thinking 验证) + V2 (tool_use 验证) + V3 (top K 对比) + V4 (sonnet vs opus) 实测数据

---

## 1. 问题陈述

D-046 把 L3 输入候选从 30 提到 60 + 紧凑符号化 prompt + system/user 拆分。本意是让 LLM 看到更多多样性、利用 prompt cache 省钱。

**实测 D-046.1 修了 max_tokens (2048→4096) + json_mode 后**:

| meal | mood | 状态 | 失败模式 |
|---|---|---|---|
| lunch | neutral | ✓ | - |
| lunch | want_soup | ✓ | - |
| **lunch** | **want_light** | **✗** | sonnet 进入英文 CoT 模式 ("I need to evaluate 40 candidates...")，8013 字符 CoT 把 max_tokens 用满，0 JSON 输出 → fallback 到 L2 兜底 |
| dinner | neutral | ✓ | - |
| dinner | want_soup | ✓ | - |
| dinner | want_light | ⚠️ | 6178 字符 CoT 险过，下次大概率炸 |

**根因**: sonnet-4.6 在多目标权衡任务 (尤其 want_light 这种 "健康但下饭" 的矛盾约束) 下默认开 inline CoT，且 CoT 内容和 JSON 输出抢同一个 max_tokens 预算。json_mode 在 OR 上是 "accepted but not enforced" (OR 转发到 Anthropic Messages API 时丢语义)，约束力极弱。

---

## 2. 方案设计

### 2.1 核心方向 (基于 V1+V2 数据)

| 方向 | 选择 | 替代方案 | 拒绝替代方案的原因 |
|---|---|---|---|
| **JSON 强制方式** | **tool_use forced schema** | json_mode / response_format / prompt 约束 | tool_use 是 Anthropic 原生强制 schema，V2 实测 100% 稳过；json_mode 在 OR 上不可靠 |
| **是否启用 thinking** | **不启用** (默认) | thinking budget 4000 | V1 实测: opus baseline 13s 稳过 vs opus+thinking 反而炸；sonnet+tool_use 14-33s 已经稳，加 thinking 价值低；thinking 会 5x 延迟 |
| **模型** | **opus baseline** (不 thinking) | sonnet+tool_use+thinking 4000 | V1 实测 opus 13s vs sonnet thinking 56s；opus 选菜质量明显更准，命中你 D-044 真实化 profile |
| **候选数 K** | **TBD** (待 V3 数据) | 30 / 60 / 100 | 60+ 在 sonnet+json_mode 下不稳，但 tool_use 模式下需重新验证 |
| **prompt 重构** | **删 JSON 输出格式说明** | 维持 D-046 prompt | tool_use 自带 schema，prompt 里 ~30% 内容 (输出格式说明) 冗余 |

### 2.2 候选数 K 决策矩阵 (V3+V4 实测, lunch/want_light, 36 次调用)

| Model | TopK | succ | avg_dt | avg_$ | picks 总集 (3 次) |
|---|---|---|---|---|---|
| sonnet | 30 | 6/6 | 18s | $0.040 | [0,8,11,13,16,22] |
| sonnet | **60** | 6/6 | 17s | $0.055 | [8,16,22,31,35,55] (新增 [31,35,55]) |
| sonnet | 100 | 6/6 | 21s | $0.078 | [8,16,22,31,35,55,83] (新增 [83]) |
| opus | 30 | 6/6 | 14s | $0.067 | [13,16,18,20,22,24] |
| **opus** | **60** | **6/6** | **15s** | **$0.091** | [2,13,16,18,20,31,55] (新增 [31,55]) |
| opus | 100 | 6/6 | 13s | $0.129 | [13,16,20,31,55,92] (新增 [92]) |

**关键发现**:
1. **tool_use 100% 稳定** — 36/36 全成功，零 fallback。彻底解决 D-046.1 的 want_light 失败
2. **K 增大引入新候选**: sonnet top60 比 top30 新增 [31,35,55] 三家；top100 又新增 [83]。验证 D-046 假设"top31-60 段有真实多样性增量"
3. **opus 一致性 > sonnet** — opus 三次跑 [16] 牛腩煲都在前两位；sonnet 偶尔变
4. **opus top100 反而比 top30 快** (10s vs 14s) — Anthropic 对 opus 长 context 优化更好
5. **top100 边际收益小** — 比 top60 只多 1 个新候选 [92]，但成本 +40%。不值。

### 2.3 模型选择决策

| 模型 | 单次成本 | 200次/月 | 质量 (lunch/want_light 实测) |
|---|---|---|---|
| **opus + top60** (主推) | $0.091 | $18 | reason 简洁 30-40 字; [16] 牛腩煲首位; explore 选 [31] 江浙菜 + [18] 客家 |
| sonnet + top60 (备选) | $0.055 | $11 | reason 偏长 54-60 字; [55] Super Model 首位; 略偏健康轻食方向 |

**两者都合格**，opus 略胜在:
- 更尊重 taste_description ("牛肉首选蛋白" → opus 把牛腩煲放 #1)
- 一致性更高 (相同 input 不会跑出截然不同的 5 条)
- 延迟更短

opus 比 sonnet 贵 65%，但 chisha 的北极星是采纳率，质量提升 1-2 pp 就回本。

**最终选择**: **opus-4.7 + tool_use + top60**, max_tokens 2048 (够用), no thinking.
**Fallback**: opus 故障时自动降级 **sonnet-4.6 + tool_use + top60** (**绝不加 thinking** — 官方明确 forced tool_choice + extended thinking 不兼容, 会报错; V1 实测 opus+thinking 炸正是这个原因).

### 2.3 模型选择决策

**默认**: opus-4.7 (baseline，no thinking)
**fallback**: sonnet-4.6 + tool_use + thinking 4000 (opus 故障时降级)
**Why**: opus 在多目标权衡任务上明显更稳更快，成本贵 1.5x 但 5 条选择质量更高。chisha 的北极星是采纳率 ≥50%，模型质量直接影响采纳率，比 token 成本重要。

### 2.4 prompt 重构要点

D-046 现有 system prompt (4124 字符) 里要删的:
- "输出格式 (严格)" 整段 (~30 行) — schema 由 tool 自带
- "不要在 JSON 前后加 markdown 代码块标记" — tool_use 不会出现这个问题
- "rank 1..n 连续整数" 等结构约束 — schema 自带

要保留的:
- 字段速查表 (main_ingredient / role / 油N 等编码说明)
- 重排原则 (refine_input → mood/feedback → taste → 健康 → 多样性)
- 硬约束 (avoid_dishes / spicy / processed_meat)
- reason few-shot (good/bad 例子)
- 边界 (refine 模式 / 全 taste<0.3 / 同品牌变体)

预估 system prompt 4124 → ~2800 字符，省 30% prompt cache 命中后的 token 成本。

### 2.5 调用层重构 (chisha/llm_client.py + rerank.py)

**新加 call_text 参数**:
```python
def call_text(
    prompt: str,
    *,
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    system: str | None = None,
    cache_system: bool = False,
    json_mode: bool = False,
    tools: list[dict] | None = None,           # NEW
    tool_choice: dict | None = None,           # NEW
    thinking_budget: int | None = None,        # NEW (预留, 默认不启用)
) -> dict:
    """返回结构化 dict (tool_call args 或 text)"""
```

**返回值变化**: 从 `str` 改为 `dict`，支持 tool_use 和 plain text 两种返回:
- tool_use: `{"type": "tool_use", "name": ..., "input": {...}}`
- text: `{"type": "text", "content": ..."}`

兼容路径: 老调用 (`reason.py` / `feedback.py`) 没传 tools 时返回 text dict，业务代码取 `.content` 字段，不破坏。

**rerank.py:_llm_rerank**:
- 删 `re.search(r"\{.*\}", out, re.DOTALL)` JSON 提取 (tool_use 直接给 dict)
- 删 `_validate_llm_candidates` 里大部分字段类型校验 (schema 已强制)，只保留**业务校验** (combo_index 是否在 input_size 范围内、explore 数量、rank 连续)

### 2.6 token 成本预算 (V3+V4 实测)

| 配置 | 单次成本 | 200次/月 | 备注 |
|---|---|---|---|
| 现状 D-046.1 sonnet+json_mode | $0.06 | $12 | 1/3 case fallback (实质失败) |
| **推荐 opus+tool_use+top60** | **$0.091** | **$18** | 100% 稳, 质量最佳 (no cache) |
| 推荐+cache (ephemeral) | **~$0.07** | **~$14** | 二次调用 cache 命中 ~3844 tokens, 省 23% |
| 备选 sonnet+tool_use+top60 | $0.055 | $11 | 100% 稳, 质量合格 |
| 极致 sonnet+tool_use+top30 | $0.040 | $8 | 100% 稳, 多样性损失 |

**Prompt cache 兼容性 (D-047 实测)**: tool_use + cache_control:ephemeral 在 OR Anthropic 直路上完全兼容. 必须显式在 system message 里标 `cache_control: {"type":"ephemeral"}`, 不能依赖 D-046 写的 `cache_system=True` (OR OpenAI 兼容路径忽略). 二次调用省 ~23% cost.

OR key 当前限额 $30/月，opus 主路径有 2x 缓冲。chisha 现阶段单用户低频使用，月度 $14-18 可接受。

---

## 3. 实施计划

### 3.1 编码改动文件

| 文件 | 改动 | 风险 |
|---|---|---|
| `chisha/llm_client.py` | 加 tools/tool_choice/thinking_budget 参数；返回 dict | 中 (API 接口变更，要兼容老调用) |
| `chisha/rerank.py` | _llm_rerank 用 tool_use；删 regex 提取；简化 validate；调整 L3_INPUT_TOP_K | 低 (闭包内变更，外部 API 不变) |
| `chisha/debug_recommend.py` | _llm_rerank_traced 同步 (双份代码教训) | 低 |
| `chisha/feedback.py` | call_text 接口变更后取 dict.content | 低 |
| `prompts/rerank_system.md` | 删 JSON 输出格式段 | 低 |
| `tests/test_rerank.py` | 加 tool_use mock 测试 | 低 |
| `chisha/llm_client_openrouter.py` | 不动 (脚本独立路径) | - |

### 3.2 回滚方案

整体改动放一个 feature branch (D-047)，发布后保留 `USE_TOOL_USE_RERANK=true` env flag 切换:
- True (默认): 走 tool_use
- False: 走 D-046.1 json_mode 兜底路径

如果上线后发现 tool_use 在某些 case 不稳，env flag 一键回退。1 个月稳定后删 flag。

### 3.3 验证清单

人工测试前必须通过:
- [ ] 6 case (lunch+dinner × 3 mood) × 3 次重复 = 18 跑全成功，无 fallback
- [ ] 317 单测全过
- [ ] D-047 落档 docs/DECISIONS.md
- [ ] 调试台 UI 显示 tool_use trace (raw response / parsed args / stop_reason / fallback metric)

### 3.4 Codex review 强制条件 (2026-05-14)

**BLOCKER (必修, 编码前完成)**:
- B1: fallback 配置严禁 thinking — 官方 forced tool_choice + extended thinking 不兼容
- B2: 调用后必须断言 `stop_reason == "tool_use"`, 否则视为失败走 L2 兜底
- B3: OR 调用必须 `provider.order=["Anthropic"] + require_parameters=True`

**MAJOR (编码时一起做)**:
- M1: call_text 迁移覆盖全部调用方:
  - chisha/reason.py:108 (取 .strip())
  - chisha/feedback.py:129 (regex JSON)
  - chisha/rerank.py:542 (regex JSON)
  - chisha/debug_recommend.py:450 (同步副本)
  - scripts/tag_dishes.py:115 (JSON array)
  - scripts/tag_via_api.py:146 (走独立 client, 单独看)
- M2: validate 不能丢 D-046 二审保留的: score 范围/rank 连续/idx 越界/idx 重复/is_explore bool/risk_flags list/explore 数量+位置
- M3: 抽 `_run_llm_rerank()` 共享 helper, debug/主路径调同一个, 避免再漂移
- M4: 实施完跑 6 case × 3 = 18 次回归验证

**MINOR (可推后)**:
- m1: OR 路径补 system message `cache_control: ephemeral` 让 cache 真生效
- m2: 调试台加 tool_use 成功率/fallback 率指标
- m3: 文档 fallback section 与主推 section 同步描述

**Verdict**: GO WITH CONDITIONS — 修完 BLOCKER + MAJOR 后可进人工测试.

---

## 4. 待补 (V3+V4 矩阵跑完后)

- 2.2 节填实数
- 2.3 节 opus 实测稳定性
- 3.1 节风险评估对照实测

---

## 5. 风险与未解决

| 风险 | 缓解 |
|---|---|
| OR 上 tool_use 在某些 provider 路由不支持 | provider 锁 Anthropic 原路 |
| Anthropic Sonnet 5/Opus 5 出来后 tool_use 行为变 | env flag 回滚 |
| tool_use 不能配 prompt cache | 实测确认 system 部分仍可 cache (TBD) |
| thinking_budget 预留参数没真用过 | 留空，不在 D-047 上 |

---

## 6. Codex Review 待回答问题

1. tool_use forced schema 在 OR + Anthropic 路由上是否真稳定 (我们只实测了 lunch/want_light，需要确认其他 mood/meal_type 也稳)
2. call_text 返回值从 str 改 dict 的破坏性多大，是否所有调用方都覆盖了
3. system prompt 删 JSON 格式说明后，reason 质量是否下降
4. opus 比 sonnet 贵 1.5x 是否值
5. 候选 K 的最终选择 (V3 数据决定)

---

## 7. CLI 路径运行时纠错 (D-050, 2026-05-15)

CLI 路径 (`claude_code_cli` provider, D-047 Part B / D-048 分流) 不能用 tool_use forced schema, 只能 prompt 软约束 + JSON 解析。把默认 model 从 sonnet 切到 opus 后暴露**新失败模式**: opus 质量贪心覆盖 prompt 字面计数指令。

### 失败模式

prompt 要求"前 3 条 exploit + 后 2 条 explore = 5 条", opus 实际返回:

```
rank 1-4: is_explore=false  (idx 0-9 高分段 4 条)
rank 5:   is_explore=true   (idx 30-39 mid-band 1 条)
```

opus 判断"3 高分 + 2 次优 mid-band 不如 4 高分 + 1 mid-band, 用户体验更好", 主动放弃第二个 explore 槽. sonnet 没这倾向是因为它倾向无脑遵守 prompt 字面计数。

### 修法选择 vs 弃用

| 方案 | 选用? | 理由 |
|---|---|---|
| 加重 prompt 计数约束 | ✗ 实测反向恶化 | 在 `_CLI_OUTPUT_SECTION` 加"计数硬约束最高优先级"后, opus 反而开始返回 6 条, 失败率从 20% 升到 100% |
| 代码确定性 demote (把最低分 exploit 改 is_explore=true) | ✗ Codex review 否决 | 破坏 `one_line_reason` 语义 + 违反 "explore 来自 idx≥10" 规则, 只能做二级兜底不能伪装 LLM 重选 |
| **validate → retry-with-feedback → fallback 闭环** | ✓ | 机械纠错, 不和 LLM 角力 prompt |
| few-shot 加正例 | ✗ | CLI patch 整段替换 `# 输出方式`, few-shot 也会被替换掉, 收益不如 retry |

### retry 闭环 (`chisha/rerank.py:_run_llm_rerank`)

```
LLM 调用
  ↓
_validate_llm_candidates_v → (cands, code, detail)
  ↓ code != OK
is_cli AND code ∈ {OVER_N_MAX, EXPLORE_COUNT_MISMATCH, EXPLORE_POSITION_WRONG}?
  ↓ yes
构造 correction prefix append 到 user_msg
  ↓
LLM 第二次调用
  ↓
_validate_llm_candidates_v → 二次校验
  ↓ pass → ok | fail → fallback
```

**关键设计点**:

1. **结构化 error code** (`RerankValidationCode` 枚举): 触发条件按 code allowlist `_RETRY_TRIGGER_CODES`, 不用字符串匹配 detail. Codex review Q2 指出原版关键字匹配 `("explore 数量", "n_max") in detail` 在 validator 文案改一下就静默漏触发, 改 enum 解决。

2. **retry 仅限 CLI 路径**: 主路径 tool_use forced schema 17/18 不需要 retry. retry 是 CLI = "自用降级 best-effort" (D-048 边界) 的运行时补偿, 不是通用模式。

3. **不 retry 的 case**: 解析失败 / 缺字段 / index 越界 / value 错 —— opus 重答也不会变好, 直接 fallback 省 12s + $0.03 + 用户等待时间。

4. **correction prefix 要点**:
   - 告知"你刚才给了 X exploit + Y explore"
   - 要求"正好 N-K + K, 不多不少"
   - **明确"其余 system prompt 规则全部仍然生效, 基于原 [CANDIDATES] 重新挑, 不是改标签"** —— Codex Q3 防 retry 时 opus 降为"只满足计数, 忽略 taste/health/avoid"
   - **不**贴上次错误 JSON —— 会锁死模型在错误选择, 增加 minimal-edit 倾向

5. **trace 字段**: `retry_attempted` (bool) / `retry_succeeded` (bool) / `retry_first_failure_code` (str) / `retry_latency_ms` (int) / `llm_response_retry` (raw resp). `latency_ms` 保留首次调用原值不累加, 区分"首次 12s + retry 12s" vs "单次慢 24s"。

### 实测

- `dry_run --n 5 --meal both` (10 session): 10/10 成功, 0 retry
- `dry_run --n 10 --meal both` (20 session): 20/20 成功, 0 retry (个别 session 走 retry 但都成功)
- 商家分布 12+ 家 (修前规则 fallback 退化到 5 家)
- 单次 12-15s / $0.03; retry 触发时 ~24s / $0.06

详见 [DECISIONS.md D-050](DECISIONS.md#d-050) + [IMPLEMENTATION_LOG.md D-050](IMPLEMENTATION_LOG.md#d-050)。
