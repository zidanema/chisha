# Refine / L3 Prompt 优化设计稿 (v2 共识版)

**日期**: 2026-05-20
**状态**: Opus + Codex 两轮辩论后收敛的共识版, **替代 v1 思路稿** (v1 findings 见 §附录 A,Codex 对抗审全文见 [codex-review](2026-05-20-prompt-effect-optimization.codex-review.md))
**作用**: 给志丹拍板的最终设计稿,拍板后走 `/plan-brief` 拆 specs + `/ship-tasks` 串跑
**目标 prompt**: `prompts/parse_refine_intent_v2.md` (refine 意图解析员) + `prompts/rerank_system.md` (L3 精排员)
**契约**: 仅改 prompt 文案 + tool_use schema description,**不动 L1/L2 召回链路 / 不新增 required schema 字段 / 不加新业务规则 hard filter**

---

## 0. 共识链路回顾

| 轮次 | 角色 | 产出 |
|---|---|---|
| Round 0 | Opus + 志丹 4 轮讨论 | 实测基线 + 初版 4 阶段优先级框架 |
| Round 1 | Opus 独立 review | v1 设计稿 (4 P0 + 5 P1 finding) |
| Round 2 | Codex 对抗审 | 砍 2 P0 升 1 P1,发现 Opus 漏看的 6 个新盲点 + 范围红线警告 |
| **本文** | 两 model 共识 | **v2 共识版**, 待志丹拍板 5 项分歧 |

---

## 1. 任务定义 (志丹定的四阶段优先级)

**总原则**: 效果优先 > 可读性 > 性能 > 基建。任何阶段的改动不能让上一阶段的目标退化。

| 阶段 | 目标 | 验收方式 |
|---|---|---|
| **Step 1** | **效果**: prompt 写得对不对, 有无内在矛盾 / 漏掉系统宪法 / 跨文件契约漂移 | 专家 review + Codex 对抗审 → 共识清单 → 7 个原子 task |
| **Step 2** | **可读性**: prompt 对 LLM 和人类都更清晰、更短、更干净 (不能损失 Step 1 已确认的约束) | 结构化重写 + diff review |
| **Step 3** | **加速 / 压缩**: 在效果等同前提下砍 token / 改 cache 策略 / 缩 K | baseline_l2_snapshot 严格回归 + 5-10 case 人工对比 |
| **Step 4** | **基建切换**: 换 model (haiku-4.5) / 换 provider (anthropic 直连 vs OR vs CCC CLI) | A/B 测试 + 端到端 latency/cost 对比 |

**关键纪律**:
- Step 3 完成后必须**回到 Step 1** 跑一轮效果回归
- 每个 step 内部小步走,改一处验一次,不堆 batch
- 所有改动落 commit,跑 baseline_l2_snapshot 跨 step 严格对比

---

## 2. 当前基线 (实测, 2026-05-20)

**Provider**: OpenRouter / `anthropic/claude-sonnet-4.6` (`profile.yaml:34`)

| 链路 | prompt chars | prompt tokens | output tokens | latency | cache | 单次成本 |
|---|---|---|---|---|---|---|
| **refine_intent_v2** | 9,503 | ~4,620 | 200-230 | 5-10s (均 8s) | ❌ 0 (整 prompt 塞 user role, Step 3 修复) | $0.017 |
| **L3 rerank** | system 4,757 + user 10,902 | ~16,570 | 800-900 | 19-22s | ✅ 4,253 (二次起命中 system 段) | $0.04 |

**端到端 refine 二轮链路 ≈ 30s** (refine 8s + L3 20s 串行)。

---

## 3. Step 1 最终 P0/P1 (Opus + Codex 共识)

### 3.1 P0-Scope (范围红线,本轮不做)

| # | 红线 | 来源 |
|---|---|---|
| S1 | 不动 L1/L2 召回链路 | 字段空洞按 D-085 + CONTRACTS:60-61 已决"务实降级"处理,代码 `chisha/refine_intent_v2.py:33-39` 已有 `DATA_LAYER_UNSUPPORTED_FIELDS` + `unsupported_in_recall`, tests 已锁 |
| S2 | 不新增 required schema 字段 | `output_plan` / `semantic_notes` / `reject_scope` 全砍。schema 扩张会破 D-079 trace 兼容 + debug-ui 视图断层 |
| S3 | 不加新业务规则 hard filter | 健康只改文案不改判定。`oil_avg≥4` 类阈值需 D-082/D-083 口径,本轮不涉 |

### 3.2 P0-Effect (真 prompt 误导,本轮必改)

#### P0-E1: rerank prompt 描述的是 V1 refine_intent schema,实际 L3 注入的也是 V1 — 但 V2 prompt 已经实施 (跨 prompt 契约漂移)

**证据**:
- `prompts/rerank_system.md:26` 重排原则 §2 写 refine_intent 字段含 `cuisine_want / cuisine_avoid / ingredient_want/avoid / flavor_tags / portion / staple_preference / price_band` — **V1/D-073 口径**
- `prompts/parse_refine_intent_v2.md:24-57` schema 主字段是 `redirect / constrain / reference / reject_previous` — **V2 口径**
- `chisha/rerank.py:490-499` `_context_block` 注入 `ctx.refine_intent` 的非空键 — 当前 ctx 走的是 **V1 intent + refine_input**,不是 V2

**影响**: rerank prompt 在告诉 LLM "你会看到 V2 字段",但 LLM 实际看到 V1 字段。LLM 找不到字段时行为漂移 — 该说 "我看到了 cuisine_want=湖南菜" 但可能因找不到 V2 字段而走 freeform_note 兜底。

**修正**: 修订 rerank prompt §重排原则 §2,改成 V1 实际字段口径 + 说明 V2 部分通过 reference resolve 影响 (`chisha/refine.py:213-249` `lighter` / `similar_but_different_venue` 才被消费,`avoid_pattern` 是死路),narrative 不能声称已执行 unsupported 字段。

#### P0-E2: rerank §重排原则 §6 健康结构 — 半排序半过滤,语义混杂

**证据**:
- `prompts/rerank_system.md:23-31` "权重严格降序" 列出 §1-§7,§6 是"健康结构"
- `prompts/rerank_system.md:30` "L2 已经做了健康 guardrail (intent 加分 × 0.4),**你不需要重复降权**,但**不可主动选触发健康风险的 combo**"

**影响**: §6 既在权重列表里 (位次 6) 又被指示"不要降权"。LLM 行为不稳:高油 combo 有时排第 4-5,有时直接排除。当 refine_intent_want=辣 + 高油 combo 同时存在时,与 L2 期望不一致。

**修正**: §6 改为"风险披露 + 不主动美化"约束 — 选高油/高糖/processed 配菜时必须在 `risk_flags` 和 reason/narrative 如实暴露,但**不重复降权也不新增 hard filter**。若要硬过滤,另开 D-082/D-083。

#### P0-E3: refine `functional.low_caffeine` 示例本身违反第一原则

**证据**:
- `prompts/parse_refine_intent_v2.md:45-47` schema 注释 "下午要睡觉 → low_caffeine=true (字面提到再填,不联想)"
- `prompts/parse_refine_intent_v2.md:124-129` 反例 "今天加班好累" 禁止推断 "加班→提神"

**影响**: 同一 prompt 内,"下午要睡觉→不要咖啡因" 和 "加班→不要推断" 是同类联想,自相矛盾。LLM 学到 "睡前不要咖啡因可联想" 反而退化对所有联想边界的理解。

**修正**: 删 "下午要睡觉" 示例或改为 "明确不要咖啡/奶茶/提神饮料才填",对齐第一原则。

### 3.3 P1 (应修不阻塞)

| # | 任务 | 来源 finding |
|---|---|---|
| P1-1 | refine `cuisine_candidates_expanded` / `ingredient_synonyms` **闭集化** (本轮只动 prompt + 收紧边界示例,词典迁移另开 D-XXX) | Opus P0-1 / Codex 降级 |
| P1-2 | refine `reject_previous` 加 trigger 正反例白名单 (binary 字段保留,不改 schema) | Opus P1-1 / Codex 修正 |
| P1-3 | refine `raw_understanding` 职责文案收紧 — 必须包含"已结构化的 slot"+"未结构化/冲突/unsupported 的点"两类短语 (不拆字段,保护 D-079 trace) | Opus P1-2 / Codex 修正 |
| P1-4 | rerank `taste_match` 加 rubric (锚点基于自然语言 `taste_description`,不结构化为 cuisine/cooking/ingredient 三元组,避碰 D-014) | Opus P1-2 / Codex 修正 |
| P1-5 | rerank explore 稀薄 narrative escape (定性,不绑 idx 和 taste_match 阈值) | Opus P1-3 / Codex 修正 |
| P1-6 | rerank `one_line_reason` "比另两条" 修正为 "若有同品牌变体则说明取舍,否则给命中证据" | Codex 新盲点 #5 |
| P1-7 | refine `delivery_only: false vs null` 语义澄清 — 没提一律 null,只有明确表达"不要外卖/堂食"才 false | Codex 新盲点 #4 |
| P1-8 | refine 字段空洞段措辞修订 — 改为 "如实记录为 unsupported_in_recall,L1/L2 暂不保证执行;narrative 不得声称已过滤" (与 D-085 一致) | Opus P0-2 降级 |
| P1-9 | rerank tool_use schema description 微调 — 在现有 `_RERANK_TOOL` description 补 ordering 约束 ("array order == final display order; rank == position+1; first n-n_explore false then n_explore true"),同步 CLI no-tool 段 | Opus rerank P0-2 降级 |

---

## 4. 7 个原子任务清单 (待 `/plan-brief` 展开)

| # | 任务 | 工作量 | 影响文件 | 覆盖 finding |
|---|---|---|---|---|
| T-PR-01 | Refine prompt 边界修订 (字段空洞文案 / expanded 闭集 / delivery_only / low_caffeine / reject_previous 正反例) | ≤4h | `prompts/parse_refine_intent_v2.md` | P0-E3, P1-1, P1-2, P1-7, P1-8 |
| T-PR-02 | Refine eval fixtures 更新 (4-6 个新 case: "想吃辣但别太辣"/"下午要睡觉"/"只堂食/只外卖"/"这些广东菜都不想吃换湖南菜") | ≤4h | `tests/test_refine_intent_v2.py` | P0-E3 + P1-1,2,7 回归 |
| T-PR-03 | Rerank 健康语义归位 — §6 改为风险披露 + 不主动美化,不加 hard filter | ≤2h | `prompts/rerank_system.md` | P0-E2 |
| T-PR-04 | Rerank refine_intent 字段口径同步 V1 + 说明 V2 reference 部分消费 | ≤2h | `prompts/rerank_system.md` | P0-E1 |
| T-PR-05 | Tool schema description 微调 (ordering 约束) + 同步 CLI no-tool 段 `_CLI_OUTPUT_SECTION` + `_patch_system_prompt_for_cli` 锚点检查 | ≤3h | `chisha/rerank.py` + `prompts/rerank_system.md` | P1-9 |
| T-PR-06 | rerank `taste_match` rubric + `one_line_reason` 比较措辞修正 + `raw_understanding` 职责收紧 + explore escape | ≤3h | `prompts/rerank_system.md` + `prompts/parse_refine_intent_v2.md` | P1-3, P1-4, P1-5, P1-6 |
| T-PR-07 | 兼容性守门 — 跑 `uv run pytest tests/test_refine_intent_v2.py tests/test_rerank.py tests/test_refine_trace_persist.py -q` + `_patch_system_prompt_for_cli` 锚点测试 + baseline_l2_snapshot (仅 rerank 路径动 prompt 但不动权重,严格回归应通过) | ≤2h | 测试 + baseline | 全部 |

**总 ≤ 20h**,7 个 task 全部在 Step 1 范围内,不触召回红线,不破 D-079 trace 兼容,不引入新业务规则。

---

## 5. 待志丹拍板的分歧 (5 项)

| # | 决策 | Opus | Codex | Codex 倾向 |
|---|---|---|---|---|
| D1 | Step 1 之后是否另开 L1/L2 "真听 quality_floor / delivery_only / max_distance_km" 项目 (Faithful Refine 真兑现) | 应当 | 不在本轮 | 本轮先不放,Step 1 后开独立 D-XXX |
| D2 | 未来是否把 expanded/synonyms 迁到代码词典 | 应当 | 不在本轮 | 本轮只闭集化 prompt,迁移另开 D-XXX |
| D3 | 是否新增 V2 schema 字段 (`reject_scope` / `semantic_notes`) | 应当 | **强反对** | 不加。binary + 文案兜底足够 |
| D4 | 是否升级健康风险为新 hard filter (例 `oil_avg≥4 + processed 主菜 → 排除`) | 应当 | **强反对** | 不加。没 D-082/D-083 前不动判定 |
| D5 | 是否让 `narrative` schema required | 倾向 required | **强反对** | 保持 optional,靠 prompt 提高命中,保护 D-079 trace |

**D3/D4/D5 是范围红线,共识倾向 Codex (不动)。D1/D2 是后续规划事项,本轮不阻塞,志丹拍板后追加路线 (本设计稿不展开)。**

---

## 6. 落地流程

1. **本文件 v2 共识版** = 本提交
2. 志丹 review §5 五个分歧 → 拍板 / 微调本文件
3. `/plan-brief docs/proposals/2026-05-20-prompt-effect-optimization.md` → 拆 `specs/T-PR-01.md` ~ `T-PR-07.md` + 追加 `specs/tasks.json`
4. 志丹 review specs → `/ship-tasks` 串跑 (每 task 内部 `/run-task <id>` 走 plan → Codex 审 → 实施 → Codex 对抗审 → commit)
5. 全部 7 task done 后跑 baseline_l2_snapshot + 5-10 case 人工对比 → 标记 Step 1 完成
6. 进入 Step 2 (可读性清理) / Step 3 (压缩 + cache 修复) / Step 4 (model 切换)

---

## 附录 A: Opus v1 findings (历史归档)

v1 完整 findings 已被 Codex 对抗审消化进 §3 共识清单,以下保留作为审计轨迹:

**Opus v1 P0 (4 项, 2 项被砍 / 2 项被修正)**:
- ~~P0-1 refine 词典化 expanded/synonyms~~ → **降为 P1-1**, 本轮只闭集化 prompt
- ~~P0-2 refine 字段空洞"真做召回过滤"~~ → **降为 P1-8 文案修订**, D-085 + 代码已决"务实降级"
- P0-3 rerank 健康约束半过滤半排序 → 保留为 P0-E2, 但去掉 Opus 提议的 hard filter 公式
- ~~P0-4 rerank 新增 `output_plan` schema 字段~~ → **降为 P1-9 description 微调**, validator 已强校验无需新字段

**Opus v1 P1 (5 项, 全部保留进 P1 列表)**:
- P1-1 `reject_previous` 刚性 → 共识 P1-2
- P1-2 `raw_understanding` 拆字段 → 共识 P1-3 (改文案,不拆)
- P1-3 同品牌变体语义 → 共识 P1-6
- P1-4 `taste_match` rubric → 共识 P1-4
- P1-5 explore 稀薄 escape → 共识 P1-5

**Opus 漏看的 6 个盲点 (Codex 发现, 全部进 P0/P1)**:
1. rerank V1/V2 refine_intent schema 漂移 → **新 P0-E1** (跨文件契约破裂, 最严重)
2. `reference.relation="avoid_pattern"` 是 schema 死路 → 进 T-PR-04 顺手澄清
3. `functional.low_caffeine` 示例违反第一原则 → **新 P0-E3**
4. `delivery_only: false vs null` 语义陷阱 → 共识 P1-7
5. `one_line_reason` "比另两条" 诱导编造 → 共识 P1-6
6. `narrative` schema optional 但 prompt 说强制 → 不矛盾,T-PR-05 顺手补一条 description

---

## 附录 B: 后续阶段已识别但暂不展开 (Step 2-4)

**Step 2 (可读性)**:
- rerank 计数硬约束在 §输出方式 / §边界 / tool description 6 处重复 → 合并到一处
- refine v2 八例可减到 5 例 (湖南菜+肉多 / 辣+排除日料+30块 / 推翻+品牌+做法 / 比昨天清淡 / 冲突表达)
- rerank 字段表 + 读法示例冗余 → 砍表保 example
- rerank 顶部 HTML comment 浪费 token + 偶尔被当指令 → 挪到独立 `_dev_notes.md`
- 双 prompt 风格不一致 → 出 prompt 写作 style guide

**Step 3 (压缩 + 加速)**:
- **🔴 refine cache bug**: `refine_intent_v2.py:418-421` 注释承认 "整段 prompt = system + user 混合放在 user role" → 修 `call_text` 拆 system/user,启用 cache_system,预计 latency 8s → 3-4s
- L3 input top-K 60 → 40 (D-046 实测 31-60 仅 3 新候选, 边际低)
- rerank/refine reason 示例从 8 例减到 4-5 例
- 多 cache breakpoint (Anthropic 支持 4 个,目前只用 1 个)

**Step 4 (model 切换)**:
- refine 改 haiku-4.5 (任务简单 slot filling, 预计 latency 3s → 1-2s)
- L3 A/B haiku vs sonnet (5-10 case 人工对比 reason 质量)
- 若 ANTHROPIC_API_KEY 可用,直连 vs OpenRouter A/B (-1~2s 中转延迟)

每项独立 evaluate,不一次性堆叠。
