# 今天吃点啥 · 路线图

> 这份文档说清楚**什么时候做什么、什么不做**。
> 防止偏航：实现某个功能前先看这里它在哪个版本。
> 已砍清单尤其重要——避免反复讨论同一个被否决的想法。
>
> 项目名：今天吃点啥 · 代码名：`chisha`

---

## 当前状态

**V1 in flight** —— 数据准备 + 推荐三阶段跑通 + 自用一周。

预计 V1 完成时间：本对话讨论后 4-6 周。

**当前状态（2026-05-12）**：

- 打标：v3 全量重打两 zone 13,240 菜（D-032）；dual-model golden set 171 条（D-036, Opus+Codex 共创, 4 大字段一致率 99.27%）；6 模型横评后生产默认 `deepseek-v4-flash`（D-037, field acc 88.9%, 100万条 $100）。
- 推荐 V2 链路端到端跑通：Context 注入 / score V2 ~12 维 / LLM 精排 top30→5（D-035） / refine + session（D-033 V2.1）/ LLM 抽象 Phase 1 provider auto-detect（D-038, 商家去重兜底）。
- 5 次空跑（mood × meal_type 对照）：mood/taste 信号生效，0 同商家重复，reason 直引"命中 want_light"等。
- 100 候选合理性扫描：lunch 84% / dinner 64% pass，0 硬约束违规，flag 全部是软约束油超 3（湘川菜常态 + 末段炸物店）。
- 架构重构推迟到 V1.5（[D-030](DECISIONS.md#d-030)），下一步：飞书 + OpenClaw 接入（用户当前在另一 session 做调试前端页面）。

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
- [x] V1 路径：打分 top 3 + LLM 写 reason（D-024，作为 V2 baseline 保留可用）
- [x] **V2 路径：LLM 精排 top30→5 + Context + session**（[D-033](DECISIONS.md#d-033) / [D-034](DECISIONS.md#d-034) / [D-035](DECISIONS.md#d-035)）
- [x] **LLM 抽象 Phase 1**（[D-038](DECISIONS.md#d-038)）：provider auto-detect + 商家去重兜底
- [x] 5 次空跑测试（mood × meal_type 对照, 真 LLM Sonnet-4.6, 0 同商家重复）
- [ ] **接入 OpenClaw + 飞书卡片**（D-022）：integrations/openclaw/{skill,feishu_card}.py 骨架已搭，cron 调度待装
- [ ] 工作日 11:25 / 18:00 自用一周，纸笔记录每次推荐质量

### 不做（明确推迟）

> 注：以下 ★ 项目原计划 V2.0/V2.1 做，因 [D-033](DECISIONS.md#d-033) "V2.0+V2.1 合并触发"已在 V1 主线内做完代码骨架，但 V1 验收门（采纳率 ≥ 50%）未达成前不算真正"上线"。

- ~~LLM 精排~~ ★（D-024 V1 不做，[D-035](DECISIONS.md#d-035) 已实现）
- ~~探索机制（is_explore 标记）~~ ★（已实现 5 候选 = 3 exploit + 2 explore）
- ~~refine 多轮收敛~~ ★（refine_recommendation API 已实现）
- ~~session 状态管理~~ ★（24h TTL + logs/sessions/，[fix f6e16d0](#) 已修路径）
- 反馈系统 personal_offsets 写入 → V2.0 验收（chips/rating 字段骨架已在 chisha/feedback.py）
- learned_profile 统计聚合 → V2.2（不再做 LLM 蒸馏 insights，[D-026](DECISIONS.md#d-026)）
- LLM 抽象 Phase 2 callable 注入点 → 等 OpenClaw/Hermes 真接入触发（[D-038](DECISIONS.md#d-038)）
- MCP Server 包装 → V2.3
- SKILL.md 完整化 → V2.3（D-022 推迟，integrations/openclaw/SKILL.md 已占位）
- pip 包发布（按工区拆子包）→ V2.4
- CLI 包装 → V2.4 视情况

### 抽查标准

完成下列验证才算 V1 通过：

| 验证项 | 标准 | 2026-05-12 状态 |
|---|---|---|
| 打标准确率 | 50 条抽查 ≥ 80% | ✅ 171 条 dual-audit golden 89% (D-036 / D-037) |
| 召回合理性 | 100 个候选无明显该排除项；每个候选满足弱约束三件套 | ✅ scripts/audit_recall.py lunch 84% / dinner 64% pass, 0 硬约束违规 |
| 推荐质量 | 5 次空跑 top 3 都满足"控油+有菜+有蛋白"，商家不集中，reason 具体不空话 | ✅ V1+V2 5 次空跑通过, 0 同商家重复 |
| 飞书卡片接入 | OpenClaw cron 11:25/18:00 能稳定推送，deeplink 跳转测试 iOS/Android/PC 三端 | ❌ 待装 |
| 自用稳定性 | 一周连续可用，**工作日 7 日采纳率 ≥ 50%**（D-028 北极星 V1 目标） | ❌ 待飞书接入后采集 |

---

## V1.5 · 数据链路重构（V1 跑完后做，先于 V2.0）

> 目标：把"采集 / 清洗打标 / 对外数据服务"三件事拆成单仓内的独立子模块（[D-030](DECISIONS.md#d-030)）。
> **触发条件**：V1 工作日 7 日采纳率 ≥ 50% 已达成，主线推荐链路稳定。

- [ ] 把 `~/waimai_data` 接管进 `chisha/collector/`（真机采集 / uiautomator2 / 美团）
- [ ] 把现有 `chisha/loader.py` + `scripts/tag_dishes.py` + `scripts/tag_via_subagent.py` 收拢到 `chisha/cleaning/`（raw → §5.2 + 打标）
- [ ] 新建 `chisha/data_service/`：清洗后数据对外的统一入口（list_restaurants / list_dishes / get_restaurant / search_by_tags），后续 V2.3 的 CLI / MCP 都从这里包
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

成功标准：能用自然语言追加约束，推荐能根据 explore 接受度调整新店发现频率。

### V2.2 · learned_profile 统计聚合

- [ ] 加工脚本（每周日凌晨自动跑）
- [ ] 数据加权策略（D-013）
- [ ] **统计聚合到 (cuisine, cooking_method, main_ingredient) 维度**（[D-026](DECISIONS.md#d-026)）
- [ ] top_preferences / bottom_preferences / blacklist 自动维护
- [ ] summary_for_llm 文字总结（限定输入是统计结果，不是原始 meal_log）
- [ ] 精排 prompt 加入 learned_profile.summary_for_llm

成功标准：top/bottom_preferences 中至少有 5 条维度的统计 N ≥ 10，且与用户实际感受一致。

### V2.3 · Claude Code 接入 + MCP 化

- [ ] 写完整 SKILL.md（Claude Code 接入入口，用户主动 query 场景）
- [ ] `chisha/mcp_server.py`（开放给其他长程 Agent）
- [ ] INSTALL.md（OpenClaw / HappyClaw / Claude Code 三种接入说明）
- [ ] LLM 抽象（添加 OpenAI / Ollama adapter）
- [ ] 打分权重外部化到 config.yaml

成功标准：Claude Code、OpenClaw、HappyClaw 三种 Agent 至少跑通两种端到端。

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
| Web URL 渲染层 | 渲染是 Agent 的事，Skill 不绑死 | D-017 |
| 独立 APP 形态 | 定位是 Skill 不是产品 | PRD §7 |
| **V1 接 Claude Code 而不接 OpenClaw** | **CLI 不能主动推送，与 PRD 故事 1 承诺不匹配** | **D-022（取代 D-018）** |

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
| 价格硬约束 | 不在乎预算，方法论是结构正确 | DESIGN.md 早期讨论 |
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
| 同维度（cuisine,cooking,ingredient）反馈中"A 店好 B 店差"集中 | D-025 offset 粒度 |
| 6 个月后偏好维度的 N 仍 ≤ 5 | D-025 offset 粒度 |
| chisha-collector 项目停止维护 / schema 大改 | D-027 数据来源（已被 D-030 推翻方向，留作历史） |
| 反馈数据起来后"采纳但餐后差评"频繁 | D-028 北极星指标 |
| V1 7 日采纳率 ≥ 50% 已达成 | D-030 启动 V1.5 数据链路重构 |
| collector schema 变更打挂 shenzhen-bay ≥ 2 次 | D-030 提前启动 V1.5 |
| OpenClaw / Hermes / Claude Code skill 真要接入 chisha 推荐 | D-038 Phase 2 启动（callable LLM 注入点） |
| LLM 精排 sonnet-4.6 与 deepseek-flash 质量持平 | D-038 评估精排降本 |

---

## 路线图维护原则

1. **完成的项目立即勾选**，每周 review 进度
2. **新增功能想法**先进 V3 / V4 候选区，不直接进 V2
3. **砍掉的功能加进已砍清单**，附上原因和关联决策
4. **触发重审条件命中时**，先去 DECISIONS 加新条目，再调整路线图
5. **每个版本启动时**新建对应的 DESIGN.md（旧的归档到 docs/archive/）
