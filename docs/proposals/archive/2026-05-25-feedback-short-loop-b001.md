# B-001 反馈短链路 — 差评即时生效 (短链路补 L1 慢链路缺口)

**日期**: 2026-05-25
**状态**: v2 定稿 — codex 共商达成 (§8.1-8.2) + 志丹 4 点拍板完成 (§8.5)。**待 review → TaskCreate 进实现**
**第一原则 (拟新立 D-098)**: **Responsive Feedback — 用户每一次 👍/👎 必须在下一次推荐就被可感知地响应; "差评不生效" = 信任崩塌.** 短链路 (实时 / 餐厅·菜品级 / 带衰减) 补 L1 慢链路 (LLM 抽取 / 泛化 / 长期稳定) 的缺口, 二者独立互补.
**参照**: 对标 Refine v2 优化 (D-080 Faithful Refine + D-094 字段闭包 + D-090 gating) 的思路与实现范式 — 第一原则先行 / 双层互补 / gating 守 0-diff / clock 注入 / 显式告知用户.

---

## 1. 背景: B-001 根因 (代码地图已验证)

反馈 → 推荐**只有一条慢链路**: `feedback_store → l1_extractor (LLM) → long_term_prefs.json → score.taste_match`。三处断点:

1. **L1 保守 + 阈值**: 信号弱/矛盾/样本 < 阈值 → 抽空 (`{"boost":[], "penalty":[]}`)。沙盒 9 餐实测抽空 → `load_prefs()` 返 None → `taste_match=0`。
2. **score.py 不读 rating**: `score_combo` 14 维里没有任何一维消费 `feedback.rating`。rating 仅在 `l1_extractor.aggregate_inputs` 聚成直方图喂 LLM 上下文, **不直接进打分**。
3. **recall.py 不读 rating**: `diversity_filter` (recall.py:341) 只看 meal_log 时间戳 ("吃过没"), 7 天 hard cooldown 对 👍👎 **行为完全一致**。7 天后差评店照样召回、照样同分。

**净效果**: 中期 (30-60 天) 餐厅/菜品级差评对排序 **0 影响**; 冷启动期 (L1 抽出 token 前) 完全空白。这是留存杀手 (D-097 列为自用刚需 P0)。

### 数据地基: feedback_store 自包含 (v2 修正, 取代 v1 的 meal_log JOIN)

**v1 草稿提议 session_id JOIN meal_log — 已验证不可取**: `meal_log.jsonl` 落盘时**丢弃 dish_id** (只留 `main_ingredient_type + canonical_name`), 且 `canonical_name` **非唯一** (跨店重复 1349 / 同店重复 147) → 无法当菜品身份键。

**v2 正解 — 信号全部从 `feedback_store` 自包含取齐** (无需 JOIN):
- `feedback_store.feedbacks[sid]`: `{rating, repurchase_intent, submitted_at, accepted_rank, ...}`
- `feedback_store.sessions[sid]`: **冷存完整 RecommendResponse**, 含 `candidates[].dishes[].dish_id` (源数据全量唯一 `d_{rest}_{dish}`)
- `accepted_rank` → `sessions[sid].candidates[rank-1]` → 该 combo 的 `restaurant_id` + `dishes[].dish_id`
- **一个 store 同时给出**: rating/repurchase (信号强弱) + restaurant_id (餐厅级身份) + dish_id 列表 (菜品级身份) + submitted_at (衰减用 days_ago)
- `meal_log` 仍只服务 recall 既有 7 天 cooldown (不动)。
- **降级规则**: 若某 sid 无 cold-store 完整响应 (老数据 / 未存) → 该餐降级为 restaurant-only (从 `accepted` 记录取 restaurant_id) 或跳过, 不报错。

---

## 2. 方案: 短链路 = 新增 `feedback_recency` 信号, 双注入 (score + L3 narrative)

### 2.1 新模块 `chisha/feedback_signal.py` (parallel `l1_prefs.py`)

纯函数, 输入 `feedback_store` (自包含, 见 §1 数据地基), 输出餐厅级 + 菜品级 recency-weighted 信号 dict。

```
build_feedback_signal(feedback_store, today, *, root=None) -> dict
  # 遍历 feedbacks[sid] → 取 rating/repurchase + 经 accepted_rank 定位 sessions[sid] combo
  #   → restaurant_id + dish_id 列表 + days_ago(submitted_at)
  # 信号源 = 组合 C (§8.5): 抑制 strong = rating==-1 且 repurchase==0; 抑制 mild = rating==-1 或 repurchase==0;
  #   boost = rating==1 且 repurchase==2; 冲突 (rating/repurchase 反向) → repurchase 为准 (志丹拍板 Q-B)
  # 按衰减曲线折算 → {
  #   "restaurant": {rid: w∈[-1,1]},          # 餐厅级 (主, 干净归因)
  #   "dish": {dish_id: w∈[-1,1]},             # 菜品级 (辅, 弱; 跨 combo 累积抵消归因噪声, 见 §8.5)
  #   "recall_evict": {rid: until_days}        # 强负 → recall 30天剔除清单
  # }
  # today 走 clock.today(root) (D-077 硬约束); 无反馈 / 已衰减 → 空 dict (gating 0-diff 前提)
```

为什么独立模块而非塞 score.py: mirror `l1_prefs.py` 分层 (信号构建 ≠ 打分消费), 且 What-if 需 override 注入 (见 §2.4)。**单次构建** (§8.1 共识): API recommend 起点构建一个对象, recall/score/L3/trace 共享同一引用, 严禁各自读盘重算。

### 2.2 注入点 1 — `score.py` 新维度 `feedback_recency` (主, 保证排序真降)

`score_combo` 加第 15 维 `feedback_recency`, mirror `taste_match` / `intent` 的 gating:

```python
"feedback_recency": feedback_recency_bonus(combo, fb_signal) * _w("feedback_recency"),
# fb_signal=None / 该 restaurant 无近期反馈 → 0 → 对无反馈 combo 0-diff (mirror intent=None)
```

`rank_combos` 加 `feedback_signal_override=_UNSET` sentinel (复刻 D-079 `l1_prefs_override` 模式): 不传→`build_feedback_signal(...)`; 显式传→用之 (What-if 冻结)。

### 2.3 注入点 2 — `recall.py` 强负延长冷却 (辅, 只对最强差评)

`diversity_filter`: 命中**强负** (rating=-1 且 repurchase=0, 见 §8.5 Q-A) 的 restaurant, `no_same_restaurant_within_days` 从 7 延长到 ~30 (带衰减)。**不做永久 hard avoid** — 避免一次差评永久误杀整店 (Faithful 但不过度)。

### 2.4 注入点 3 — L3 narrative (透传, mirror D-083/D-085)

把"近期差评店清单"透传 rerank prompt, 让 narrative 能忠实说"你上次说不喜欢 XX, 这次避开了" (Faithful Refine 推论 2: 失败/响应显式告知)。**严守 D-085 第一句**: narrative 必须在 score 真生效后才上线, 否则 LLM 自信编"已避开"实际没降分 = 信任放大器隐患。

### 2.5 守门: gating + baseline_l2_snapshot (mirror D-090)

- 无反馈 combo → `feedback_recency=0` → 对旧 baseline **0-diff** (先 disable 信号跑一遍对旧基线验证)。
- enable 后跑新基线, 人工验证 diff **仅落在有近期反馈的 restaurant/dish 上, 且方向正确** (差评降分 / 好评升分)。
- 新增 `test_feedback_signal_snapshot` (mirror `test_l2_refine_snapshot_d090`): 构造 fixture feedback, 断言强负店排名下降、强正店 cooldown 后上升。
- What-if 零 runtime read (D-079): trace frozen 加 `feedback_signal_snapshot`, `what_if_rerun` 用冻结值不重算。

---

## 3. Open Questions (讨论留档 — 全部已解)

> **Q1-Q6 已全部 close, 见 §8.5 拍板表 + §8.1 共识 + §8.4 默认。下面保留当时的选项与取舍推理 (留档), 不再是开放问题。**
> 映射: Q1 信号源 → 组合 C (§8.4); Q2 hard/soft → §8.5 Q-A (软压+强负剔除); Q3 衰减 → §8.4 默认 (照搬预案); Q4 F-008 → §8.5 Q-D (不做); Q5 粒度 → §8.5 Q-C (**做菜品级**, dish_id 走 feedback_store.sessions); Q6 香菜 → §8.4 默认 (降级)。

### Q1 [codex+志丹] 信号源: rating vs repurchase_intent vs 组合?

| 选项 | 抑制触发 | boost 触发 | 取舍 |
|---|---|---|---|
| **A 纯 rating** | `rating==-1` | `rating==1` | 最直觉 (用户 👍👎 心智), 但混"好吃度"和"想不想再吃" |
| **B 纯 repurchase_intent** | `repurchase==0` | `repurchase==2` | 语义最贴"要不要再推", 但用户不一定填 (是 calibration 二级信号) |
| **C 组合 (拟推荐)** | `rating==-1` **或** `repurchase==0` | `rating==1` **且** `repurchase==2` | 抑制宽松 (任一强负即压)、boost 保守 (双正才升), 防误 boost |

拟推荐 C。风险: D-063~D-065 "三类信号语义不可混" — 但本场景是"再推决策"而非"打分维度复用", 是否算违反? **codex 拷问点**。

### Q2 [志丹] hard 拉黑 vs soft 扣分强度?

- 拟推荐: **soft 扣分为主 (score 强负, 足够压过健康维度淹没) + 强负 recall 延长冷却到 30 天**, 不做永久 hard avoid。
- 志丹可能想要更强 ("差评直接消失一段时间")。**需拍板**: 差评店是 (a) 排名靠后但仍可能出现, 还是 (b) N 天内直接 recall 剔除?

### Q3 [志丹] 衰减曲线 (BACKLOG 预案已给草数)

- 差评 `rating=-1`: 0-30 天强抑制 → 30-60 天线性衰减 → >60 天无影响
- 好评 `rating=+1`: 0-7 天 cooldown (recall 已有, 避连吃) → 7-30 天弱 boost → >30 天衰减
- 待定: 线性 (可解释可调, 拟推荐) vs 指数; 天数阈值是否照搬预案。

### Q4 [志丹] F-008 (反馈 3 维 不合时宜) 本轮做不做?

- 风险: 用现有 rating=-1 强抑制会**误伤"本身爱但那天不想吃"** → 污染 30-60 天。F-008 加"不合时宜"维度区分。
- 拟推荐: 本轮**不扩 schema**, 用 C 方案的 `repurchase==2` 部分缓解 (想复购则即便当天 rating 低也不强抑制); F-008 作 follow-up。
- 反方: 既然开反馈优化专题, 一并把 schema 改干净 (但牵动前端 UI + feedback_store + D-066/067 readonly)。

### Q5 [codex] 粒度: 餐厅级 + 菜品级, 不做三维泛化 — 对吗?

- 拟定: 短链路只压"差评的那家店/那道菜" (忠实直觉), **不泛化**到 `(cuisine,cooking,ingredient)` — 泛化是 L1 慢链路 (D-025) 职责。
- codex 拷问: 菜品级信号粒度用 `dish_id` 还是 `main_ingredient_type`? 数据是否支撑?

### Q6 [降级] 香菜连吃 (B-001 现象之二)

- "连吃 non-protein 配料 (香菜) 无法 cooldown" 是 recall ingredient 粒度问题 (现仅红肉/白肉/海鲜/豆制品 走 ingredient cooldown), **与 rating 无关**, 依赖更细 dish 配料标签 (类比 F-011 数据缺口)。
- 拟**降级/本轮不做**, 核心 B-001 = 差评不生效 (a)。

---

## 4. 用户视角行为表 (修后)

| 场景 | 现状 | 本方案后 |
|---|---|---|
| 给某店 👎, 8 天后 | 照样推、同分 | score 强负 → 排名垫底; 强负则 recall 30 天内不召回 |
| 给某店 👍 | 7 天 cooldown 后行为同 👎 | 7 天 cooldown → 7-30 天弱 boost (爱吃的店更易回到 top) |
| 差评店进了 top60 | L3 narrative 不知情, 可能选 | score 已压低; narrative 可忠实说"已按你上次反馈避开 XX" |
| 连吃香菜 | 无法 cooldown | 本轮不变 (Q6 降级) |
| 无任何反馈 (冷启动/新数据) | — | `feedback_recency=0`, 行为 = baseline 0-diff |

---

## 5. 风险红线

**high-risk 文件白名单触碰** (需 baseline_l2_snapshot 守门 + Codex commit-前 diff review):
- `chisha/feedback_signal.py` — **新增核心模块** (改白名单单一权威源 = CLAUDE.md § 推荐链路改动红线, 须同步加进去)
- `chisha/score.py` — 加第 15 维 `feedback_recency` + `feedback_signal_override` sentinel
- `chisha/recall.py` — `diversity_filter` 强负延长冷却
- `chisha/rerank.py` — L3 prompt 透传近期差评清单 (narrative)
- `chisha/api.py` — recommend 链路 wire `build_feedback_signal` + 透传 root
- `chisha/debug_what_if.py` — frozen snapshot 加 `feedback_signal_snapshot` (D-079 零 runtime read)
- `chisha/trace_store.py` — trace frozen schema bump (加新字段, `TRACE_SCHEMA_VERSION`++)

**baseline_l2_snapshot**: 无反馈 combo 必须 0-diff (信号 disable 跑对旧基线), enable 后 diff 仅落反馈店且方向正确。
**clock 注入 (D-077)**: 衰减 today 必走 `clock.today(root)`, 禁裸 `dt.date.today`。
**D-085 narrative 后置**: narrative 透传必须在 score 真生效之后上线。

---

## 6. 工程量粗估 + 子任务草拆 (待 codex 共商后正式 TaskCreate)

| 任务 | 工作量 | high-risk |
|---|---|---|
| T-FB-01 · `feedback_signal.py` 新模块: feedback_store 自包含取数 (accepted_rank→cold-store combo→restaurant_id+dish_id) + 组合C信号 + 衰减 + 餐厅/菜品双级 + 降级规则 + 单测 | ~6h | 高 (新核心模块) |
| T-FB-02 · `score.py` 加 `feedback_recency` 维 (餐厅级强 + 菜品级弱叠加) + override sentinel + 权重 | ~4h | 高 |
| T-FB-03 · `recall.py` 强负 (rating=-1 且 repurchase=0) 延长冷却到 30 天 | ~3h | 高 |
| T-FB-04 · `api.py` recommend 起点单次构建 signal + 全链路透传同一对象 + root | ~3h | 高 |
| T-FB-05 · `rerank.py` L3 narrative 透传差评清单 (D-085 后置, 最后做) | ~3h | 高 |
| T-FB-06 · `debug_what_if.py` + `trace_store.py` frozen `feedback_signal_snapshot` + schema bump | ~4h | 高 |
| T-FB-07 · penalty 量纲标定 (top5 cutoff margin 法) + baseline_l2_snapshot 守门 + `test_feedback_signal_snapshot` + eval | ~5h | 中 |
| **总** | **~28h** | 6 个 high-risk 文件 + 1 新模块 |

> 注: dish_id 数据全在 feedback_store cold-store, **本轮不改 meal_log schema** (recall 既有 cooldown 不动)。

---

## 7. 落地流程 (mirror D-094 流程)

1. ~~v1 草稿~~ ✅ → v2 定稿 (含 §8 共商 + 拍板)
2. ~~调 `codex:rescue` 共商~~ ✅ (§8.1-8.2; What-if 注入 + 粒度数据源拷问已处理)
3. ~~志丹拍板 Q-A/B/C/D~~ ✅ (§8.5)
4. **← 当前: 志丹 review brief → TaskCreate 拆 7 task (一原子动作一 task)**
5. 逐 task 实施 → 每 high-risk task **commit 前强制 `codex:rescue` diff review**
6. 全 done → baseline_l2_snapshot + 5-10 case 人工对比 + 前端自测 (若动反馈 UI) → D-098 落 decisions.md (正式) + B-001 标 resolved + CLAUDE.md 白名单加 `feedback_signal.py`
7. F-008 / Q6 香菜 留 BACKLOG follow-up
8. **合回 main 前置**: 先把 main 上未提交的 D-097 6 文件 commit (否则撞 decisions.md/BACKLOG.md 同步冲突)

---

## 附录: 与现有决策/BACKLOG 关系

- **B-001** (BACKLOG): 本方案直接 resolve (a) 差评不生效; (b) 香菜连吃 降级留 BACKLOG
- **F-008** (反馈 3 维): Q4 待拍板, 拟 follow-up
- **D-076** (L1 长期层): 不动。短链路与 L1 慢链路双层互补 (本方案第一原则)
- **D-090~092** (L2 信号校准): 复用 gating 0-diff 范式, 不改其数值
- **D-025** (personal_offsets 三维泛化): 泛化仍是 L1 职责, 短链路不碰
- **D-079** (What-if 零 runtime read): frozen snapshot 必须含新信号
- **D-097** (自用为主): 本方案是其列的 P0 自用刚需

---

## 8. Codex 共商结论 (2026-05-25)

### 8.1 已达成共识 (锁定, 不再讨论)

- **整体架构 AGREE** (Q1): `feedback_signal.py` + 三注入成立 (共商时数据地基写的是 session_id JOIN meal_log, 共商后查证改为 **feedback_store 自包含**, 见 §1 v2)。**强化硬约束**: signal **API 单次构建一个内存对象**, 由 recall / score / L3 narrative / trace 落盘**共同消费同一对象, 严禁各自读盘重算** (防反馈提交竞态导致 trace 与排序不一致, 同时满足 D-079)。
- **recall hard vs soft AGREE** (Q6): soft 扣分为主 + 强负 30 天延长冷却 = 既有 7 天多样性机制的**语义强化, 非永久封禁**。永久 hard avoid 只来自用户显式 `preferences.avoid_restaurants` (沿用现硬过滤语义)。强负超 30 天仍需处置 → 走"多次一致证据"的新决策, 不在短链路隐式升级。
- **L3 narrative 纪律 AGREE**: L3 **只能叙述 recall/score 已执行且可验证的避开结果**, 不能编 (D-085)。

### 8.2 Codex 两处拷问的处理

- **粒度 (Q5) — Codex 建议砍菜品级, 志丹 override 保留**: Codex 复核出 `meal_log` 落盘只有 `main_ingredient_type` + `canonical_name`、**无 `dish_id`**, 故建议本轮只做餐厅级。志丹拍板**保留菜品级** (§8.5 Q-C)。数据路径改走 **`feedback_store.sessions` cold-store** (含真 `dish_id`, 见 §1 v2; 比 Codex 设想的 `sessions/{sid}.json` 更可靠 — 后者只有 dish_names)。Codex 的"禁用 `main_ingredient_type` 冒充菜品级 + 补降级规则"两条要求, 以 dish_id 真身份 + §8.5 归因噪声处理 + §1 降级规则**满足**。
- **What-if (Q-Codex) — override 形式贯穿 L2+L3, 非"trace 再建一份"** (已采纳): 必须 mirror `l1_prefs_override` —— 生产路径推荐开始单次构建 signal, 同一对象供 recall/score/narrative/`api._build_trace` 落盘; What-if 重跑 `rank_combos` + `rerank` 时以 `feedback_signal_override` 注入冻结值。**recall 不在 What-if 重跑** (已冻结 `l1_combos` 足以复现), 故 What-if 不读 feedback store。

### 8.3 待志丹拍板 4 个 decision point [已拍板 → §8.5]

- **Q-A 强负可见性目标**: 差评店 30 天内应 (a) 退出 **top5** (仍在 L3 候选池, 只是不进最终 5 条) 还是 (b) 退出 **L3 top60** (连 LLM 都看不到)? → 这决定 penalty 量纲 (Codex: 关闭反馈取基准分 → 算差评店最佳 combo 相对目标 cutoff 的 margin → penalty 覆盖该 margin 分位 + 余量 → snapshot/eval 校验误杀率, 不拍脑袋) + 是否需要 recall 硬剔除。
- **Q-B 冲突规则**: `rating=-1` 但 `repurchase_intent=2` (不好吃但想再吃 / 或反之) 时, 短链路按哪个走? v1 草稿默认负向覆盖, Codex 指出**无决策依据**。
- **Q-C 菜品级粒度本轮做不做**: 仅餐厅级 (Codex 推荐, 数据现成) vs 额外接 `sessions/` 快照做菜品级 (+工作量, 数据需验证覆盖率)。
- **Q-D F-008 (反馈 3 维 "不合时宜") 本轮做不做**: 不做则用 `repurchase_intent` 部分缓解"本身爱但那天不想吃"误伤; 做则扩 schema + 前端 UI + 守 D-066/067 readonly。

### 8.4 采用默认 (志丹未否决即生效)

- **衰减曲线**: 照搬 BACKLOG 预案 — 差评 0-30d 强抑制 / 30-60d 线性衰减 / >60d 无; 好评 0-7d cooldown / 7-30d 弱 boost / >30d 衰减。线性 (可解释可调)。
- **香菜连吃 (Q6 现象之二)**: 降级留 BACKLOG (recall ingredient 粒度 + 数据缺口, 与 rating 无关)。
- **信号源框架**: 组合 C (抑制 = rating==-1 或 repurchase==0; boost = rating==1 且 repurchase==2)。**不违反 D-063~065** (Codex: 禁的是改写成同一字段语义, 不禁决策层并列消费两个原始字段; 但 F-008 落地前组合信号不得外推为长期口味结论)。

### 8.5 志丹拍板结论 (2026-05-25)

| 点 | 拍板 | 落地 |
|---|---|---|
| **Q-A 差评强度** | 软压为主 + 强负剔除 (自然分级) | 一般差评 (rating=-1) → score 强负压出 top5; **强负 (rating=-1 且 repurchase=0)** → recall 30 天剔除 (退出 top60)。penalty 量纲走 Codex 法: 关闭反馈取基准分 → 算差评店最佳 combo 相对 **top5 cutoff** 的 margin → penalty 覆盖该 margin 分位 + 余量 → snapshot/eval 校验误杀率 |
| **Q-B 冲突规则** | 以 `repurchase_intent` 为准 | rating/repurchase 反向时听 repurchase。`rating=-1 且 repurchase=2` (难吃但想再吃) → **不抑制**; 天然缓解"本身爱但那天没发挥好"误伤 |
| **Q-C 菜品级** | **本轮做** (志丹 override Codex 的"仅餐厅级") | 数据走 §1 v2 正解 (feedback_store.sessions cold-store 取 dish_id, 非 meal_log)。见下"菜品级归因噪声处理" |
| **Q-D F-008** | 本轮不做, follow-up | 用 repurchase_intent 缓解; F-008 留反馈优化专题下一步 |

**菜品级归因噪声处理 (Q-C 落地关键)**:
- 问题: 反馈是**餐级** (rating 对整个 combo), 但 combo 有 2-4 道菜 → 无法精确归因到"哪道难吃"。若对 combo 内所有 dish_id 等额扣分 = 噪声 (可能只 1 道菜的锅)。
- 解法: 菜品级是**弱信号** (penalty 量纲显著 < 餐厅级), 且**跨 combo 累积** — 同一 dish_id 在多个差评 combo 反复出现才积累成强信号 (重复证据自洽抵消单次归因噪声)。单次差评对每道菜只给弱权重。
- 与餐厅级关系: 餐厅级是主 (归因干净)、菜品级是辅 (归因弱 + 累积)。二者叠加进同一 `feedback_recency` 维度。
