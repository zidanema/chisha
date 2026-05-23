# prompts/ · 索引

> Prompt 是**代码资产** (被 Python 直接读), 非文档。改 prompt = 改链路, 走代码评审。
> 新增/废弃 prompt 时改这一处, 防腐化。

## 当前 prompts

| 文件 | 状态 | 加载点 | 相关决策 |
|---|---|---|---|
| `l1_extract.md` | active | `chisha/l1_extractor.py:34` | D-076 (L1 长期偏好) |
| `parse_refine_intent_v2.md` | active | `chisha/refine_intent_v2.py:34` | D-080~D-085, D-094 (Faithful Refine 主输出, L3 + trace 双存消费) |
| `parse_refine_intent.md` | active (并行, 待退役) | `chisha/refine_intent.py:33` | 每次 refine 跟 V2 并行调; 下游 recall/score 消费窄枚举字段; 退役计划见 specs/T-FR-V1-RETIRE.md |
| `parse_feedback.md` | legacy | `chisha/feedback.py:18` | D-073 已被 refine_intent V2 取代; `parse_feedback()` 无 live caller, `CHIP_VOCAB` 仍被 openclaw 引 |
| `rerank_system.md` | active | `chisha/rerank.py:32` | D-046/D-047/D-048/D-049, T-PR-01~07 |
| `rerank_user.md` | template (仅供人对照) | 不加载, 实际 user message 由 `rerank.build_user_message()` 拼 | — |
| `tag_dishes.md` | active | `scripts/tag_via_api.py`, `scripts/tag_dishes.py` | D-036/D-037 (dual-model audit, deepseek-v4-flash) |
| `tag_dishes.v3.pre_dual.md` | **archive** | 无加载点 | D-036 之前备份; git 可溯源, 待评估删除 |

## 纪律

- 新增 prompt: 加文件 + 在上表加一行 (文件 / 状态 / 加载点 / 相关 D-XXX)
- 废弃 prompt: 状态改 `archive` + 等下一次清理直接删 (git log 即权威)
- 本地阅读用 PDF/导出文件: 由根 `.gitignore` 屏蔽 (`prompts/*.pdf`), 不提交
