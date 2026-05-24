# T-FR-V1-RETIRE · V1 退役 + V2 schema 扩 + 全栈切 V2 (shipped 2026-05-24)

> **Status**: shipped (2026-05-24, worktree `v1-retire-brief` 合 main)
> **Decision ID**: D-096 (主决策) + D-090.1 + D-094.1 (修正案)
> **Origin**: 2026-05-23 prompts/ 清理时发现 V1/V2 并行
> **Final shape**: V1 refine_intent.py + parse_refine_intent.md 整模块砍; V2 schema bump 2.0→2.1 (redirect 9 槽 + constrain 4 槽); 全栈 (后端 12 / debug-ui 9 文件) 切 V2.1; 历史 trace 删; pytest 930+ pass.

## 第一原则

召回 / 打分 / 排序必须真支持用户表达 → **V2 schema 必须覆盖高频真诉求**, narrative 只补充不替代。

**D-094 字段闭包修正 (本案发起 D-094.1)**: 原 D-094 锁定 V2 9 槽 (7 redirect + 2 constrain), 写明「schema 未覆盖诉求 narrative 不假装支持」。**D-094.1 推翻闭包约定**, 追加 4 个 V2 slot (heavy 走 `oil="high"` / `wants_soup` / `staple_want/avoid` / `price_band`); narrative 不假装的纪律保留不变。

## What

**一个 PR, 全栈切 V2**:
- 后端: 砍 V1 LLM + V1 prompt + `refine_intent.py` 模块; V2 schema 扩 3 字段 (heavy/soup/staple/price_band) + sweet/sour 砍; recall/score/rerank/api 全部读 V2
- 前端 3 个 SPA (`apps/web` + `apps/debug-ui` + `apps/sandbox-lab`): 改成读 V2 shape
- openclaw (`integrations/openclaw/feishu_card.py`): 切 V2 字段
- 历史 trace: 删 (个人项目, trace 是调试 artifact 非用户数据)
- D-094 字段闭包注脚澄清; D-090 oil 豁免落到 V2 `constrain.oil="high"`
- 守门: pytest + L3 eval + chrome-devtools 前端验证 + openclaw smoke + baseline_l2_snapshot **重新 baseline**

终态: 一次 refine 一次 LLM (V2), 全栈只有 V2 shape, 高频用户表达 V2 schema 真覆盖 (不再 narrative 假装)。

## Why

V1 跟 V2 并行调用是过渡债 (每次 refine 跑两次 LLM, 多 2~6s 延迟, T-PR-04 这种字段同步维护成本一直在); shim 渐进路径是企业级稳健思维, 不适合个人用户量级 (用户量 = 1, trace 可弃)。

**第一原则**: 召回/打分/排序必须真支持用户表达 → V2 schema 必须覆盖高频真诉求, narrative 只补充不替代。D-094 字段闭包的本意是「narrative 别假装」, **不是 schema 越窄越好**。

## 5 字段 audit (基于志丹自述高频用户表达, 非 grep 证据)

> **频率证据声明**: 字段频率主张基于志丹 (唯一用户) 自述 + V1 现有 score 分支判断, 非全仓 grep 量化 (codex round-4 验证 grep 被菜品 tagging 污染, 不可作真证据). 真验证靠**落地后 eval set + 实际 refine trace 数据驱动**, 见「Done When」.

| 字段 | 自述频率 | V1 作用 | V2 等价? | 决策 |
|---|---|---|---|---|
| **heavy** (重口/下饭/够味) | 高 (志丹自述) | `score.py:598` oil 豁免 (D-090) + `:720` 加分 | ❌ V2 `constrain.oil` 只有 `low`; raw_understanding 到 L3 时 L2 已压完油菜 | **V2 schema 补 `constrain.oil="high"`** |
| **soup** (想喝汤/粥) | 高 (晚饭常见) | `recall.py:519` + `score.py:711` 优先有汤 | ❌ V2 无 wetness 槽, L3 兜不住 L2 已 demote | **V2 schema 补 `constrain.wants_soup: bool`** (简单 bool, 不抓 wetness 数值细节, 后续 D-XXX.future 演进) |
| **staple_preference** (米/面/粥) | 中 | `score.py:785` 主食匹配 | ⚠️ ingredient_want 语义错 | **V2 schema 补 `redirect.staple_want/avoid: list[str]`** (自由字符串, 跟 cuisine 一样, 不闭包) |
| **price_band 模糊文本** (便宜/高端) | 中 | V1 文本规则 → cheap/premium | ⚠️ V2 只 `price_max` 数字 | **V2 schema 补 `constrain.price_band: cheap\|normal\|premium\|null`** — **优先级: `price_max` 数字优先 (更精确), `price_band` 是兜底** |
| **sweet** (想吃甜) | 低 | `score.py:649,733` 甜酱权重 | ⚠️ L3 raw_understanding 勉强兜 | **砍**, L3 兜底 |
| **sour** (酸辣/酸菜) | 低 | `score.py:726` 按菜名"酸"打分 (本身 hacky) | ⚠️ L3 兜 | **砍**, 实现 hacky 删了不可惜 |

直接 1:1 切 V2 (8 字段, 无 schema 改): `cuisine_want/avoid`, `ingredient_want/avoid`, `cuisine_candidates_expanded`, `brand_avoid`, `cooking_method_avoid`, `freeform_note → raw_text`

V1 限定→V2 现有 (2 字段): `flavor_tags=spicy → cuisine_candidates_expanded`, `flavor_tags=light → constrain.oil="low"`

直接砍 (3 字段, V1 已无消费): `cooking_method` (positive), `raw_flavor`, `portion`

## V2 schema 扩展 (新增 4 槽)

```diff
 {
   "redirect": {
     "cuisine_want": [...],
     "cuisine_avoid": [...],
     "cuisine_candidates_expanded": [...],
     "ingredient_want": [...],
     "ingredient_avoid": [...],
     "brand_avoid": [...],
     "cooking_method_avoid": [...],
+    "staple_want": [...],           // 新, 主食偏好 (米/面/粥)
+    "staple_avoid": [...]           // 新, 不要的主食类型
   },
   "constrain": {
-    "oil": "low" | null,
+    "oil": "low" | "normal" | "high" | null,   // 扩枚举 _OIL_VALUES = {"low","normal","high"}; "high" 替代 V1 heavy + 触发 D-090.1 oil 豁免
     "price_max": number | null,
+    "price_band": "cheap" | "normal" | "premium" | null,  // 新, 模糊文本表达 (price_max 是数字, 互补)
+    "wants_soup": bool              // 新, 想喝汤
   },
   "reference": ...,
   "reject_previous": ...,
   "raw_understanding": ...,
   "schema_version": "2.1"           // bump
 }
```

`flavor_tags=heavy/sweet/sour` 全部从 V2 接口消失 — sweet/sour 走 raw_understanding + L3 (narrative 兜底, 不假装在 L1/L2 真过滤), heavy 走 `constrain.oil="high"`.

## Affected files (一个 PR 全动, 按层分组)

### 后端 — live code
| 文件 | 改动 |
|---|---|
| `prompts/parse_refine_intent_v2.md` | schema 扩 4 槽; 加示例 (重口/想喝汤/想吃面/便宜); 砍 sweet/sour 提及 |
| `prompts/parse_refine_intent.md` | **删** |
| `chisha/refine_intent.py` | **整模块删** (414 行) |
| `chisha/refine_intent_v2.py` | RefineIntentV2 dataclass 加 4 字段; `_fallback_to_legacy` 改成 empty fallback (不调 V1); schema_version bump 2.1; `_clean_parsed_to_v2` 加新字段清洗 |
| `chisha/refine.py` | 去 V1 调用 + V1→V2 桥接 (D-094 桥接代码); 下游直接拿 V2 |
| `chisha/recall.py` | line 516 (flavor_tags spicy/soup/light) 改成读 `constrain.oil` + `constrain.wants_soup` + `cuisine_candidates_expanded`; 砍 sour |
| `chisha/score.py` | line 593-726 大改: heavy 路径读 `constrain.oil=="high"`; soup 读 `constrain.wants_soup`; staple 读 `redirect.staple_want/avoid`; price 读 `constrain.price_band` (字符串) 或 `price_max` (数字 → 推 band); 砍 sweet/sour 分支 |
| `chisha/rerank.py` | refine_intent 字段口径切 V2; L3 prompt 输入字段同步 |
| `chisha/web_api.py` | API response 字段切 V2 shape (refine_intent 字段返 V2 schema, 不再返 V1 shape) |
| `chisha/sandbox_adapter.py` | refine_intent 字段同步 V2 |
| `chisha/trace_helpers.py` | 砍双存; 只存 V2; trace schema bump |
| `chisha/context.py` | line 57/196/228 refine_intent 字段同步 V2 |

### 前端 (codex round-4 grep 修正: 真改的主要是 debug-ui)
| 应用 | refine_intent 字段引用数 | 改动 |
|---|---|---|
| `apps/web/src/**` | **0** (用户视图不直接读 refine_intent 字段) | 仅 `types.ts` 类型定义跟随后端 schema; UI 渲染不变 |
| `apps/debug-ui/src/**` | **9 个文件** | trace 视图 / 5 主题里 refine_intent inspect 全部切 V2 shape — chrome-devtools-mcp 自驱必验 |
| `apps/sandbox-lab/src/**` | **0** | 仅 `types.ts` 跟随; refine inspect 视图若已存在则切 V2 |

### 外部集成
| 文件 | 改动 |
|---|---|
| `integrations/openclaw/feishu_card.py` | 飞书卡片渲染切 V2 字段 (cuisine_want/avoid / ingredient_want/avoid / constrain.oil / wants_soup / staple_want+avoid / price_band 全部重映射成 chip). **保留 chip 反馈 UX, 不改 OpenClaw 用户体感** |
| `chisha/feedback.py` | `parse_feedback()` 已无 live caller, 可一并砍. `CHIP_VOCAB` (拒绝**反馈** chip 词表, **跟 refine intent 是两个语义层**) 保留; sweet/sour 反馈 chip 不在本案废弃, 另立 D-XXX 再决 |

### 契约文档
| 文件 | 改动 |
|---|---|
| `docs/api.md` (line 47-49) | 修自相矛盾, 写明 `/api/refine` 返 V2 shape (`RefineIntentV2`) |
| `docs/CONTRACTS.md` (line 37) | D-090.1 修正案: oil 豁免触发条件从 `intent.flavor_tags='heavy'` 改为 `constrain.oil=="high"` |
| `docs/CONTRACTS.md` (line 61) | **D-094.1 修正案: 推翻原 D-094 字段闭包约定**, V2 schema 从 9 槽扩到 13 槽 (+oil="high" / wants_soup / staple_want+avoid / price_band). narrative 不假装支持的纪律保留. 这是发起修正案, 不是重解释原文 |
| `docs/decisions.md` | 加 D-XXX 主条 (V1 退役 + 全栈切 V2) + D-090.1 (oil 豁免触发字段切换) + D-094.1 (字段闭包推翻 + schema 扩 4 槽) |
| `docs/ROADMAP.md` | V1 退役进 Phase 1 推广前的工程清理 |

### eval / tooling / tests
| 文件 | 改动 |
|---|---|
| `prompts/parse_refine_intent_v2.md` eval set | 加 4 字段 (heavy/soup/staple/price_band) case 各 5+; 砍 sweet/sour case |
| `scripts/refine_eval_runner.py` | eval 集成新字段; `legacy_v1.price_band` 字段清理 |
| `tests/test_refine_intent_parser.py` | **整组删** (V1 parser 测试) |
| `tests/test_refine_intent_v2.py` | 加新字段断言 |
| `tests/test_intent_score.py` | score 分支测试改 V2 字段 |
| `tests/test_refine.py` | API shape 测试改 V2 shape |
| `tests/test_l0_constraints.py` / `test_l2_refine_snapshot_d090.py` | D-090 触发字段切 V2 |
| `tests/test_acceptance_d076_d077.py` | prompts/ 目录复制改 (V1 prompt 已删) |
| 其他 V1 相关测试 | grep 后逐个砍/改 |

### 数据
- 历史 trace 文件 (`data/feedback_history.jsonl` + trace_store 文件): **直接删** (用户决定)

## Done When

- pytest 全绿 (V1 相关测试整组删, V2 新字段断言加)
- L3 eval 重跑 no regression (V2 新字段 + 砍 sweet/sour 后, top60 / final 5 跟当前 V2 路径不退步)
- V2 eval set 新加 case 100% pass (4 新字段 + 砍字段 narrative 路径)
- baseline_l2_snapshot **重新 baseline** (V2 是新基线, 不跟 V1+V2 时代对比)
- 前端 chrome-devtools-mcp 自驱: `/` (web) + `/` (debug-ui) + `/` (sandbox-lab) 各跑 golden path + 1 edge case, console 无 error/warn, network 无 4xx/5xx
- openclaw smoke test (飞书卡片渲染不崩, 字段读取无 KeyError)
- 一次 refine 一次 LLM (V2), 延迟降 2~6s

## 红线

- D-090 / D-094 推翻有迹可循: `decisions.md` D-090.1 + D-094.1 必须落, `CONTRACTS.md` 同步更新
- V2 schema bump 到 2.1, 老 trace 不复用 (删)
- 前端不许只跑 vitest/tsc 就宣告完成 — `chrome-devtools-mcp` 自驱浏览器是硬约束 (CLAUDE.md「前端自测」)
- baseline_l2_snapshot 是「重新 baseline」, 不是「0 diff 对比」— 因为 schema 变了, 跟旧 baseline 对比无意义
- 砍 sweet/sour 信号是已知功能退步, eval + dry_run 验证可接受

## 不做

- 不动 reference resolver (T-P2-01)
- 不动 L1 词表扩
- 不接 OpenClaw 新能力 (D-074 待定)
- 不动 V2 raw_understanding 行为 (narrative 纪律不变)
- 不在本案添加 food_form_avoid 等 D-094 未规划字段

## Open questions

无.

注: 之前疑问的 openclaw chip 已在「外部集成」章节定: 飞书卡片切 V2 字段重映射, 保留 chip UX. **CHIP_VOCAB 是反馈 chip 词表 (跟 refine intent 是两个语义层), 不在本案动**; sweet/sour 砍的是 V1 refine intent 字段 (`flavor_tags=sweet/sour`), 不是餐后反馈"太甜"chip — 后者另立 D-XXX 再说。
