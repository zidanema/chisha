# Phase 0 ROADMAP 历史归档

> 2026-05-20 V1.0 工程里程碑收尾时归档.
> 这份文件是 Phase 0 (D-001~D-093) 已完成清单 + 当时收尾路线的快照.
> **不再维护**. 活路线见 [../ROADMAP.md](../ROADMAP.md).

---

## Phase 0 收尾路线 (2026-05-17 拍板, 已完成)

终极路径: **自用稳定 → 接个人 agent (含 context 注入) → 扩同事 / 数据源**.

5 步收尾顺序:

1. **Debug trace 串接验收** — 归因基础设施先跑可信 ✅
2. **摸清 L1 抽取 prompt + 链路** — 不学整套系统, 只看清 L1 这层 ✅
3. **沙盒 e2e 跑通 + D-080~D-085 Refine v2 framework 复测** — 沙盒主战场 ✅ (D-093 sandbox-lab 落地)
4. **接个人 agent + context 注入** — 放大 chisha 价值的拐点 (推迟到 Phase 1)
5. **同 query 引入可控随机性** — 接 agent 后频次拉高才有体感场景 (推迟到 Phase 1)

### 划掉的犹豫点

- **macOS launchd 定时拉起**: 自用手动开页面没毛病, 不是债
- **Step 2 真实自用一周作为强门槛**: 改成沙盒 + 真实并行
- **系统性深入学链路**: 不专门学, 边跑边问 claude code

---

## V1 必做清单 (全完成)

- [x] 数据采集 + 打标 v3 (171 条 dual-audit golden 89%, D-031/032/036/037)
- [x] profile.yaml 弱约束三件套 + spicy_tolerance + taste_description + meal_trigger_time
- [x] 召回模块 (规则 + 弱约束三件套校验 + 多样性过滤)
- [x] 抽查 100 候选合理性 (lunch 84% / dinner 64% pass, 0 硬约束违规)
- [x] 打分函数 V1 + V2 多维升级 (D-043)
- [x] V2 路径: LLM 精排 top60→5 + Context + session (D-033/034/035)
- [x] LLM 抽象 Phase 1 (provider auto-detect, D-038)
- [x] 推荐调试台 (D-039), 后续演进到 D-075 SPA / D-087 Workflow A
- [x] 召回硬过滤双层架构 (D-041)
- [x] L2 cap + 三层 cap 防扎堆 (D-042/D-043)
- [x] L2 打分体系重设计 (删死权重 + 改活 popularity/variety/taste/context + unforgivable penalty, D-043)
- [x] 反馈闭环 P3 最小实现 (long_term_prefs.py 反馈历史 → boost/penalty hints)
- [x] Web 用户视图 SPA (D-051 + D-052~D-068)
- [x] 调试台改独立 apps/debug-ui SPA (D-075)
- [x] FastAPI 后端扩展为 Web 服务 (D-051 + D-056~D-068)
- [x] Step 1: 砍 mood picker + want_soup 关键词识别 (D-071)
- [x] Step 3: methodology spec 抽象 + score.py 重构 (D-072) + L2 trace baseline 严格回归 (D-072.1)
- [x] Refine v2 / Faithful Refine framework 重构 (D-080~D-085)
- [x] L2 refine 信号校准 + 死维度清理 (D-090/D-091/D-092)
- [x] Sandbox Lab 白盒时光机落地 (D-093)

### 不做 (明确推迟)

- 反馈系统 personal_offsets 写入 → V2.0 验收 (chips/rating 字段骨架已在 chisha/feedback.py)
- learned_profile 统计聚合 → V2.2 (不再做 LLM 蒸馏 insights, D-026)
- LLM 抽象 Phase 2 callable 注入点 → D-074 翻案后走 `llm_request_spec` 数据契约
- MCP Server 包装 → 改 CLI + Skill 模式, 待 D-074 落
- SKILL.md 完整化 → V2.3
- pip 包发布 (按工区拆子包) → V2.4

### V1 抽查标准 (全过)

| 验证项 | 标准 | 状态 |
|---|---|---|
| 打标准确率 | 50 条抽查 ≥ 80% | ✅ 171 条 dual-audit golden 89% |
| 召回合理性 | 100 个候选无明显该排除项 | ✅ lunch 84% / dinner 64% pass, 0 硬约束违规 |
| 推荐质量 | 5 次空跑 top 3 都满足"控油+有菜+有蛋白", 商家不集中, reason 具体不空话 | ✅ V1+V2 5 次空跑通过, 0 同商家重复 |
| Web 用户视图可用性 | 5 推荐卡片 / accept lock-in / refine 面包屑 / skip 逃生口 / profile YAML 编辑 / 反馈全可交互 | ✅ |
| 自用稳定性 | 沙盒 D-080/D-081 复测 OK + 真实日历日不抗拒 + 接个人 agent 跑通 | 🔄 推到 Phase 1 |

---

## 旧 V1/V2/V3 段 (供考古, 不再驱动节奏)

旧 V1/V2/V3 笛卡尔积已被 D-070 的 Phase 路线取代. Phase 0 ≈ V1 后半 + 砍 mood + spec 化; Phase 1 ≈ V2 反馈闭环成熟期 + 同事接入; Phase 2 ≈ V2.4+/V3 多区域 + 多方法论.
