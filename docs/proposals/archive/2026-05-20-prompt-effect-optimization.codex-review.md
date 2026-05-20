# Codex 对抗审 (S2)

**日期**: 2026-05-20
**输入**: Opus 设计稿 v1
**verdict**: 需修正后落地。Opus 抓到若干真实 prompt 风险，但 P0 范围混入 L1/L2 改造、部分 schema 建议会破坏 D-079 trace 兼容，不能按原分级直接执行。

## 1. Opus findings 逐条评估

### A. `parse_refine_intent_v2.md`

#### P0-1: 「不联想」vs `cuisine_candidates_expanded` / `ingredient_synonyms`

**判断**: 修正。

**同意的问题**: prompt 内部确实有张力。第一原则禁止主观联想，仅允许字面 + 直接同义词 (`prompts/parse_refine_intent_v2.md:10`)，但 schema 要求 LLM 推断 `"辣"→["川菜","湘菜","贵州菜","重庆菜","韩式"]` 和 `"肉"→["排骨","牛肉","猪肉","鸡","鸭","羊"]` (`prompts/parse_refine_intent_v2.md:31`, `:34`)。冲突例又要求对应 slot 全空，包括 expanded (`prompts/parse_refine_intent_v2.md:111-116`)。这会让“直接同义词”和“菜系扩展”的边界压在模型临场判断上。

**不同意的解法**: “移到 L1/L2 查表展开”不是 Step 1。`refine_intent_v2.py` 文件头明确说 V2 新 slot 当前不被 recall/score/rerank 消费，只做抽取 + trace (`chisha/refine_intent_v2.py:5-9`)；生产 refine 仍用 V1 intent 进 L1/L2/L3 (`chisha/refine.py:128-183`, `:185-196`, `:277-285`)。把扩展移入召回是跨阶段行为改造，不是 prompt/schema 文案修改。

**Step 1 可落地修正**: 保留字段以兼容 trace，但收紧 prompt: expanded 只允许从一个显式闭集选择，且 `韩式` 从“辣”默认例移除；`ingredient_synonyms` 改名不做，文案改为“直接上位类展开，禁止品牌/菜名脑补”。若后续真要代码词典，另开 D-XXX + L1/L2 回归。

#### P0-2: 「字段空洞」段制造系统性失信

**判断**: 反对 P0，修正为 P1 文案问题。

**证据**: Opus 把 `quality_floor / delivery_only / max_distance_km / reference` 视为“系统说了但没做”。但 D-085 和 CONTRACTS 已经把字段空洞定义成务实降级: 抽出但 L1/L2 不消费，仅透传 L3 + trace 标 unsupported (`docs/decisions.md:193-195`, `docs/CONTRACTS.md:60-61`)。代码也有 `DATA_LAYER_UNSUPPORTED_FIELDS` 并写入 `unsupported_in_recall` (`chisha/refine_intent_v2.py:33-39`, `:394`)；测试固定了这些字段必须列为 unsupported (`tests/test_refine_intent_v2.py:52-62`)。

**真实问题**: prompt 的措辞“让 trace 反映系统听懂了”“漏填 = 用户信任崩塌” (`prompts/parse_refine_intent_v2.md:69-77`) 过于肯定，会让 LLM 和人类误读为“系统会执行”。但这不是 P0，更不是应在 Step 1 里“真做 L1 召回过滤”。

**Step 1 可落地修正**: 不删字段，不改召回。把段落改成“如实记录为 unsupported_in_recall，L1/L2 暂不保证执行；narrative 不得声称已过滤”。这与 D-085 一致。

#### P1-1: `reject_previous` 定义不够刚性

**判断**: 同意问题，反对 schema 扩字段作为 Step 1 默认方案。

**证据**: 当前 prompt 只有一句“都不要/重来/全不行 true；仅换一个不算” (`prompts/parse_refine_intent_v2.md:65`)。binary 表达力弱，确实容易把“这些广东菜看着都不想吃，换湖南菜吧”误判成全局 reject。

**但影响被 Opus 夸大**: V2 的 `reject_previous` 当前不被下游消费 (`chisha/refine_intent_v2.py:7-9`)；生产链路仍用 V1 intent (`chisha/refine.py:128-174`)。所以它不是会立刻触发 diversity penalty 的 P1 行为风险，至少在当前代码里只是 trace/debug 风险。

**Step 1 可落地修正**: 先加正反例和 trigger 白名单/黑名单，不引入 `reject_scope`。`reject_scope` 是 schema 变更，会影响 D-079 存量 trace 与 debug-ui schema 渲染，需要单独评估。

#### P1-2: `raw_understanding` 语义岗位过载

**判断**: 修正。

**同意的问题**: 字段注释说它同时给 L3 narrative + debug (`prompts/parse_refine_intent_v2.md:55`, `:67`)，冲突例又要求它承载“不确定”信号 (`prompts/parse_refine_intent_v2.md:114-116`)。但当前生产 L3 不消费 V2 `raw_understanding`，L3 只看到 V1 `refine_intent` 和 `refine_input` (`chisha/rerank.py:487-499`)。

**反对拆字段**: 新增 `semantic_notes` 会变更 trace/debug schema。D-079 要求 trace 自包含且 trace schema 改动要 bump 版本 (`docs/CONTRACTS.md:109-115`)；debug-ui intent schema 也显式列了 `raw_understanding`，未列新字段 (`chisha/web_api.py:2785-2830`)。为一个当前未被 L3 消费的字段拆 schema，收益低于兼容成本。

**Step 1 可落地修正**: 不拆字段。把 prompt 改成 `raw_understanding` 必须包含两类短语: “已结构化执行的 slot” + “未能结构化/冲突/unsupported 的点”。这解决信息丢失，避免 schema 扩张。

### B. `rerank_system.md`

#### P0-1: 「重排原则」硬约束 + 健康结构互相覆盖

**判断**: 同意问题，反对 Opus 的具体 hard filter 公式。

**证据**: prompt 把健康结构放在“权重严格降序”的第 6 项 (`prompts/rerank_system.md:23-31`)，同时又说 L2 已做 guardrail，“不需要重复降权，但不可主动选触发健康风险的 combo” (`prompts/rerank_system.md:30`)。这在执行上确实是半排序、半过滤的混合规则。

**反对点**: Opus 建议新增 “oil_avg ≥ 4 且 main processed=true → 排除” 是新业务规则，不是 prompt 澄清。当前硬约束只有 avoid、辣度、processed 主菜 (`prompts/rerank_system.md:17-22`)；`_compute_health_flags` 只在出站后规则计算健康字段，并不参与硬过滤 (`chisha/rerank.py:697-739`)。把平均油阈值写成 hard filter 会改变推荐行为，需要 D-082/D-083 口径确认。

**Step 1 可落地修正**: 将 §6 改为“风险表达/理由约束”: 不新增 hard filter，不重复降权；当选择高油/高糖/processed 配菜时必须在 `risk_flags` 和 reason/narrative 如实暴露。若要硬过滤，另开 D-XXX。

#### P0-2: tool_use schema 缺少关键 ordering 约束

**判断**: 修正，降级。

**Opus 证据不完整**: schema 的确只规定 `rank` 范围和 `is_explore` 类型 (`chisha/rerank.py:67-69`)。但代码 validator 已强制 rank 连续、combo_index 不重复且不越界、explore 数量和位置正确 (`chisha/rerank.py:877-957`)；对应测试也覆盖 (`tests/test_rerank.py:219-235`, `:238-297`)。所以“用户看到 L2 ordering → 信任崩塌”不是无防线风险，失败会 retry/fallback。

**反对 `output_plan`**: 加顶层 plan 是 schema 变更，会扩大 tool 输出、增加 plan/candidates 不一致的新校验面，并破坏旧 trace 的简单解析预期。`narrative` 当初刻意做 optional 以兼容旧 trace (`chisha/rerank.py:88-99`)；`output_plan` 若 required，会比 narrative 风险更高。若 optional，又不能解决 Opus 所说“schema 强制”问题。

**Step 1 可落地修正**: 在现有 schema description 里补 `candidates must be emitted in final display order; rank must equal array position + 1; first n-n_explore false then n_explore true`。同时在 retry feedback 文案里可更明确，不加 plan 字段。

#### P1-1: 「同品牌至多 2 条变体」语义不清

**判断**: 同意。

**证据**: prompt 先说输入同品牌至多 2 条，要求 2 条里挑最贴合的 (`prompts/rerank_system.md:15`)，边界又说最终 5 条同 brand 至多 1 条 (`prompts/rerank_system.md:120`)。这两句不冲突，但缺少“如何说明内部择优”的输出锚点。

**Step 1 可落地修正**: 不要求每条都比较“另两条”（候选里同品牌最多 2 条，不一定有两条可比）。改成: 如果同品牌有两个变体被候选输入包含，`one_line_reason` 优先说明为什么选这条而不是同品牌另一条。

#### P1-2: `taste_match` 字段语义无锚点

**判断**: 修正。

**同意的问题**: schema 只有 0-1 范围 (`chisha/rerank.py:70-71`)，prompt 只说与 `taste_description` 命中度 (`prompts/rerank_system.md:79`)。加 rubric 有助于稳定。

**反对 Opus 影响描述**: 没看到 `feedback.py` 使用 L3 输出的 `taste_match` 做长期 prefs 训练；长期反馈抽取走 `feedback_store` + `l1_extractor`，CONTRACTS 也说 numeric ranking signal 来自 structured ratings，不是 comments 或 L3 字段 (`docs/CONTRACTS.md:73-77`)。因此“污染长期 prefs”证据不足。

**Step 1 可落地修正**: 加 rubric，但锚点必须基于 `taste_description` 与 `[PROFILE]`，不要写成固定 cuisine/cooking/ingredient 三元组，否则会把自然语言 taste_description 误结构化，碰到 D-014 红线 (`docs/CONTRACTS.md:65-69`)。

#### P1-3: explore 段质量约束语义层级不清

**判断**: 部分同意。

**证据**: prompt 同时要求 explore 数量硬约束 (`prompts/rerank_system.md:66-72`) 和“不为新奇牺牲本轮” (`prompts/rerank_system.md:121`)。它已经说明计数优先，但“候选稀薄” narrative 只泛指 intent 命中少 (`prompts/rerank_system.md:92`)，没有覆盖 explore 质量稀薄。

**修正**: Opus 的 `idx≥10` / `taste_match<0.4` 规则不可落地。idx 是候选数组位置，不等于“推荐第 11 名以后”的稳定语义；prompt 没有候选原始 rank 字段，只有 `[idx]` (`prompts/rerank_system.md:37-42`)。`taste_match` 又是 LLM 自己输出，不能先拿它作为 narrative 条件。

**Step 1 可落地修正**: 加定性 escape: 当 explore 槽只能选“与当下 refine 弱相关/只是多样性补位”的候选，narrative 必须说“后两条偏探索/备选”。不要绑定 idx 和 taste_match 阈值。

## 2. 你发现的新盲点

1. **rerank prompt 的 `refine_intent` 字段说明过期**。prompt 说结构化字段含 `flavor_tags / portion / staple_preference / price_band` (`prompts/rerank_system.md:26`)，这是 V1/D-073 口径；V2 prompt 的主字段是 `redirect / constrain / reference / reject_previous` (`prompts/parse_refine_intent_v2.md:24-57`)。生产 L3 当前也只注入 `ctx.refine_intent` 的非空键 (`chisha/rerank.py:490-499`)，不是 V2。Step 1 必须明确 L3 现在读的是 V1 intent + refine_input，不要让 rerank prompt 假装理解 V2 slot。

2. **`reference.relation="avoid_pattern"` 是 schema 死路**。V2 prompt 允许 `avoid_pattern` (`prompts/parse_refine_intent_v2.md:50-53`)，清洗也允许 (`chisha/refine_intent_v2.py:337-340`)；但 refine 执行只消费 `lighter / similar_but_different_venue`，`avoid_pattern` 会 fallback 到 raw parser，最终可能 no-op (`chisha/refine.py:213-249`)。这是比 `quality_floor` 更隐蔽的字段空洞，因为它看起来在 `reference` 内部“已支持”。

3. **`functional.low_caffeine` 示例违反“不联想”边界**。schema 注释写“下午要睡觉 → low_caffeine=true (字面提到再填)” (`prompts/parse_refine_intent_v2.md:45-47`)。用户没说咖啡因，只说睡觉；这与“加班不能推断想提神”的规则同类 (`prompts/parse_refine_intent_v2.md:124-129`)。建议删 `low_caffeine` 示例或改成“不要咖啡/奶茶/提神饮料”。

4. **`delivery_only` 的类型存在 false/null 语义陷阱**。prompt 允许 `true | false | null` (`prompts/parse_refine_intent_v2.md:43`)，但示例只有 true。`false` 究竟是“明确不要外卖/只堂食”还是“没提”容易漂移；代码会保留 false (`chisha/refine_intent_v2.py:358`)。Step 1 应要求没提一律 null，只有明确“不要外卖/堂食”才 false。

5. **L3 的 `one_line_reason` “比另两条”不总成立**。prompt 要求“说出为什么是这条而不是另两条” (`prompts/rerank_system.md:81`)，但输入候选不提供可比较组，且同品牌最多 2 条 (`prompts/rerank_system.md:15`)。这会诱导模型编造比较对象。应改为“相对可见候选/同品牌变体/相邻候选给一个具体取舍点；无可比对象时只给命中证据”。

6. **`narrative` 可选但 prompt 说强制**。tool schema 顶层只 required `candidates`，`narrative` optional 是为旧 trace 兼容 (`chisha/rerank.py:88-99`)；prompt 说顶层 narrative 强制 (`prompts/rerank_system.md:85-94`)。这不是坏事，但要在审计里承认: Step 1 只能通过 prompt 提高出现率，不能用 required 破兼容。

## 3. 强反对项

1. **反对在 Step 1 里“真做 L1 召回过滤”**。这会触碰 `recall.py / score.py / methodology.py` 的回归红线，CONTRACTS 要求 baseline_l2_snapshot 严格回归 (`docs/CONTRACTS.md:33-40`)。当前任务边界是 prompt 文案 + tool_use schema，不应混入召回过滤。

2. **反对删除 V2 字段或重命名字段**。`cuisine_candidates_expanded / ingredient_synonyms / raw_understanding / unsupported_in_recall` 已进入 trace、debug-ui schema 和测试 (`chisha/web_api.py:2800-2809`, `:2827-2830`; `tests/test_refine_intent_v2.py:347-364`)。删字段会让 D-079 存量 trace 与 debug-ui 视图出现断层。

3. **反对新增 required `output_plan`**。现有 validator 已有后验强校验 (`chisha/rerank.py:877-957`)；新增 plan 会引入 plan/candidates 双源不一致。对 fast model/provider 切换也更不友好，违反 Step 4 前不提前扩大 schema 面的原则。

4. **反对把健康 hard filter 写成 Opus 提议的油均值公式**。processed 主菜已经是硬约束 (`prompts/rerank_system.md:21`)；processed 配菜 + oil_avg 的组合阈值是新业务判断，不是 prompt 修错。没有 D-082/D-083 更新前，不应写成“直接丢弃”。

## 4. 优先级重排

**P0-Scope: 必须先澄清，否则 Step 1 会越界**
- 字段空洞只能改文案，不做 L1/L2 过滤；任何“真听”执行改造单独立项。
- schema required 字段不新增，尤其不加 `output_plan / semantic_notes / reject_scope`。

**P0-Effect: 当前 prompt 内真正会误导 LLM 的问题**
- rerank 健康结构半过滤半排序的矛盾: 改成风险披露约束，暂不新增 hard filter。
- rerank `refine_intent` 字段说明过期: 明确 L3 当前读 V1 intent + refine_input，V2 只部分通过 reference 代码路径消费。
- refine 的 `functional.low_caffeine` 示例和“不联想”冲突。

**P1: 应修但不阻塞**
- expanded/synonyms 的闭集与边界示例。
- `reject_previous` trigger 正反例。
- `raw_understanding` 职责文案收紧，不拆字段。
- `taste_match` rubric。
- explore 稀薄 narrative escape。
- 同品牌变体 reason 说明。

**降级**
- Opus P0-2 字段空洞: 降为 P1 文案修复 + P0 范围声明。
- Opus rerank P0-2 schema ordering: 降为 P1 schema description/prompt 修复，因代码 validator 已兜底。

## 5. 落地建议

1. **Refine prompt 边界修订**: 改 `parse_refine_intent_v2.md` 的字段空洞段、expanded/synonyms 说明、`delivery_only=false/null` 规则、`low_caffeine` 示例、`reject_previous` 正反例。只动文案，不改字段名。

2. **Refine eval fixtures 更新**: 针对“想吃辣但别太辣”“下午要睡觉”“只堂食/只外卖”“这些广东菜都不想吃换湖南菜”补 4-6 个 prompt-only 期望样例。≤4h。

3. **Rerank prompt 健康语义归位**: 把 §6 从“权重降序里的健康排序信号”改成“风险披露 + 不主动美化”约束；不写新 hard filter 阈值。≤2h。

4. **Rerank prompt 字段口径修订**: 修正 `refine_intent` 字段说明为当前 V1 实际字段；说明 V2 unsupported/reference 只能靠 trace/refine_input 部分影响，narrative 不得声称执行 unsupported。≤2h。

5. **Tool schema description 微调**: 只增强 `_RERANK_TOOL` 的 description，不新增 required 字段: array order == final order、rank == position+1、explore suffix。同步 CLI no-tool 段。≤3h。

6. **taste_match rubric + reason 约束**: 在 rerank prompt 增加基于自然语言 `taste_description` 的 0.9/0.7/0.5/0.3 锚点，并修正“另两条”比较措辞。≤2h。

7. **兼容性守门**: 跑 `uv run pytest tests/test_refine_intent_v2.py tests/test_rerank.py tests/test_refine_trace_persist.py -q`。若只改 prompt 无代码，可至少跑 prompt patch 相关测试和 `_patch_system_prompt_for_cli` 守门。≤1h。

## 6. 共识 vs 分歧

**已共识**
- refine prompt 存在“不联想”与扩展字段边界不清。
- 字段空洞需要显式、诚实地标注 unsupported，narrative 不能假装执行。
- `reject_previous` 需要更刚性的正反例。
- rerank 健康段当前语义混杂，需要归位。
- `taste_match` 需要评分锚点。
- explore 质量差时需要 narrative 诚实降级。
- 同品牌变体选择需要更清楚的 reason 约束。

**需要志丹拍板**
- 是否在 Step 1 之后另开 L1/L2 “真听 quality_floor / delivery_only / max_distance_km”项目。Codex 建议不放进本轮。
- 是否未来把 expanded/synonyms 迁到代码词典。Codex 建议本轮只闭集化 prompt，迁移另开 D-XXX。
- 是否新增任何 V2 schema 字段 (`reject_scope / semantic_notes`)。Codex 建议本轮不加。
- 是否把健康风险升级成新 hard filter。Codex 建议没有 D-082/D-083 更新前不加。
- 是否让 `narrative` required。Codex 建议保持 optional，靠 prompt 和测试提高命中，保护 D-079 存量 trace。
