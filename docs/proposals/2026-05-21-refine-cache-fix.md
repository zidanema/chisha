# Refine LLM cache 修复 — system/user 拆分 + ephemeral cache 启用

**日期**: 2026-05-21
**状态**: brief 草稿, **待 codex 共商方案**
**来源**: 2026-05-20 prompt review brief 附录 B Step 3 🔴 项, 用户拍板优先处理
**第一原则**: refine 是 L1 抽取层, prompt 模板 95%+ 是固定结构化指令, 真正变化的只有用户 refine 文本 — 这是 prompt cache 的教科书场景, 当前完全没启用是已识别的 bug.

---

## 1. Bug 起底

`chisha/refine_intent_v2.py:417-446` 自承认注释 (第 419 行原话):

> 但当前实现是单消息: 整段 prompt = system + user 混合放在 user role.

实际调用 (445 行):
```python
resp = call_text(final_prompt, max_tokens=1024, temperature=0.0,
                  json_mode=True, profile_llm=profile_llm)
# ❌ 没传 system=, 没传 cache_system=True
# ❌ final_prompt = prompt_template.replace("{INPUT_TEXT}", text) — 整段塞 user role
```

而对照组 `chisha/rerank.py:1127-1135` 早就是标准范式:
```python
kwargs = {
    "system": system_prompt,
    "cache_system": True,
    "profile_llm": profile_llm,
}
resp = call_text(user_msg, **kwargs)  # ✅
```

底层支持齐了 — `chisha/llm_client.py:117-165` `call_text(system=, cache_system=)`; `chisha/llm_providers/anthropic_api.py:42-46` 和 `openrouter.py:54-60` 都已实现给 system 加 `cache_control: {"type": "ephemeral"}`. refine 是**唯一漏网**.

---

## 2. 当前 trace 字段的"假拆"

`refine_intent_v2.py:428-437` 已经按"拆完" 落 trace:
```python
template_head, _sep, template_tail = prompt_template.partition("{INPUT_TEXT}")
trace_collector["system_prompt_full"] = template_head + template_tail  # 已存
trace_collector["user_message_full"] = text                              # 已存
```

但**真实调用是混的**, trace 数据**对不上实际 LLM 收到的内容** — 这是隐藏 trace 失真.

Trace 下游消费 (`chisha/trace_helpers.py:78-100`, `web_api.py:263`, debug-ui R2 round.refine_intent_llm) 完全按"拆完"姿态读, schema 不用动.

---

## 3. Fix 方案 (待 codex 拷问)

### 3.1 候选 A: system = head + tail (推荐草案)

```python
template_head, _sep, template_tail = prompt_template.partition("{INPUT_TEXT}")
system_prompt = template_head + template_tail  # head 含 "用户 refine 文本:\n```\n", tail 含 "\n```"
user_msg = text                                 # 纯用户输入

resp = call_text(
    user_msg,
    system=system_prompt,
    cache_system=True,
    max_tokens=1024,
    temperature=0.0,
    json_mode=True,
    profile_llm=profile_llm,
)
```

**优点**: trace `system_prompt_full` / `user_message_full` 与实际 LLM 收到的 1:1 对齐, 注释 419 行的"等迁移到 system/user 分离后这里语义自然" 真生效.

**疑问点 (留给 codex 拷问)**:
- (Q1) head + tail 拼起来时, 中间的 `{INPUT_TEXT}` 没了, 上下文是 `用户 refine 文本:\n\`\`\`\n` + `\n\`\`\`\n` — system 里有两个空 code fence, LLM 是否会困惑? 还是 user_msg = text 顺序上下来就自然?
- (Q2) Anthropic ephemeral cache 命中条件: system content **完全相同** (含 markdown 排版). head + tail 包含模板末尾 `## 现在开始` + ```` ``` ```` 等固定字符, 不含 INPUT_TEXT, 每次都一致 — 应该命中
- (Q3) 模板长度 ~180 行, ~6-8K tokens, 超过 Anthropic 1024 tokens 最小 cache 门槛 (确认), ROI 有

### 3.2 候选 B: system = head, user = text + tail

```python
system_prompt = template_head           # 不含末尾 fence 关闭
user_msg = text + template_tail         # 用户文本 + 末尾 fence
```

**优点**: 语义更自然 — system 一直说"接下来用户会发文本", user 发文本 + fence.

**缺点**: tail 现在是 `\n```\n` 这种**末端 fence**, 放在 user_msg 尾巴上看着像"截断". 但实际 LLM 解析没问题.

### 3.3 候选 C: 重排 prompt 模板, 把 `{INPUT_TEXT}` 挪到末尾或开头

例如改成模板末尾就是 `## 用户 refine 文本` 标题, 然后直接 `{INPUT_TEXT}` 收尾. system = template_head (含标题), user = text.

**优点**: 拆点最干净.
**缺点**: 动 prompt 文件本身, 行号会变, prompts/parse_refine_intent_v2.md 已经经过 T-PR-01/06 多轮微调, 改结构可能引入语义漂移. **本轮不推荐**, 留下次 prompt 写作 style guide 一起做.

**草案选 A**, 等 codex 共商.

---

## 4. 预期 ROI

| 指标 | 当前 | 预期 | 备注 |
|---|---|---|---|
| refine latency (P50) | 6-8s (D-089 实测) | 3-4s | 模板 cache 命中后 input_tokens 大头是 cached |
| input_tokens (cached) | 0 | ~5-7K (~95% 模板) | 仅 user_msg 走 fresh tokens |
| trace `cache_hit%` (debug-ui DagHeader) | 0% | >90% (二次调用起) | DagHeader 公式: cache_read / input_tokens |
| 月成本影响 | — | -50%~70% refine token 成本 | cache_read 是 fresh 价格 10% |

注: 首次调用必走 fresh (cache 写入), 第二次起命中. 5 分钟 ephemeral TTL 内连续 refine 命中率最高.

---

## 5. 风险

### 5.1 high-risk 文件白名单
- `chisha/refine_intent_v2.py` — 在白名单内, **CLAUDE.md 强制流程**: 设计 codex 共商 (本步) + commit 前 codex diff review

### 5.2 baseline_l2_snapshot 严格回归
- refine cache fix 不动 L2 打分链路 — 空 refine 路径必须 0 diff
- 但 refine 路径本身改了调用形式 (system/user 拆), **JSON 输出内容理论上不变** (相同模型, 相同 prompt 内容, T=0)
- **验证方法**: 跑 `scripts/eval_refine_intent.py` 43 case eval set, 准确率应保持 ≥ 85% (T-P1a-03 阈值)

### 5.3 多 provider 兼容
- anthropic_api / openrouter — 都已支持 cache_control, 直接生效
- **claude_code_cli** — 静默忽略 cache_system (`claude_code_cli.py:217`), 不破; 但 CLI 路径 cache 不会生效, 这是已知限制
- **deepseek-flash via OpenRouter** — D-047 + memory `chisha_l3_model_refine_intent_sensitivity` 提示 refine 默认 sonnet/opus, 但 OR 的 deepseek 不走 Anthropic cache 协议, **需 codex 确认**: deepseek-flash 当前是否被 refine 调用? 如果是, cache 命中 0% 但不破

### 5.4 trace 字段语义同步
- `refine_intent_v2.py:417-421` 注释承认"假拆", fix 后**必须改注释** (这次真就是 system/user 了)
- 字段名 `system_prompt_full` / `user_message_full` 不变 (rerank 已经这语义, 跨链路口径统一)
- `trace_helpers.py:78-100` schema 不动 (口径正确)
- debug-ui R2 round.refine_intent_llm 渲染**应该无变化** — 内容真实化了, schema 不动

### 5.5 单测
- `tests/test_refine_intent_v2.py` (T-P1a-03 落的 LLM extractor 单测) — mock `call_text` 的 patch, **签名要看是否 break** (新增 system=, cache_system= kwargs)
- `tests/test_refine_trace_persist.py` — trace 字段从 trace_collector 读, 不变
- 跑 `uv run pytest tests/test_refine_intent_v2.py tests/test_refine_trace_persist.py -q` 守门

---

## 6. 工程量粗估 + 子任务草拆 (待 /plan-brief)

| 任务 | 工作量 | high-risk | 内容 |
|---|---|---|---|
| T-PR3-01 · refine_intent_v2._llm_parse_v2 拆 system/user + cache_system=True | ~2h | **high** (refine_intent_v2.py) | 改 7-10 行代码, 同步 419-421 注释 |
| T-PR3-02 · 单测同步 (call_text mock 签名兼容) + 跑 43 case eval | ~2h | low | 守门: 准确率 ≥ 85% |
| T-PR3-03 · latency 实测对比 (改前 5-10 次 / 改后 5-10 次) + 落 baseline | ~1h | low | 给 D-095 决策做数据支撑 |
| **总** | **~5h** | 1 个 high-risk 文件 | |

---

## 7. 落地流程

1. **本文件 v1 草稿** = 本提交 (志丹拍优先级 + 起 brief, 等 codex 共商)
2. 志丹 review brief 内容
3. 调 `codex:rescue` 共商方案 — 重点拷问:
   - (Q1) head + tail 拼起来中间没了 INPUT_TEXT, system 里两个空 code fence 模型是否困惑?
   - (Q2) 候选 A vs B 哪个更稳? (A 1:1 对齐 trace, B 语义自然但 user_msg 带 tail fence)
   - (Q3) 当前 refine 是否有走 deepseek-flash 的实际场景? OR deepseek 走 Anthropic cache 协议吗?
   - (Q4) 单测 mock `call_text` 时, 新增 `system=` / `cache_system=` kwargs 会不会 break 已有 patch?
   - (Q5) D-089 trace 完整性约定下, fallback (无 LLM key / 超时) 路径的 cache 失效是否需要 trace 标记?
4. codex 共识达成 → `/plan-brief docs/proposals/2026-05-21-refine-cache-fix.md` → 拆 `specs/T-PR3-01.md` ~ `T-PR3-03.md` + 追加 `specs/tasks.json`
5. 志丹 review specs → subagent 执行
6. 所有 task done → 实测 5-10 次 refine latency + cache_hit% → 落 D-095 (正式)

---

## 附录 A: 当前 refine 调用代码片段 (2026-05-21)

```python
# chisha/refine_intent_v2.py:417-446
# parse_refine_intent_v2.md 不像 rerank 那样有 {INPUT_TEXT} 之外的动态部分,
# system_prompt 形态上等同 "整个 prompt 模板"; user_message 是 INPUT_TEXT 子串.
# 但当前实现是单消息: 整段 prompt = system + user 混合放在 user role.
# 落 trace 时分两段: prompt_template (== system_prompt_full),
# input_text (== user_message_full). 等迁移到 system/user 分离后这里语义自然.
prompt_template = ""
final_prompt = ""
try:
    from chisha.llm_client import call_text, _resolve_provider
    prompt_template = PROMPT_PATH_V2.read_text(encoding="utf-8")
    final_prompt = prompt_template.replace("{INPUT_TEXT}", text)
    if trace_collector is not None:
        template_head, _sep, template_tail = prompt_template.partition("{INPUT_TEXT}")
        trace_collector["system_prompt_full"] = template_head + template_tail
        trace_collector["system_prompt_chars"] = len(template_head + template_tail)
        trace_collector["user_message_full"] = text
        trace_collector["user_message_chars"] = len(text)
        # ...
    resp = call_text(final_prompt, max_tokens=1024, temperature=0.0,
                      json_mode=True, profile_llm=profile_llm)  # ❌ 缺 system= + cache_system=
```

## 附录 B: rerank 对照范式 (chisha/rerank.py:1127-1135)

```python
kwargs = {
    "max_tokens": 4096 if is_cli else 2048,
    "temperature": 0.0,
    "system": system_prompt,
    "cache_system": True,
    "profile_llm": profile_llm,
}
if not is_cli:
    kwargs["tools"] = [_RERANK_TOOL]
    kwargs["tool_choice"] = _RERANK_TOOL_CHOICE
resp = call_text(user_msg, **kwargs)
```
