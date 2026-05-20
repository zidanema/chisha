# T-PR-01 · refine prompt 多项边界修订 — Plan

参考 spec: `specs/T-PR-01.md`. 参考 brief: `docs/proposals/2026-05-20-prompt-effect-optimization.md` §3.2 P0-E3 + §3.3 P1-1/P1-2/P1-3/P1-7/P1-8.

## Affected files

- `prompts/parse_refine_intent_v2.md` (改, 单文件 9 处文案修订 — schema 注释段 5 处 + 关键约定段 2 处 + 字段空洞段 1 处 + example block 2 处)

无 .py / 测试代码变动 (本任务纯 prompt). 现有 `tests/test_refine_intent_v2.py` 不改 (它只断 schema/字段存在性, 不断 prompt 语义)。

## Regression risk

- **medium** (CLAUDE.md 红线: prompts/*.md 不在 12-file 高风险白名单, 但 prompt 是 refine 链路行为载体, 同 T-P1b-02 narrative 等级)
- baseline_l2_snapshot 期望 **0 diff** (L2 不动, prompt 改不影响打分 14 维)
- 测试守门: `tests/test_refine_intent_v2.py` 现有断言全绿即可 (schema 字段不变)

## Step-by-step

### 修订 1 (P0-E3): `functional.low_caffeine` 示例

**位置**: `parse_refine_intent_v2.md:45-47` schema 注释里 "下午要睡觉 → low_caffeine=true"

**改动**: 把 trigger 描述从隐式联想改为显式表达:
- 旧: `"low_caffeine": true | false | null,  // "下午要睡觉" → true (字面提到再填, 不联想)`
- 新: `"low_caffeine": true | false | null,  // 仅明确提"不要咖啡/奶茶/提神饮料"才填 true; "下午要睡觉"这种不算 (违反不联想原则)`

行 124-129 "今天加班好累 → 反例" 段保留, 形成内部一致。

### 修订 2 (P1-1): `cuisine_candidates_expanded` / `ingredient_synonyms` 闭集化

**位置**: `parse_refine_intent_v2.md:31` (`cuisine_candidates_expanded` schema 注释) + `:34` (`ingredient_synonyms` schema 注释) + §关键约定第 2/3 条 (`:63-64`) + **example block `:87-90`** (`"今天想来点辣的"` 输出含 `"韩式"` 必须同步删, Codex iter 1 issue 2)

**改动**:
- `cuisine_candidates_expanded` schema 注释: 把例子 `"辣"→["川菜","湘菜","贵州菜","重庆菜","韩式"]` 改为 `"辣"→["川菜","湘菜","贵州菜","重庆菜"]` (移 "韩式" 因有争议), 加一句 "**只从你认为高置信的菜系挑, 不要为了凑多样性硬塞**"
- `ingredient_synonyms` schema 注释: 保留例子 `"肉"→["排骨","牛肉","猪肉","鸡","鸭","羊"]`, 加一句 "**只列上位类的直接同义/子类, 不要扩到品牌名 / 菜名**"
- **`:87-90` example output 同步**: `"今天想来点辣的, 不要日料, 30 块以内"` 输出里 `"cuisine_candidates_expanded":["川菜","湘菜","贵州菜","重庆菜","韩式"]` 改为 `["川菜","湘菜","贵州菜","重庆菜"]` (删 "韩式") — **跟 schema 注释保持一致, 否则 LLM 看到两条相反指令**
- §关键约定第 2 条 (`:63`) 重写: "**仅在用户表达抽象口味时填, 且必须是高置信菜系子集**。'湘菜' 已是明确菜系 → `cuisine_want=["湖南菜"]` 即可, `expanded` 留空。**禁止脑补菜系: '辣'扩展不要写'韩式'/'东南亚菜', 写主流 4 个就够。**"
- §关键约定第 3 条同步收紧

### 修订 3 (P1-2): `reject_previous` trigger 白名单 + 部分拒绝时强制伴随字段

**位置**: `parse_refine_intent_v2.md:65` (§关键约定第 4 条)

**改动**: 把单行说明扩为 trigger 白名单 + 反例 block + **partial reject 时必填伴随字段** (Codex iter 1 issue 4 — 防止信息丢失):
```
4. **`reject_previous`**:
   - **trigger 白名单 (满足任一才 true)**: "都不要" / "全不要" / "重来" / "重新挑" / "全不行" / "全部换掉" / 类似全盘否定语义
   - **反例 (false)**: 
     - "换一个" — 只是请求新一轮, 不是推翻
     - "换湖南菜吧" — 子类否定 + 替代, 不是全盘
     - "这些广东菜都不想吃, 换湖南菜吧" — 同上, **属于 partial reject (拒一类菜系不拒全部)**
   - **partial reject 时必须如实填伴随字段, 不能让"被拒绝"信号丢失**:
     - 例: "这些广东菜都不想吃, 换湖南菜吧" → `reject_previous=false` **但** `cuisine_avoid=["广东菜"]` + `cuisine_want=["湖南菜"]` + `raw_understanding` **必须**含"用户拒绝了上一轮的广东菜"
     - 不允许只填 `reject_previous=false` 而把拒绝信号丢掉 (这会违反 Faithful Refine, D-080)
   - 不确定时**默认 false** (保守: 误判 true 会触发 diversity penalty + 抛弃上轮排序, 影响大), **但要在 raw_understanding 注明"未明确拒绝, 按细化处理"**
```

### 修订 4 (P1-3): `raw_understanding` 职责文案收紧

**位置**: `parse_refine_intent_v2.md:55` (schema 注释) + `:67` (§关键约定第 6 条)

**改动**: 字段说明改为必须包含两类短语 (但不拆字段, 保护 D-079 trace + debug-ui schema):
- Schema 注释 (`:55`): `"raw_understanding": "...",  // 必填, 30-80 字, 包含 (a) 已结构化执行的 slot 摘要 + (b) 未结构化/冲突/unsupported 的点; 给 L3 narrative + debug 用`
- §关键约定第 6 条 (`:67`): 加一句 "如果有 `unsupported_in_recall` 字段或冲突表达, `raw_understanding` **必须如实说明**, 例: '想吃湖南菜清淡; 用户提"30 块以内"已抽出 price_max 但 L1/L2 不消费, narrative 不要声称已过滤'"

### 修订 5 (P1-7): `delivery_only: false vs null` 语义澄清

**位置**: `parse_refine_intent_v2.md:43`

**改动**: 把注释扩为三态语义 + 正反例:
- 旧: `"delivery_only": true | false | null,       // "今天只点外卖" → true`
- 新: `"delivery_only": true | false | null,       // null=没提 (默认); true="只外卖/不要堂食"; false="只堂食/不要外卖". **没提一律 null, 不要默认 false**`

§字段空洞 (line 73-78) 正例 line 75 (`"今天只吃外卖" → delivery_only: true`) 保留, 加一条反例: `"今天加班好累" → delivery_only: null (没提外卖偏好, 不要默认 false)`

### 修订 6 (P1-8): 「字段空洞」段措辞修订 — **`reference` 单独处理** (Codex iter 1 issue 1)

**位置**: `parse_refine_intent_v2.md:69-77` 整段 "## 字段空洞"

**Codex iter 1 issue 1 关键修正**: `reference` 字段不是纯 unsupported! T-P2-01 已实施 reference resolver, `chisha/refine.py:202-246` 在 L3 之前消费 V2 `reference` (relation=`lighter` / `similar_but_different_venue` 真做软重排, 通过 `chisha/reference_resolver.py` 解析 + `apply_relation`)。`avoid_pattern` 是死路 (T-PR-04 会单独说明)。所以"字段空洞"段必须区分:
- **真不消费** (L1/L2 + L3 都不读, 只透传 trace): `constrain.quality_floor / delivery_only / max_distance_km`
- **L3 上游消费** (refine.py 在 L3 前用 reference resolver 做软重排): `reference.relation in {lighter, similar_but_different_venue}`
- **schema 允许但不消费** (死路): `reference.relation == "avoid_pattern"` (T-PR-04 处理)

**改动**: 措辞改为:
```
## 字段空洞 (你照填, 但下游不保证执行 — D-085 务实降级)

下游对 V2 字段的执行情况分三类, 你都要如实填, 但 raw_understanding 要明白系统能做什么:

**真不消费类** (L1/L2 召回不读, L3 也只能看到字符: `constrain.quality_floor / delivery_only / max_distance_km`):
- 用户明确表达时如实填 (例: "不要快餐" → `quality_floor="non_fast_food"`)
- 没表达留 null
- 自动加入 `unsupported_in_recall` 数组

**L3 上游真消费类** (refine.py 用 reference resolver 软重排, T-P2-01): `reference.relation in {"lighter","similar_but_different_venue"}`
- 用户用了相对表达 ("比昨天清淡" / "和上次那家差不多") 时填
- 这部分 **真会影响推荐排序**, narrative 可以说"按你说的比昨天清淡来排"

**schema 允许但不消费类** (死路, T-PR-04 处理): `reference.relation == "avoid_pattern"`
- 暂不推荐使用, 如果填了 raw_understanding 要注明"avoid_pattern 当前不消费"
- **编码路径规则 (Codex iter 2 NEW-A)**: 用户实时输入的显式避口 ("不想吃韩国菜" / "别给我日料" / "排除粤菜") **一律走 `redirect.cuisine_avoid`**, 不要走 `reference.avoid_pattern`. `avoid_pattern` 仅保留给无法解析为具体菜系的隐式 negative 历史引用 (例: "不要像那次那样") — 当前 LLM 在 prompt 范围内基本遇不到这种情形, **默认不要主动用**.

**填字段的规则**: 用户明确表达时如实填, 让 trace 反映"系统听到了什么"; 没表达时留 null. **不要为了显得听懂而过度推断**.

**L3 narrative 的禁线**: narrative **不得声称**已对"真不消费类"字段做过过滤/排除/召回筛选 (违反 D-085 + CONTRACTS:60-61); 对"L3 上游真消费类" reference 字段可以声称已按相对关系排序。raw_understanding 应注明该填了哪个 unsupported 字段。

正例:
- `"今晚不要快餐"` → `constrain.quality_floor: "non_fast_food"` (真不消费, narrative 不要说"已过滤快餐")
- `"今天只吃外卖"` → `constrain.delivery_only: true` (真不消费类)
- `"走路 10 分钟以内的"` → `constrain.max_distance_km: 1.0` (真不消费类)
- `"和上次那家差不多"` → `reference: {"reference_meal_id": null, "relation": "similar_but_different_venue"}` (L3 上游真消费类, narrative 可说"按你说的找相似口味不同餐厅")
```

(具体保留正例数量、格式细节由实施时根据现有上下文判断, 不影响语义。)

## Test strategy

- **不加新测试** (eval fixture 留 T-PR-02)
- 现有 `tests/test_refine_intent_v2.py` 全跑, 应全绿 — 它只断 schema 字段 + 字段类型, 不依赖 prompt 文案
- 全测试 `uv run pytest tests/ -q` 跑过, 期望与改前条数一致 (无新增 / 无失败)
- baseline_l2_snapshot 不强制跑 (prompt 改不影响 L2; 但 T-PR-07 整体守门会跑)

**spec Done When 强制人工语义验证** (Codex iter 1 issue 3):
- spec `specs/T-PR-01.md:29-30` 明确要求两条人工验证 case (本地跑, 非 CI 必过):
  - `"这些广东菜都不想吃, 换湖南菜吧"` → `reject_previous=false` + `cuisine_avoid=["广东菜"]` + `cuisine_want=["湖南菜"]` + raw_understanding 含拒绝信号
  - `"下午要开会"` → `functional.low_caffeine=null` (不再 true)
- 实施时 (Phase 3 之后) 用 `uv run python -c "from chisha.refine_intent_v2 import extract_refine_intent_v2; ..."` 跑这两条, 结果记到 commit message 或 plan 末尾 verification block
- **prompt 内部一致性 self-check**: 实施完后 grep `prompts/parse_refine_intent_v2.md` 确认 "韩式" 全部移除 (schema 注释 + example block 同步)

**额外人工对比**:
- 不跑真 LLM 的 `use_llm=True` 测试 (会调 OpenRouter 真接口); 上面两条 case 是手跑, 不算 CI

## Rollback notes

- 单文件改动, rollback = `git checkout HEAD~1 -- prompts/parse_refine_intent_v2.md`
- 不涉及代码逻辑, 不影响 trace schema, 不影响测试断言
- 字段空洞段措辞改动可能让 LLM 偶尔少填 unsupported 字段 → eval fixture (T-PR-02) 会守门; 但本任务先不加 fixture, 留作 T-PR-02 范围
- 修订 5 / 6 措辞改动若让 LLM 在某些 case 上变得过分保守 (例: 明确 "只外卖" 时还填 null), T-PR-02 fixture 会暴露

## 不做

- 不动 `chisha/refine_intent_v2.py` 代码 (本任务纯 prompt 文案)
- 不删 / 不重命名任何 V2 schema 字段
- 不动 L1/L2 召回链路
- 不迁词典 (`expanded`/`synonyms` 留在 LLM, 仅闭集化 prompt 文案; 词典化是 F-010 Phase 1 后)
- 不引入 `reject_scope` / `semantic_notes` 新 schema 字段 (D3 已决)

## Plan 规模

- 本文件: ~180 行, ≤ 200 ✅
- Affected files: 1, ≤ 5 ✅

## Changelog (iter 2 接受 Codex iter 1 5 个 BLOCKER)

| Issue | Codex 反对 | 主 agent 处理 |
|---|---|---|
| 1 (P0) | `reference` 不是纯 unsupported, T-P2-01 真消费 lighter/similar_but_different_venue | 接受. 修订 6 字段空洞段分三类: 真不消费 / L3 上游真消费 / schema 死路. narrative 禁线只对真不消费类 |
| 2 (P0) | `:87-90` example 还含 `"韩式"`, 跟 schema 注释修订矛盾 | 接受. 修订 2 affected lines 加 `:87-90` example block, 同步删 "韩式" |
| 3 (P1) | spec 要求人工验证 case 但 plan test strategy 没列 | 接受. test strategy 段加两条人工验证 case + prompt 内部一致性 self-check |
| 4 (P1) | "换湖南菜吧" → false 时如果不强制 cuisine_avoid/want/raw_understanding 伴随, 拒绝信号丢失违反 Faithful Refine | 接受. 修订 3 反例改为 "partial reject 时必填伴随字段, 不能让被拒绝信号丢失" |
| 5 (P1) | 受影响行号清单不完整 (line 84 / 90 / 102 example block 也是语义受影响位置) | 接受. affected files 描述从 "6 处" 改为 "9 处" (含 schema 注释 5 + 关键约定 2 + 字段空洞 1 + example block 2) |

无拒绝项, 无过度谨慎判定。

## Changelog iter 3 (接受 Codex iter 2 NEW-A)

| Issue | Codex 反对 | 主 agent 处理 |
|---|---|---|
| NEW-A | 三类 reference 描述了消费行为但没说编码路径: "不想吃韩国菜" LLM 走 cuisine_avoid 还是 reference.avoid_pattern? | 接受. 修订 6 "schema 允许但不消费类" 段加编码路径规则: 实时显式避口一律走 `redirect.cuisine_avoid`, `avoid_pattern` 仅留无法解析的隐式 negative 历史引用, 默认不主动用 |
