# plan-brief Codex audit · prompt-effect-optimization

## 强制改动

### T-PR-01
- 粒度偏大但可接受: 6 项都只改 `prompts/parse_refine_intent_v2.md`, 且覆盖 P0-E3/P1-1/P1-2/P1-3/P1-7/P1-8 (`specs/T-PR-01.md:7-14`)。
- 与 brief 拆分有漂移: brief 把 `raw_understanding` 放在 T-PR-06 (`docs/proposals/2026-05-20-prompt-effect-optimization.md:121`), spec 改放 T-PR-01 (`specs/T-PR-01.md:12`)。这不是漏项, 但应在 tasks/spec 标题里显式说明是按同文件合并。
- affected file 存在: `prompts/parse_refine_intent_v2.md` 已 grep 到, 且对应字段段存在 (`prompts/parse_refine_intent_v2.md:24-77`)。
- regression_risk=medium 合理: 只动 prompt, 不触 CLAUDE high-risk 12 文件 (`CLAUDE.md:66-75`)。

### T-PR-02
- 依赖 T-PR-01 合理: 这些 fixture 是守门 T-PR-01 的 prompt 边界, 若先跑会因 prompt 未改而失败 (`specs/T-PR-02.md:7-20`, `specs/tasks.json:242-249`)。
- affected files 存在: `tests/test_refine_intent_v2.py` 和 `tests/refine_eval/eval_set.jsonl` 均存在; spec 的 "或类似目录" 可在实施时 grep 确认 (`specs/T-PR-02.md:40-43`)。
- Done When 可观测: 至少 4 条断言、默认 CI 不跑真 LLM、全测试全绿 (`specs/T-PR-02.md:28-33`)。
- regression_risk=low 合理: 只改测试/eval fixture, 不改 refine 运行链路。

### T-PR-03
- affected file 存在: `prompts/rerank_system.md` 存在, 健康 §6 原文在 `prompts/rerank_system.md:23-31`。
- 越界风险已被红线压住: spec 明确不新增 hard filter (`specs/T-PR-03.md:40-45`), 对齐 S2 强反对 (`docs/proposals/2026-05-20-prompt-effect-optimization.codex-review.md:115-123`)。
- regression_risk=medium 合理: 只动 L3 prompt 文案, 不改 `chisha/rerank.py`。
- 必改: `specs/tasks.json` 不应让 T-PR-04 depends_on T-PR-03 (`specs/tasks.json:260-267`)。二者同改 `prompts/rerank_system.md` 但语义独立, 这是串行/冲突规避偏好, 不是真依赖。

### T-PR-04
- coverage 完整: 覆盖 P0-E1 和 S2 新盲点 #1/#2, 包括 V1 字段口径、`avoid_pattern` 死路、unsupported narrative 约束 (`specs/T-PR-04.md:7-18`)。
- affected file 存在: `prompts/rerank_system.md` §2 在 `prompts/rerank_system.md:23-31`; `chisha/rerank.py` 实际注入在 `chisha/rerank.py:490-499`。
- regression_risk=medium 合理: 只动 L3 prompt, 不改 high-risk 文件。
- 必改: T-PR-04 的 depends_on=T-PR-03 是顺序偏好, 不是语义依赖 (`specs/tasks.json:264-266`)。若需要避免同文件冲突, 用执行顺序说明, 不要写 depends_on。

### T-PR-05
- regression_risk=high 正确: 改 `chisha/rerank.py`, 命中 CLAUDE high-risk 12 文件 (`CLAUDE.md:66-75`; `specs/T-PR-05.md:37-45`)。
- affected files 存在: `_RERANK_TOOL` / `_CLI_OUTPUT_SECTION` 在 `chisha/rerank.py:52-137`, `prompts/rerank_system.md` 输出段在 `prompts/rerank_system.md:64-83`。
- Done When 可观测: schema properties/required 零变化、CLI 锚点测试、baseline_l2_snapshot 0 diff (`specs/T-PR-05.md:22-30`)。
- 必改: T-PR-05 depends_on=T-PR-04 也只是同文件/同主题串行偏好 (`specs/tasks.json:274-276`)。没有真实数据或接口产物依赖, 应移除或改成非依赖的执行顺序备注。

### T-PR-06
- coverage 基本完整: taste_match rubric、one_line_reason、explore escape 覆盖 S2 落地建议 #6 和 P1-5 (`specs/T-PR-06.md:7-28`)。
- affected file 存在: `prompts/rerank_system.md` 字段/narrative/边界段存在 (`prompts/rerank_system.md:73-94`, `prompts/rerank_system.md:114-123`)。
- regression_risk=medium 合理: 只动 prompt。
- 必改: T-PR-06 depends_on=T-PR-05 是顺序偏好, 不是真依赖 (`specs/tasks.json:284-286`)。同时 T-PR-03/04/05/06 都改 `prompts/rerank_system.md`, 必须串行执行或明确 rebase 策略, 但不应伪装成 depends_on。

### T-PR-07
- 粒度可接受但范围要收窄: 作为整体验收 gate 合理, 覆盖 tests、CLI 锚点、baseline、人工对比 (`specs/T-PR-07.md:7-25`)。
- 必改: 不要把 "完成日期 + 关联 commit" 写回 `docs/proposals/2026-05-20-prompt-effect-optimization.md` (`specs/T-PR-07.md:26`, `specs/T-PR-07.md:38-40`)。CLAUDE 文档纪律明确 commit hash / 测试列表 / 文件改动清单不写文档, 以 git log + grep 为准 (`CLAUDE.md:19-24`)。
- 必改: affected files 应删除 proposal 修改项, 保留 `plans/T-PR-07.review.md` + 临时 baseline 目录即可 (`specs/T-PR-07.md:47-51`)。
- regression_risk=low 合理: 若移除 proposal 写回, 只做验证和 plan 留档; depends_on T-PR-01~06 是真依赖 (`specs/tasks.json:290-303`)。

### 全局漏项 / 越界 / 文件存在性
- S2 7 个落地建议均已覆盖: #1=T-PR-01, #2=T-PR-02, #3=T-PR-03, #4=T-PR-04, #5=T-PR-05, #6=T-PR-06, #7=T-PR-07 (`docs/proposals/2026-05-20-prompt-effect-optimization.codex-review.md:148-162`)。
- brief P1-9 已覆盖 ordering description + CLI no-tool (`docs/proposals/2026-05-20-prompt-effect-optimization.md:108`, `specs/T-PR-05.md:7-15`)。
- 未发现撞 ROADMAP 已砍/V2/V3: 当前任务限 prompt/test/rerank schema description, 不触 data zone、外部 Agent、screener、methodology spec、L1 词表扩等红线 (`docs/ROADMAP.md:163-167`; `docs/CONTRACTS.md:138-147`)。
- 三个用户点名文件均存在: `prompts/parse_refine_intent_v2.md`, `prompts/rerank_system.md`, `chisha/rerank.py`。

## 可讨论建议

### T-PR-01 / T-PR-06 分工
- 现在把 `raw_understanding` 从 brief T-PR-06 移到 T-PR-01 是合理工程合并: 同属 `parse_refine_intent_v2.md`, 可减少跨任务冲突。
- 建议在 T-PR-06 的 What/不做里保留一句 "raw_understanding 已由 T-PR-01 覆盖", 避免 reviewer 按 brief 行 121 误判漏项。

### T-PR-03 → T-PR-04 → T-PR-05 → T-PR-06 冲突
- 四个任务都可能改 `prompts/rerank_system.md` (`specs/T-PR-03.md:36-38`, `specs/T-PR-04.md:39-41`, `specs/T-PR-05.md:37-40`, `specs/T-PR-06.md:52-54`)。
- 建议保留串行执行顺序 03→04→05→06, 但不要用 `depends_on` 表达; 用 `implementation_order` / `_notes` 更准确。
- T-PR-05 同时改 `chisha/rerank.py` 和可能改 prompt 输出段, 最容易与 T-PR-06 的字段说明相邻冲突, plan 里应要求先读最新 prompt 再 patch。

### Plan 规模预判
- T-PR-01 虽是单文件, 6 处文案 + 实测 case 容易让 plan 写长; 仍应能压在 ≤200 行, 但计划需按 6 个 bullet 逐条映射。
- T-PR-05 因 high-risk + schema 零变化证明 + baseline 说明, plan 最容易接近 200 行; 建议把验证矩阵写短, 避免复述整段 schema。
- T-PR-07 若保留人工对比、baseline、全测试、review 留档, plan 仍可 ≤200 行; 不应再包含 proposal 收口写回。

### Done When 质量
- 大多数 Done When 可观测; T-PR-04 的人工对比 "narrative 不出现已过滤" (`specs/T-PR-04.md:32`) 需要明确记录样例输出位置, 否则 review 难复核。
- T-PR-01 的两条 "实测 refine 文本" (`specs/T-PR-01.md:29-30`) 若调用真 LLM, 需标明本地人工验证, 不作为 CI 必过断言; CI 守门应落到 T-PR-02。

## 结论

🔧 需要 Opus 改一轮

原因: 覆盖面基本完整、文件存在、风险评级大体正确, 但 `depends_on` 把同文件串行偏好写成了任务依赖, 且 T-PR-07 要把 commit hash/完成标记写回 proposal, 与项目文档纪律冲突。修完这些元数据和范围问题后, 可以进志丹 review。
