# 今天吃点啥 · 路线图

> 这份文档说清楚**什么时候做什么、什么不做**。
> 防止偏航：实现某个功能前先看这里它在哪个版本。
> 已砍清单尤其重要——避免反复讨论同一个被否决的想法。
>
> 项目名：今天吃点啥 · 代码名：`chisha`

---

## 当前状态

**Phase 0 工程侧已收尾**（2026-05-15）—— 「原则派点餐执行外包」定位收敛 + L0 方法论 spec 抽象 + 推荐 L1/L2/L3 全跑通 + Web SPA + V1.1 反馈 + FastAPI 13 端点。剩下 Step 2 自用一周（用户行为侧）→ Phase 1 同事推广。

**当前状态（2026-05-15）**：

- 打标：v3 全量重打两 zone 13,240 菜（D-032）；dual-model golden set 171 条（D-036, Opus+Codex 共创, 4 大字段一致率 99.27%）；6 模型横评后生产默认 `deepseek-v4-flash`（D-037, field acc 88.9%, 100万条 $100）。
- 推荐 V2 链路端到端跑通：Context 注入 / score V2 ~12 维 / LLM 精排 top60→5（D-035/D-046）/ refine + session（D-033 V2.1）/ LLM 抽象 Phase 1 provider auto-detect（D-038, 商家去重兜底）。
- **推荐调试台已上线**（[D-039](DECISIONS.md#d-039)）：FastAPI on port 8765, instrumented V2 管道, L1/L2/L3/Final 四段折叠 + 16 维 score breakdown + LLM payload 全可见 + profile 临时覆盖 + combo 追溯 + mood 三栏对比。
- **召回硬过滤升级**（[D-041](DECISIONS.md#d-041)）：双层架构 `hard_max_*` 召回 ban / `prefer_max_*` 打分扣；新增 ETA / combo 总价 / 餐厅/主蛋白/烹饪/菜系 6 类硬黑名单。
- **combo 生成参数化**（[D-040](DECISIONS.md#d-040)）：多蛋白多蔬菜由 profile 注入；召回总 combos 454 → 2206。
- **L2 cap + 重设计 + 反馈闭环**（[D-042](DECISIONS.md#d-042) / [D-043](DECISIONS.md#d-043) / [D-045](DECISIONS.md#d-045)）：4 层 cap（restaurant/brand/cuisine/food_form）防扎堆；砍 3 个死权重；改活 popularity/variety/taste/context；加 unforgivable penalty；反馈闭环 P3 落地（`chisha/long_term_prefs.py`）。**top30 score 跨度 0.34 → 4.997（15×）**。详见 [`RECOMMEND_PRINCIPLES.md`](RECOMMEND_PRINCIPLES.md)。
- **profile.yaml 真实化**（[D-044](DECISIONS.md#d-044)，2026-05-13）：从用户口述 + 历史订单回顾重建 profile（goal/zones/min_protein_g/avoid_dishes/price/taste_description 全量校正）。沉淀两个普适方法论到 [RECOMMEND_PRINCIPLES](RECOMMEND_PRINCIPLES.md) §12 §13：**偏好层 ≠ 行为层** + **隐藏目标识别**。
- **L3 精排 prompt + payload 重构**（[D-046](DECISIONS.md#d-046)，2026-05-13）：①top30 → top60（二审实测 shenzhen-bay top41-60 有 10 brand / 12 餐厅的真实多样性增量，top61+ 才同质化崩；不上 80/100 避开同分平台 + 输出漏号风险）；②prompt 拆 system / user, system 进 Anthropic prompt cache（~1.7k tokens 100% 命中）；③payload 紧凑符号化（每菜一行约 80-100 chars, 默认值省略）；④health_flags 从 LLM 输出移除, 改 rerank.py 规则后处理；⑤加观测埋点：每次记录 LLM 选中的 combo_index 分布。实测 input tokens ~22k → ~6.2k（cache 命中时, 省 72%, N 还涨了一倍）。
- **L3 tool_use 重构**（[D-047](DECISIONS.md#d-047) L3 部分，2026-05-14）：D-046 上线后 sonnet-4.6 在 want_light 等复杂 mood 撞英文 CoT 占满 max_tokens 致 fallback。①**tool_use forced schema** 替代 json_mode（V2 实测 100% 稳定输出）；②**opus-4.7 默认**（V3+V4 矩阵实测 opus 比 sonnet 更尊重 taste、一致性更高）；③top60 保留（V3 验证多样性增量）；④`cache_control: ephemeral` 在 OR 路径真生效（V5 实测 cached=3748t 省 23%）；⑤抽 `_run_llm_rerank()` 共享 helper 消灭 debug/prod 双份代码漂移；⑥强断言 stop_reason + tool_name. 实测 6 case × 3 重复 = **17/18 成功率（vs D-046.1 的 67%）**, 平均延迟 12s（vs 50-80s）。后续 L3 改动必读 [`docs/L3_RERANK_REDESIGN.md`](L3_RERANK_REDESIGN.md)。
- **LLM Provider 抽象 + Claude Code CLI 路径**（[D-047](DECISIONS.md#d-047) provider 部分，2026-05-14）：`chisha/llm_providers/` 拆三 provider（anthropic_api / openrouter / claude_code_cli），`llm_client.py` 成薄路由层。`profile.yaml.llm.provider` + 环境变量 `CHISHA_LLM_PROVIDER` 控制；auto-detect 优先级 ANTHROPIC_API_KEY > Claude Code 订阅 > OPENROUTER_API_KEY。自用本机走订阅省 ¥24-120/月，分发用户可改配置走 OpenRouter。10 个隔离 flag 防 Claude Code 默认 system / hooks / CLAUDE.md 污染；env 过滤 ANTHROPIC_*/OPENROUTER_* 防订阅路径被付费 API 劫持；Popen + start_new_session + PR_SET_PDEATHSIG 防 orphan。spec + plan + 真 Codex 三轮 review 闭环（[详见](superpowers/specs/2026-05-14-claude-code-cli-provider-design.md)）。
- **L3 双路径收口**（[D-048](DECISIONS.md#d-048)，2026-05-14）：D-047 Part A (tool_use 主路径) 与 Part B (CLI provider) 同日 merge 协同 gap — CLI 不支持 tool_use 但 rerank 硬编码 tools 致 NotImplementedError 静默 fallback。修法：①rerank 层做 provider 分流，CLI 走 prompt 软约束 + 三层 JSON 解析（含 `JSONDecoder.raw_decode`），主路径保留 tool_use；②**配置错 hard-fail**：`_resolve_provider` 抛错时返回 `status="config_error"` 不再被外层 except 吞，区分"L3 真跑通 / fallback / 配置错根本没跑"三态；③trace 加 `status` / `resolved_provider` / `config_error` 结构化字段，调试台 L3 section 直接给三态 badge + provider/latency 一行带出；④Codex 独立 review 闭 1 BLOCKER + 5 MAJOR + 2 MINOR。新增 13 个测试。
- **CLI 精排运行时纠错**（[D-050](DECISIONS.md#d-050)，2026-05-15）：CLI 路径默认 model sonnet → opus 后, dry_run 暴露 ~20% session 触发 `explore 数量错误` fallback —— opus 质量贪心(挑 4 高分 exploit + 1 mid-band explore, 主动放弃第二个 explore 槽). 加重 prompt 反向恶化(100% fallback). 改用 **validate→retry→fallback** 闭环: ①validator 返回 `(cands, code, detail)` 结构化三元组, `RerankValidationCode` 稳定 enum; ②retry 触发按 code allowlist (`OVER_N_MAX` / `EXPLORE_COUNT_MISMATCH` / `EXPLORE_POSITION_WRONG`), 不再用字符串匹配; ③CLI 路径限定一次 retry, 显式纠错 prefix 含"其余 system prompt 规则全部仍生效"(Codex Q3 防质量退化); ④trace 加 `retry_attempted/succeeded/first_failure_code/retry_latency_ms`. 实测 20/20 session 成功(0-10% retry), 商家分布 12+ 家。
- 架构重构推迟到 V1.5（[D-030](DECISIONS.md#d-030)）。
- **测试**：381 单测全过（D-048 新增 13 个：CLI 分流 / config_error / prompt patch / parser 边界）+ 5 个 integration e2e 全过（opt-in `requires_claude_cli` marker）。
- **产品形态翻案**（[D-051](DECISIONS.md#d-051)，2026-05-15）：V1 主交互改 Web localhost SPA（用户视图 `/` + 调试台 `/debug` 双路由），飞书降级为 V1.5 推送 + deeplink 通道。D-022 标 partial superseded。理由：飞书卡片放不下 refine 多轮 / profile 编辑 / 高密度反馈；Web + claude.ai/design 协同体验迭代速度远超飞书卡片定制；调试台和用户视图共享 API / 组件 / 状态，改一次推荐链路两边同步。
- **Web SPA V1 落地**（[D-052~D-055](DECISIONS.md#d-052)，2026-05-15）：`apps/web/` 子项目（Vite + React 18 + TS + React Router + Tailwind）从 claude.ai/design 原型搬迁完成。HomePage / ProfilePage / HistoryPage 全量；mock + 真接口双模式（`VITE_USE_MOCK`）。新决策：①D-052 Accept 改 inline 持久锁定 + 复制店名（不假装 deeplink），②D-053 refine 顶部面包屑 + 输入框置顶 + smooth-scroll，③D-054 skip-meal escape hatch（新增 `POST /api/skip`），④D-055 同 session 抑制 unfed banner。文案规范 + 视觉系统沉淀到 [`docs/style-guide.md`](style-guide.md)；前后端契约见 [`docs/api.md`](api.md)。
- **V1.1 反馈系统落地**（[D-056~D-068](DECISIONS.md#d-056-navbar-加反馈-tab--角标-v11)，2026-05-15）：第二轮设计迭代，反馈链路从 placeholder 改成完整 7 步 user journey。13 条新决策分三组：①入口架构（D-056 NavBar tab + 角标 / D-057 banner 升级 stack + 多条堆叠 / D-058 `/feedback` 反馈中心三段 / D-059 history 行可点 / D-060 snooze vs stop 两态语义），②表单内容（D-061 5 变体方法论 → D-062 选 E 渐进披露 + 借 D 复盘卡 / D-063 calibration·behavior·gut 三类信号框架 / D-064 头部 gut 跟 behavior 分离 / D-065 展开 4 维 + 每行对齐 prediction），③生命周期（D-066 一次提交永久 readonly / D-067 append-only timeline / D-068 V2 砍单清）。schema 全量改写：砍 `rating_taste`/`rating_satisfaction`/`feedbackChips`，加 `rating: -1\|0\|1` + 4 维 calibration/behavior + comments[] timeline。新增 5 文件 / 改写 10 文件 / 删 FeedbackPlaceholder。mockApi 7 个端点全实现。详见 [IMPL_LOG D-056~D-068](IMPLEMENTATION_LOG.md#d-056d-068-执行记录--v11-反馈系统落地-appsweb)。
- **FastAPI 后端 13 端点联调完成**（[IMPL_LOG D-069](IMPLEMENTATION_LOG.md#d-069-执行记录--fastapi-v1--v11-后端-13-端点联调--codex-review-修复)，2026-05-15）：兑现 D-051~D-068 + `docs/api.md` §5 契约，V1 推荐链路 6 个（recommend/refine/accept/skip/profile/history）+ V1.1 反馈链路 7 个全部装上，单 JSON 文件 `logs/feedback/store.json` 落盘（用户决策走单文件 v.s. SQLite，V1 单用户够用），apps/web SPA 静态托管在 `/`，老调试台挪 `/debug`。Codex review（D-036 dual-model audit 模式）发现 4 MED（写盘失败静默 / SPA path traversal / corrupt store 静默清空 / feedback schema 未约束）+ 6 LOW（debug 边界 / today 4xx / comment ID 碰撞 / naive datetime / limit 边界 / quick default），全修后验证通过。前后端真接口全链路 ready。
- **产品定位收敛**（[D-070](DECISIONS.md#d-070-产品定位收敛到原则派点餐助手--三层信号模型-v1)，2026-05-15）：D-069 后端联调后，对首屏 mood picker 做产品复盘 → 定位明确为「原则派点餐执行外包」（已认定一套吃法但每天落地费力的用户），明确不服务目标缺失型。三层信号模型沉淀：L0 方法论层 (profile + spec) / L1 长期反馈层 (V1.1 已建) / L2 当下 session 层 (refine 文本)。Phase 路线改三段线性 (Phase 0 自用 → Phase 1 同事推广 → Phase 2 双向扩展)。
- **砍 mood picker + want_soup 关键词识别**（D-071 **已 superseded by [D-073](DECISIONS.md#d-073-refine-走结构化意图-refineintent--重召回-让用户主动表达诉求真正生效)**, 2026-05-15 `e4db6e9` → 2026-05-16 整体改 D-073）：D-071 砍前端 mood picker 的产品决策仍生效, 但后端 `infer_refine_mood` want_soup 关键词识别已被 D-073 `RefineIntent.flavor_tags=["soup"]` 取代; `logs/refine_mood_trace.jsonl` 归档为 `.legacy.jsonl`.
- **refine 结构化意图链路**（[D-073](DECISIONS.md#d-073-refine-走结构化意图-refineintent--重召回-让用户主动表达诉求真正生效)，2026-05-16）：用户实测"想吃点湖南菜，然后肉多一点"暴露 CHIP_VOCAB 封闭词表 + chip 死映射 + refine 不重召回 3 个结构性约束. 拆 parse_feedback (餐后) / parse_refine_intent (餐中); 开放 RefineIntent schema (cuisine/ingredient/flavor_tags/portion/staple/price); recall 重做 (intent 进 combo 生成排序 + 三桶 + avoid 硬过滤); L2 加 intent_match_bonus 三档 (cuisine 0.50 / ingredient 0.20 / flavor 0.10) + 健康 guardrail × 0.4 + spicy_tolerance-aware; 砍 D-071 全套代码; 断 refine 端 append_feedback. Opus 设计 + Codex review 5 修订点 + 用户拍板 Q1/Q2/Q3 → 3 天工程节奏; 68 新单测, 0 回归.
- **methodology spec 抽象 + score.py 重构**（[D-072](DECISIONS.md#d-072-methodology-spec-抽象-放-phase-0-收尾-v1)/[D-072.1](DECISIONS.md#d-0721-phase-b-不等-step-2-自用数据-用-l2-trace-baseline-替代)，2026-05-15，`88b0ec7`）：L0 方法论从 score.py 硬编码抽到 `profiles/methodologies/harvard_plate.yaml`（7 必备字段 + 16 维 score_weights + 4 层 cap，严格 keyset 校验）；`chisha/methodology.py` 加载/校验/merge 接口，`load_profile` 自动 merge spec defaults（profile 显式 override）；rerank `_profile_block` 注入"方法论:"行让 L3 显式知道 baseline；D-072.1 修订：Phase B 不等 Step 2 数据，用 L2 trace baseline 替代采纳率门（`scripts/baseline_l2_snapshot.py` + `scripts/compare_traces.py` 严格 \|delta\| < 1e-6）；Codex Round 2+3 闭 3 BLOCKER + 6 MAJOR + 5 MINOR + 3 blindspot；新增 23 单测。
- **下一步（Step 2，用户行为侧）**：自用一周，工作日 7 日采纳率 ≥ 50% 是 Phase 0 验收门。不在 Claude Code 代码范围。飞书接入推到 V1.5（integrations/openclaw/ 骨架保留）。

---

## Phase 路线（[D-070](DECISIONS.md#d-070-产品定位收敛到原则派点餐助手--三层信号模型-v1) 沉淀，取代旧 V1/V2/V3 笛卡尔积）

```
Phase 0 · 自用跑通 (当前, 工程侧已收尾, 等用户行为验证)
  范围: 1 方法论 (harvard_plate) × 1 用户 × 2 zone
  步骤:
    Step 1 [完成 2026-05-15]: 砍 mood picker + want_soup 关键词识别 (D-071, e4db6e9)
    Step 2 [进行中, 用户侧]: 自用一周, 工作日 7 日采纳率 ≥ 50% (北极星)
    Step 3 [完成 2026-05-15, 用 L2 trace baseline 替代采纳率门, D-072.1]: methodology
      spec 抽象 + score.py 重构 (D-072, 88b0ec7), compare_traces 严格 0 diff
  门槛: 自己愿意每天用
        ↓ 验证: 自己用得住 (Step 2 北极星)
Phase 1 · 同方法论同事推广
  范围: 1 方法论 × N 同事 × M zone
  准入条件: 任意一套饮食原则 (不限定 harvard_plate, Codex Q4 修正), 进前先发 screener 探同事原则派密度, 阈值 30%
  关键工程: profile 解耦个人化 / data zone 拆包 / 本地数据闭环 / 接入 OpenClaw 飞书 / 必要时扩 methodology spec
  目标: ≥ 3 同事自发持续使用
        ↓ 验证: 别人也用得住
Phase 2 · 双向扩展 (顺序后议)
  方向 A: 更多方法论 (增肌 / 糖控 / 孕期 / 高血压)
  方向 B: 更多区域 / 更多用户 / 开源
  真实需求拉动哪个就做哪个
```

> 旧 V1/V2/V3 段（下方）仍保留作工程节点参考，但产品节奏以本 Phase 路线为准。Phase 0 ≈ V1 后半 + 砍 mood + spec 化；Phase 1 ≈ V2 反馈闭环成熟期 + 同事接入；Phase 2 ≈ V2.4+/V3 多区域 + 多方法论。

---

## V1 · 自用 MVP（4-6 周）

> 目标：让自己每顿能用，验证推荐质量过线。

### 必做

- [x] 从 `chisha-collector` 拉数据 → `data/shenzhen-keji/restaurants.json` + `dishes_raw.json`（D-027，实际 zone 为 home + shenzhen-bay）
- [x] 商品打标脚本（temperature=0，每批 30-50 条）
- [x] **数据校验脚本 `scripts/validate_data.py`**（schema + 引用完整性 + 唯一性 + 打标进度，已用于 2026-05-11 发现 21 家店漏抓菜单）
- [x] **prompt v1 → v2 升级（D-031）**：5 项结构性修订 + spike 50 条 violation 8% 通过
- [x] **v2 全量重打**：shenzhen-bay 11,123 条 + home 2,117 条（2026-05-11，全部 `v2-promptfix`）
- [x] **v3 全量重打 + dual-model golden 171 条**（[D-032](DECISIONS.md#d-032) / [D-036](DECISIONS.md#d-036)，2026-05-12）：13,240 菜 + 4 大字段一致率 99.27%
- [x] **6 模型横评 + 生产默认模型确认**（[D-037](DECISIONS.md#d-037)）：deepseek-v4-flash 字段 acc 88.9%，100万条 $100
- [x] profile.yaml 手填（弱约束三件套 + spicy_tolerance 整数 + taste_description + meal_trigger_time）
- [x] 召回模块（规则 + 弱约束三件套校验 + 多样性过滤）
- [x] **抽查 100 候选合理性**（2026-05-12, scripts/audit_recall.py）：lunch 84% / dinner 64% pass，0 硬约束违规
- [x] 打分函数 V1 + **V2 ~12 维升级**（vegetable_floor / protein_floor / low_oil / popularity / cuisine_pref / variety_bonus + carb_quality / processed_meat / sweet_sauce / wetness / dish_role / 履约 / taste_match / context_boost）
- [x] V1 简化路径：打分 top 3 + LLM 写 reason（D-024 历史完成；D-049 已删代码 — V2 单一路径替代）
- [x] **V2 路径：LLM 精排 top30→5 + Context + session**（[D-033](DECISIONS.md#d-033) / [D-034](DECISIONS.md#d-034) / [D-035](DECISIONS.md#d-035)）
- [x] **LLM 抽象 Phase 1**（[D-038](DECISIONS.md#d-038)）：provider auto-detect + 商家去重兜底
- [x] 5 次空跑测试（mood × meal_type 对照, 真 LLM Sonnet-4.6, 0 同商家重复）
- [x] **推荐调试台**（[D-039](DECISIONS.md#d-039)）：浏览器单页, L1/L2/L3/Final 全可见, combo 追溯, mood 对比
- [x] **召回硬过滤双层架构**（[D-041](DECISIONS.md#d-041)）：ETA/价格/餐厅/主蛋白/烹饪/菜系 6 类硬 ban + 命名规范
- [x] **combo 生成参数化**（[D-040](DECISIONS.md#d-040)）：多蛋白多蔬菜由 profile 注入
- [x] **L2 cap_per_restaurant + 三层 cap（restaurant/cuisine/food_form）**（[D-042](DECISIONS.md#d-042) / [D-043](DECISIONS.md#d-043)）：防潮汕粥/同店扎堆
- [x] **L2 打分体系重设计**（[D-043](DECISIONS.md#d-043)）：删死权重 + 改活 popularity/variety/taste/context + unforgivable penalty
- [x] **反馈闭环 P3 最小实现**（[D-043](DECISIONS.md#d-043)）：`long_term_prefs.py` 反馈历史 → boost/penalty hints（取代旧 V2.0 计划，留 V2.0 待真采集数据补完）
- [x] **Web 用户视图 SPA**（[D-051](DECISIONS.md#d-051) + [D-052~D-055](DECISIONS.md#d-052) + [D-056~D-068](DECISIONS.md#d-056-navbar-加反馈-tab--角标-v11)，2026-05-15）：`apps/web/`（Vite + React 18 + TS + React Router + Tailwind），HomePage/ProfilePage/HistoryPage/FeedbackPage/FeedbackInbox 全量；mock + 真接口双模式（`VITE_USE_MOCK`）。V1.1 反馈系统（progressive form + readonly snapshot + append-only timeline + inbox 三段 + banner stack + snooze/stop）已落地。文案规范 + 视觉系统沉淀到 [`docs/style-guide.md`](style-guide.md)；前后端契约见 [`docs/api.md`](api.md)。
- [ ] **调试台 V1 整合到 apps/web `/debug` 路由**（D-051）：把 `chisha/static/debug.html` 改写成 React 子页面，与用户视图共享组件
- [x] **FastAPI 后端扩展为 Web 服务**（D-051 + D-056~D-068 + [IMPL_LOG D-069](IMPLEMENTATION_LOG.md#d-069-执行记录--fastapi-v1--v11-后端-13-端点联调--codex-review-修复)，2026-05-15）：沿用 8765 端口，推荐链路 6 个（`/api/recommend` `/api/refine` `/api/accept` `/api/skip` `/api/profile` `/api/history`）+ V1.1 反馈链路 7 个（`/api/feedback/inbox` `/api/feedback/snooze` `/api/feedback/stop` `/api/feedback/recent` `/api/feedback/<sid>` `/api/feedback/<sid>/record` `/api/feedback` + `/api/feedback/<sid>/comments`）全部装上；apps/web SPA 托管在 `/`，老调试台 `/debug`，保留 `/api/debug_recommend` `/api/compare_moods`。落盘走单 JSON `logs/feedback/store.json`。Codex review (D-036) 修了 4 MED + 6 LOW (写盘失败暴露 / SPA path traversal 守卫 / corrupt store fail-closed / feedback schema Literal+cross-field validator / debug 边界 / today 4xx / comment ID 碰撞 / naive datetime / limit 边界 / quick default)。
- [ ] **macOS 本机定时拉起服务**（D-051）：launchd / cron 工作日 11:00 / 17:30 自动启动 chisha.web，自用周期内零摩擦
- [ ] ~~接入 OpenClaw + 飞书卡片~~ → 推迟到 V1.5（[D-051](DECISIONS.md#d-051) 翻案 D-022）
- [x] **Step 1（[D-071](DECISIONS.md#d-071-砍-mood-picker--want_soup-关键词识别-v1)）：砍 mood picker + want_soup 关键词识别**（2026-05-15 完成 `e4db6e9`）：前端 `StatusBar` 隐藏 mood chip + `HomePage` `FIXED_MOOD='neutral'`；`chisha/refine.py` 新增 `infer_refine_mood()` (10 正向词 + 6 否定词，否定优先)；埋点 5 字段 + schema_version + jsonl 5MB 轮转；删 score.py 中 want_clean / want_light / want_indulgent / low_carb 4 条 mood 规则 + `infer_default_mood` + `DEFAULT_MOOD_CONFIDENCE`；`tests/test_refine_mood_inference.py` 34 case (含 Codex Round 1 BLOCKER 闭环：契约 contract test 3 + 边界守门 8 + jsonl 写入 2 + deprecated-behavior 4)。
- [ ] **Step 2：工作日 Web 自用一周**（用户行为，不在 Claude Code 范围）。原 D-072 触发条件"采纳率 ≥ 50% + 30 样本"已被 [D-072.1](DECISIONS.md#d-0721-phase-b-不等-step-2-自用数据-用-l2-trace-baseline-替代) 推翻：Phase B 改用 L2 trace 严格回归基线 (`tmp/baseline_traces/` + `scripts/compare_traces.py`) 作为 Step 3 启动门。
- [x] **Step 3（[D-072](DECISIONS.md#d-072-methodology-spec-抽象-放-phase-0-收尾-v1)）：methodology spec 抽象 + score.py 重构**（2026-05-15 完成）：抽 `profiles/methodologies/harvard_plate.yaml` (7 必备字段 + 严格 keyset 校验) + `chisha/methodology.py` 加载/校验/merge 接口；`load_profile` 在所有路径 (api/web_api/debug/dry_run/scripts) 自动 merge spec defaults，profile 显式字段 override (D-072 schema 表 + D-072.1 回归协议)；rerank `_profile_block` 注入"方法论:"行让 L3 显式知道 baseline；新增 `tests/test_methodology.py` 23 case；Codex 三轮 review（BLOCKER 2 / MAJOR 6 / MINOR 5）全闭，`compare_traces.py` 严格回归 0 diff (top60 顺序 + 16 维 breakdown |delta| < 1e-6)。

### 不做（明确推迟）

> 注：以下 ★ 项目原计划 V2.0/V2.1 做，因 [D-033](DECISIONS.md#d-033) "V2.0+V2.1 合并触发"已在 V1 主线内做完代码骨架，但 V1 验收门（采纳率 ≥ 50%）未达成前不算真正"上线"。

- ~~LLM 精排~~ ★（D-024 V1 不做，[D-035](DECISIONS.md#d-035) 已实现）
- ~~探索机制（is_explore 标记）~~ ★（已实现 5 候选 = 3 exploit + 2 explore）
- ~~refine 多轮收敛~~ ★（refine_recommendation API 已实现）
- ~~session 状态管理~~ ★（24h TTL + logs/sessions/，[fix f6e16d0](#) 已修路径）
- 反馈系统 personal_offsets 写入 → V2.0 验收（chips/rating 字段骨架已在 chisha/feedback.py）
- learned_profile 统计聚合 → V2.2（不再做 LLM 蒸馏 insights，[D-026](DECISIONS.md#d-026)）
- LLM 抽象 Phase 2 callable 注入点 → **方案 2026-05-16 已被 D-074 共识改方向**（[D-038](DECISIONS.md#d-038) closure 注入 → `llm_request_spec` machine-readable 数据契约，详见 [design_briefs/2026-05-16-ai-friendly-integration-v2-consensus.md](design_briefs/2026-05-16-ai-friendly-integration-v2-consensus.md)）
- ~~MCP Server 包装 → V2.3~~ → **方向 2026-05-16 已改**：按 CLI + Skill 模式（同款飞书 CLI），**不做 MCP Server**，待 D-074 落
- SKILL.md 完整化 → V2.3（D-022 推迟，integrations/openclaw/SKILL.md 已占位）— D-074 落后按 CLI + Skill 模式重写为 `manifest.json` + `openapi.yaml` + `AGENT_ONBOARDING.md` 三件套
- pip 包发布（按工区拆子包）→ V2.4
- CLI 包装 → V2.4 视情况

### 抽查标准

完成下列验证才算 V1 通过：

| 验证项 | 标准 | 2026-05-12 状态 |
|---|---|---|
| 打标准确率 | 50 条抽查 ≥ 80% | ✅ 171 条 dual-audit golden 89% (D-036 / D-037) |
| 召回合理性 | 100 个候选无明显该排除项；每个候选满足弱约束三件套 | ✅ scripts/audit_recall.py lunch 84% / dinner 64% pass, 0 硬约束违规 |
| 推荐质量 | 5 次空跑 top 3 都满足"控油+有菜+有蛋白"，商家不集中，reason 具体不空话 | ✅ V1+V2 5 次空跑通过, 0 同商家重复 |
| Web 用户视图可用性 | 本机 localhost 起服务后，5 推荐卡片渲染 / accept lock-in / refine 面包屑 / skip 逃生口 / profile YAML 编辑 / 反馈 progressive form + detail + inbox 全可交互（D-051 + D-056~D-068） | ✅ 前端 mock 全跑通，后端 API 接入是下一步 |
| 自用稳定性 | 一周连续可用，**工作日 7 日采纳率 ≥ 50%**（D-028 北极星 V1 目标）| ❌ 待 Web 上线后采集 |
| ~~飞书卡片接入~~ | 推迟到 V1.5（D-051 翻案 D-022） | — |

---

## V1.5 · 数据链路重构（V1 跑完后做，先于 V2.0）

> 目标：把"采集 / 清洗打标 / 对外数据服务"三件事拆成单仓内的独立子模块（[D-030](DECISIONS.md#d-030)）。
> **触发条件**：V1 工作日 7 日采纳率 ≥ 50% 已达成，主线推荐链路稳定。

- [ ] 把 `~/waimai_data` 接管进 `chisha/collector/`（真机采集 / uiautomator2 / 美团）
- [ ] 把现有 `chisha/loader.py` + `scripts/tag_dishes.py` + `scripts/tag_via_subagent.py` 收拢到 `chisha/cleaning/`（raw → §5.2 + 打标）
- [ ] 新建 `chisha/data_service/`：清洗后数据对外的统一入口（list_restaurants / list_dishes / get_restaurant / search_by_tags），后续 V2.3 的 CLI 都从这里包（MCP 方向 2026-05-16 已砍，走 CLI + Skill 模式）
- [ ] 三个子模块之间靠 §5.2 schema 契约解耦，不互相 import 内部细节
- [ ] 推荐层（现有 `chisha/recall.py` / `score.py` / `api.py`）只消费 `chisha.data_service`，不再读 `data/{zone}/*.json` 文件路径
- [ ] schema 修正 D-027：sister project 方向作废，本仓单仓三子模块

成功标准：
- 三子模块各自能单独跑 `uv run pytest tests/{collector,cleaning,data_service}/`
- 推荐层代码里不再出现 `data/{zone}/restaurants.json` 这种硬路径
- collector 漏抓菜单或 schema 改字段时，只影响一个子模块

---

## V2 · 闭环 + 接入完善（V1 跑通后启动）

> 目标：把 V1 的推荐基础上做出反馈闭环，并支持更多 Agent 接入。

### V2.0 · 反馈闭环（V1 自用一周后启动）

- [ ] meal_log.jsonl 完整记录（dish 字段补 cuisine + cooking_method，[D-025](DECISIONS.md#d-025)）
- [ ] personal_offsets.json 写入逻辑（**粒度 = `cuisine::cooking::ingredient`**）
- [ ] 飞书反馈卡片字段：rating_taste + rating_satisfaction + tags + note
- [ ] submit_feedback API
- [ ] accept_recommendation API（自动写 meal_log）
- [ ] log_meal API（自由形式补登）
- [ ] 反馈写入规则（D-010、§4.6 of DESIGN.md）

成功标准：自用两周后，同维度（菜系×烹饪方式×主料）反馈能反映在打分排序上。

### V2.1 · 对话收敛 + 探索 + LLM 精排起步

- [ ] **LLM 精排**（取代 V1 的"打分 top 3"，让 LLM 在 100 候选里挑 5 个）
- [ ] refine_recommendation API
- [ ] LLM 自行判断重精排 vs 重召回
- [ ] 5 个候选 + 1-2 个 explore 标记
- [ ] session 状态管理（24h TTL）
- [ ] update_taste API（自然语言更新偏好）
- [ ] **个性化 refine 快捷标签**（来自 [D-051](DECISIONS.md#d-051) Web 用户视图设计 review）：当前 V1 用 6 个静态标签（想吃辣的 / 换日料 / 来份烧烤 / 想吃牛肉 / 来盖饭 / 换粤菜，见 `docs/design_briefs/v1_user_view.md` §5.4.1）；V2.1 改为根据"最近 3 天没吃过的菜系/食材 + learned_profile bottom_preferences 反向 + 当前 mood"动态生成 4-6 个标签。新增 API: `GET /api/recommend` 响应里加 `suggested_refine_tags: string[]` 字段

成功标准：能用自然语言追加约束，推荐能根据 explore 接受度调整新店发现频率，refine 快捷标签每天都不一样且至少 50% 被点击过。

### V2.2 · learned_profile 统计聚合

- [ ] 加工脚本（每周日凌晨自动跑）
- [ ] 数据加权策略（D-013）
- [ ] **统计聚合到 (cuisine, cooking_method, main_ingredient) 维度**（[D-026](DECISIONS.md#d-026)）
- [ ] top_preferences / bottom_preferences / blacklist 自动维护
- [ ] summary_for_llm 文字总结（限定输入是统计结果，不是原始 meal_log）
- [ ] 精排 prompt 加入 learned_profile.summary_for_llm

成功标准：top/bottom_preferences 中至少有 5 条维度的统计 N ≥ 10，且与用户实际感受一致。

### V2.3 · ~~Claude Code 接入 + MCP 化~~ → CLI + Skill 模式接入

> **2026-05-16 方向已改**：不做 MCP Server 包装，改按 **CLI + Skill 模式**（同款飞书 CLI）。详见 [design_briefs/2026-05-16-ai-friendly-integration-v2-consensus.md](design_briefs/2026-05-16-ai-friendly-integration-v2-consensus.md)。下面旧任务清单待 D-074 落后按新方向重写。

- [ ] ~~写完整 SKILL.md~~ → 改写 `manifest.json` + `openapi.yaml` + `AGENT_ONBOARDING.md` 三件套
- [ ] ~~`chisha/mcp_server.py`~~ → 改做 `chisha init --agent <type>` CLI + `chisha doctor` + `chisha schedule install`
- [ ] ~~INSTALL.md (OpenClaw / HappyClaw / Claude Code 三种)~~ → 改做 Phase 0 单个 reference adapter (Claude Code)，Phase 1 再扩多 Agent
- [ ] LLM 抽象 → 走 `llm_request_spec` 数据契约（chisha 不调 LLM，把 prompt + tool_schema 还给 Agent）
- [ ] 打分权重外部化到 config.yaml（仍保留）

成功标准（新）：本机用 Claude Code reference adapter 端到端跑通"装包 / 提取口味 / 配触发 / 接推送 / 接反馈"五步，自用一周采纳率 ≥ 50%。

### V2.4 · 数据层按工区拆包

- [ ] L1 数据按工区拆 `chisha-data-shenzhen-keji` / `chisha-data-beijing-zgc` 等子包（[D-002](DECISIONS.md#d-002) 修订）
- [ ] 包发布到 PyPI（先内部，再公开）
- [ ] 订阅 `chisha-collector` 的 15 天更新机制（[D-027](DECISIONS.md#d-027)）
- [ ] 多工区数据支持（深圳科技园 / 北京中关村等）

成功标准：第一个同事能 `pip install chisha-data-{他的工区}` 后接入。

---

## V3 · 开源化 + 社区（V2 完成后）

> 目标：开源给社区，吸引早期贡献者。

- [ ] README.md 完善（含 5 分钟上手）
- [ ] examples 仓库
- [ ] 数据脱敏（如果发布我的深圳数据库）
- [ ] 文档站
- [ ] CONTRIBUTING.md
- [ ] 发 GitHub
- [ ] 在 1-2 个 AI/Agent 社区软推广

成功标准：见 PRD §8 Phase 3。

---

## 已砍清单（明确不做）

> 这些功能曾被讨论过或可能被未来的我/Claude Code 提议。**已经决定不做的，不要重新讨论**。
> 如果想推翻，先去 DECISIONS 里加一条新决策说明为什么。

### 产品定位类

| 功能 | 砍掉的原因 | 关联决策 |
|---|---|---|
| SaaS 平台形态 | 运营成本高、隐私顾虑、单用户协同无意义 | D-001 |
| 用户系统 / 登录 / 计费 | 不做 SaaS 自然不用 | D-001 |
| Web URL 渲染层（Skill 内嵌输出格式）| 渲染是 Agent 的事，Skill 不绑死 | D-017（注：跟 D-051 的"独立 Web 客户端"不冲突，两件事） |
| ~~Web/小程序/独立 APP 形态~~ | ~~定位是 Skill 不是产品~~ → **D-051 翻案：V1 主交互改 localhost Web SPA** | **D-051（推翻 PRD §7 此项 + 部分推翻 D-022）** |
| **V1 接 Claude Code 而不接 OpenClaw** | **CLI 不能主动推送，与 PRD 故事 1 承诺不匹配** | **D-022（取代 D-018），D-051 后再次降级到 V1.5** |

### 功能边界类

| 功能 | 砍掉的原因 |
|---|---|
| 卡路里精确追踪 | 太重，违背"轻量决策"定位 |
| 在家做饭推荐 | 数据形态不同，不在外卖场景内 |
| 食材采购建议 | 同上 |
| 体重 / 体脂记录 | 已有专业 APP |
| 训练计划生成 | 是另一个产品 |
| 商家平台直接下单 | 接口封闭，跳转就够 |
| 社交分享 | 偏离工具属性 |

### 推荐逻辑类

| 想法 | 砍掉的原因 | 关联决策 |
|---|---|---|
| 训练日感知（练后加蛋白） | 增益小、复杂度高，V1 暂不做 | D-016 |
| ~~价格硬约束~~ | ~~不在乎预算，方法论是结构正确~~ → **D-041 翻案: 加 hard_max_lunch/dinner combo 总价硬上限** | D-041 |
| 全局协同过滤（"和你类似的人爱吃") | 单用户场景没意义 | D-001 |
| seed_dishes 列表替代 taste_description | 自然语言更高效 | D-014 |
| 严过滤（油脂硬卡）| 结构正确比绝对低脂重要 | D-006 |
| 全量丢 LLM 推荐 | token 爆炸 + 大候选约束满足效果差 | D-005 |
| 每次推荐都让 LLM 实时判断营养画像 | 一致性差、慢、贵 | DESIGN.md 早期讨论 |
| Web URL 渲染做成 secret weapon | 实际是过度设计 | D-017 |
| **严格 1/2-1/4-1/4 餐盘硬约束** | **中式外卖现实下不可达，召回会被卡死** | **D-023** |
| **V1 让 LLM 在 100 候选里挑 3 个** | **LLM 在挑选/排序上引入随机性，打分 top 3 更稳** | **D-024** |
| **personal_offsets 按"店::菜"粒度** | **N 太小、信号弱；改 (cuisine, cooking, ingredient)** | **D-025** |
| **LLM 蒸馏 learned_insights 自然语言洞察** | **N=1 数据下容易过拟合假规律；改统计聚合** | **D-026** |
| **本仓做数据采集** | **采集是 sister project chisha-collector 的事** | **D-027** |
| **北极星 = 决策时间从 15min 降到 1min** | **不可度量、易作弊；改连续采纳率** | **D-028** |

### 反馈交互类

| 想法 | 砍掉的原因 | 关联决策 |
|---|---|---|
| 单一"满意度"星级 | 好吃和满意是两个维度 | D-010 |
| 文本是唯一反馈方式 | 摩擦太大，多数人不填 | D-011 |
| 只用静态有反馈数据 | 样本太稀疏 | D-013 |

---

## 触发重审的条件清单

下列情况发生时，回头看相关决策可能需要调整：

| 触发条件 | 重审什么 |
|---|---|
| 同事开始用且不写 Python | D-003 CLI 形态 |
| LLM API 成本显著上升 | D-007 召回数量 |
| 反馈系统两个星级长期一致 | D-010 拆分必要性 |
| 训练强度大幅增加 | D-016 训练日感知 |
| 真的有非开发者群体强需 | D-001 SaaS 形态 |
| 某个 LLM 上下文能直接处理万条候选 | D-005 三阶段架构 |
| learned_profile 统计聚合质量长期不准 | D-026 加工策略 |
| 用户连续多次拒绝探索候选 | D-015 探索机制 |
| 同名菜 LLM 估算的分量长期偏差 | D-008 价格输入策略 |
| OpenClaw 飞书集成出现重大变更 / 不可用 | D-022 接入对象 |
| 用户连续 2 周采纳率 ≥ 60% 但反馈集中"蔬菜不够" | D-023 弱约束三件套 |
| V1 自用一周后 top 3 重复严重 / 与 taste_description 错位明显 | D-024 V1 不做 LLM 精排 |
| 自用后推荐仍频繁推老灶台 / 乐凯撒 / 徐记舒适圈 | D-044 偏好层提示对 LLM 是否生效, 可能要进 rerank prompt 模板 |
| 单餐 40g 蛋白召回打掉组合 >25% | D-044 min_protein_g 下调（35g 备选） |
| 同维度（cuisine,cooking,ingredient）反馈中"A 店好 B 店差"集中 | D-025 offset 粒度 |
| 6 个月后偏好维度的 N 仍 ≤ 5 | D-025 offset 粒度 |
| chisha-collector 项目停止维护 / schema 大改 | D-027 数据来源（已被 D-030 推翻方向，留作历史） |
| 反馈数据起来后"采纳但餐后差评"频繁 | D-028 北极星指标 |
| V1 7 日采纳率 ≥ 50% 已达成 | D-030 启动 V1.5 数据链路重构 |
| collector schema 变更打挂 shenzhen-bay ≥ 2 次 | D-030 提前启动 V1.5 |
| OpenClaw / Hermes / Claude Code skill 真要接入 chisha 推荐 | D-038 Phase 2 启动（callable LLM 注入点；D-047 已把 provider 抽象做好, 仅剩 closure 注入接口） |
| LLM 精排 sonnet-4.6 与 deepseek-flash 质量持平 | 改 `profile.yaml.llm.provider=openrouter` + `model.openrouter=deepseek/...` 即可降本 (D-047) |
| Web 自用一周采纳率 < 50% 且飞书推送能独立证明补回触达缺口 | D-051 重审，考虑把 D-022 飞书提前到 V1.5 主交互 |
| claude.ai/design 产出与 FastAPI 集成成本 > 3 天 | D-051 重审，考虑改 lark card + 简化 Web 双轨 |

---

## 路线图维护原则

1. **完成的项目立即勾选**，每周 review 进度
2. **新增功能想法**先进 V3 / V4 候选区，不直接进 V2
3. **砍掉的功能加进已砍清单**，附上原因和关联决策
4. **触发重审条件命中时**，先去 DECISIONS 加新条目，再调整路线图
5. **每个版本启动时**新建对应的 DESIGN.md（旧的归档到 docs/archive/）
