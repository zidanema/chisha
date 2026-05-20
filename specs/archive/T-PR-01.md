# T-PR-01 · refine prompt 多项边界修订

参考: `docs/proposals/archive/2026-05-20-prompt-effect-optimization.md` §3.2 P0-E3 + §3.3 P1-1/P1-2/P1-3/P1-7/P1-8 + §4 T-PR-01

## What

只动 `prompts/parse_refine_intent_v2.md` 一个文件, 做 6 项 prompt 文案修订:

1. **删/改 `functional.low_caffeine` 示例** (P0-E3) — schema 注释 line 45-47 "下午要睡觉 → low_caffeine=true" 违反第一原则; 改为 "明确不要咖啡/奶茶/提神饮料才填", 对齐第 124-129 行 "加班不能联想想提神" 边界
2. **`cuisine_candidates_expanded` / `ingredient_synonyms` 闭集化** (P1-1) — 把 line 31/34 的开放式推断改为从一个**显式有限闭集**选择; 边界示例移除 `辣→韩式` (有争议) 等模糊扩展; **本轮不迁词典** (跨阶段)
3. **`reject_previous` trigger 白名单** (P1-2) — line 65 加正例 ("都不要" / "重来" / "全不行" / "全不要" / "重新挑") + 反例 ("换一个" / "换湖南菜吧" / 仅否定某子类不算); 当前实测 LLM 把 "换湖南菜" 判 true 是误判
4. **`raw_understanding` 职责文案收紧** (P1-3) — line 55/67 字段说明改为必须包含两类短语: "已结构化执行的 slot" + "未结构化/冲突/unsupported 的点"; **不拆字段** (保护 D-079 trace + debug-ui schema)
5. **`delivery_only: false vs null` 语义澄清** (P1-7) — line 43 加规则: "没提一律 null; 只有明确表达'不要外卖/只堂食'才 false"; 加 1 正例 + 1 反例
6. **「字段空洞」段措辞修订** (P1-8) — line 69-77 改为 "如实记录为 `unsupported_in_recall`, L1/L2 暂不保证执行; narrative 不得声称已过滤" — 与 D-085 + CONTRACTS:60-61 一致, 不假装做了

## Why

- 全部是 `prompts/parse_refine_intent_v2.md` 内的文案修订, 同源单文件, 一次性改完一次性回归, 降低 patch 冲突面
- P0-E3 (low_caffeine 示例自相矛盾) 是第一原则执行体的内部裂缝, 必须修
- P1-1/P1-2/P1-7 是 Codex 对抗审发现的边界陷阱, 都属于 prompt 文案级清晰度问题
- P1-3 (raw_understanding 文案收紧) 不拆字段, 在文字层提高 LLM 输出对 L3 narrative 的有效性
- P1-8 把"假装听见"的措辞校正为"如实记录 unsupported", 落实 D-080~085 Faithful Refine

## Done When

- `prompts/parse_refine_intent_v2.md` 6 处修订全部落, 文件 diff 可逐条对应 What 的 6 项
- 现有 `tests/test_refine_intent_v2.py` 全绿 (`uv run pytest tests/test_refine_intent_v2.py -q`)
- 全测试 `uv run pytest tests/ -q` 全绿
- 实测一条 refine 文本 "这些广东菜都不想吃, 换湖南菜吧" → `reject_previous=false` (修订前可能为 true) — **本地人工验证, 不作 CI 必过断言** (CI 守门走 T-PR-02 fixture)
- 实测一条 refine 文本 "下午要开会" → `functional.low_caffeine=null` (修订前可能为 true) — 同上
- prompt 总长度允许略缩 (4-8 行内增减), 不强制压缩 (压缩留 Step 2)

## Plan 规模上限

- `plans/T-PR-01.plan.md` ≤ 200 行
- Affected files ≤ 5

## Affected files (预估)

- `prompts/parse_refine_intent_v2.md` (改, 单文件 6 处)

## 红线

- 不删 / 不重命名任何 V2 schema 字段 (D-079 trace 兼容 + debug-ui schema + `tests/test_refine_intent_v2.py:347-364` 已锁)
- 不改 `chisha/refine_intent_v2.py` 代码逻辑 (本任务纯 prompt 文案)
- 不动 L1/L2 召回链路 (字段空洞 P1-8 只改措辞, 不真做过滤 — 真做留 D1 后续决策)

## 不做

- 不把 `expanded` / `synonyms` 迁到代码侧 yaml 词典 (D2 拍板后另开 D-XXX, 本轮只闭集化 prompt 文案)
- 不引入 `reject_scope` / `semantic_notes` 新 schema 字段 (D3 已决: 不加)
- 不动 `chisha/refine_intent_v2.py` 调用方式 (call_text 是否拆 system/user 留 Step 3)
- 不动 eval fixtures (T-PR-02 独立)
