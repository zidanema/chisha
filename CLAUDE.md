# chisha · 项目级指令

> 项目名:今天吃点啥 (chisha) · 个人 AI **原则派点餐执行外包**工具 (L0 方法论 spec / L1 数据 / L2 打分 / L3 LLM 精排)
> 当前阶段:**Phase 0 工程侧收尾** — 推荐链路 + Web SPA + V1.1 反馈 + FastAPI 13 端点 + 砍 mood picker + methodology spec 抽象全部 ready (D-001~D-072, 2026-05-15)。剩 Step 2 用户自用一周采纳率验证, 不在代码范围。
> 主语言:Python (后端) + TypeScript (前端) · 包管理:uv / npm · 测试:pytest

## 必读(首次接触本项目)

按顺序读:
1. [README.md](README.md) — 项目状态与文档体系总表
2. [docs/PRD.md](docs/PRD.md) — 产品定位
3. [docs/ROADMAP.md](docs/ROADMAP.md) — V1/V2/V3 边界、已砍清单
4. [docs/CONTRIBUTING_DOCS.md](docs/CONTRIBUTING_DOCS.md) — 文档纪律(改任何文档前必读)
5. `docs/decisions.md`(提炼中)+ `docs/CONTRACTS.md`(待建) — 替代已归档的 DESIGN / DECISIONS / IMPL_LOG

改 `apps/web/` 用户视图前必读 [docs/style-guide.md](docs/style-guide.md);改 `/api/*` 前必读 [docs/api.md](docs/api.md)。
改推荐链路 / L3 精排:历史背景在 [docs/archive/DECISIONS_phase0.md](docs/archive/DECISIONS_phase0.md),活约束在 `docs/CONTRACTS.md`(Wave 3 落)。

## 文档纪律(强制 · 2026-05-16 重构后)

文档按"读者"分四桶:

| 桶 | 文件 | 写什么 | 写多长 |
|---|---|---|---|
| 产品决策(给用户) | `docs/decisions.md` | 产品方向 / 推翻历史 / 没选 B 方案的原因 | **3-5 行**,> 15 行说明你在写实施,停下 |
| Agent 契约(给 Claude/Codex) | `docs/CONTRACTS.md` | 跨文件隐含约束 / 反直觉规则 / 系统级 invariant | 单条 ≤ 10 行,全文 ≤ 200 行 |
| Agent 红线(给 Claude/Codex) | `CLAUDE.md`(本文件) | 命令 / avoid 清单 / 当前阶段焦点 | 全文 ≤ 100 行 |
| 历史归档(不维护) | `docs/archive/*_phase0.md` | Phase 0 历史 | 只读 |

**不写**(无论多重要,代码已有): 字段表 / schema keyset / prompt 行号 / 参数值 / 测试列表 / batch 数 / commit hash / 文件改动清单 — git log + grep 代码即权威。

详见 [docs/CONTRIBUTING_DOCS.md](docs/CONTRIBUTING_DOCS.md)(Wave 4 重写)。

## 决策编号约定

- D-XXX 编号**全项目共享**,新条目追加到 `docs/decisions.md` 尾部
- 推翻型条目用 D-NNN.M(如 D-046.1)
- superseded 就地标 `[已废弃 by D-NNN]`,不删不挪

## 常用命令

```bash
# 调试台 (D-039)
uv run python -m chisha.debug_server  # http://127.0.0.1:8765

# 推荐 dry_run
uv run python -m scripts.dry_run --n 5 --meal both

# 召回审计
uv run python -m scripts.inspect_candidates --meal lunch --limit 100

# 打标 (V3 走 OpenRouter,默认 deepseek-v4-flash, D-037)
uv run python scripts/tag_via_api.py shenzhen-bay --limit 50

# 测试
uv run pytest tests/ -q

# L2 trace 严格回归 (D-072.1, 改打分链路必跑)
uv run python -m scripts.baseline_l2_snapshot --out-dir tmp/baseline_traces       # 改前存
uv run python -m scripts.baseline_l2_snapshot --out-dir tmp/baseline_traces_after # 改后存
uv run python -m scripts.compare_traces                                            # 严格对比 (EPSILON=1e-6)
```

## 推荐链路改动红线 (D-070/D-071/D-072 沉淀)

- **不要让用户主动选 mood**: D-071 砍掉 mood picker. 新心情维度走 refine 文本或 L3 prompt, 绝不在前端加 chip
- **`infer_refine_mood` 只服务 want_soup**: 不许扩为通用 mood parser (D-071 边界, 单测有守门 8 case)
- **methodology spec 抽象只搬运不改逻辑**: 改打分逻辑 / 调权重 / 加新维度都不走 spec, 走 score.py + DECISIONS 修订. spec 是 yaml 化的 V2_DEFAULT_WEIGHTS, 不是新接口
- **改 score.py / methodology / spec 前后必跑 baseline_l2_snapshot + compare_traces**: top60 顺序 + 16 维 breakdown |delta| < 1e-6 才允许 commit (D-072.1)
- **Phase 1 (同事推广) 才考虑**: data zone 拆包 / OpenClaw 接入 / screener 设计 / 第二份 methodology spec — Phase 0 内不做

## 提醒(给未来的 Claude Code)

- **文档体系 2026-05-16 重构过**:DECISIONS/IMPL_LOG/DESIGN 已归档,新决策只写 `docs/decisions.md`,且 ≤ 15 行/条。超过就是你在写实施,删掉重写
- 改完任意 D-XXX 后,**主动检查** README / ROADMAP 是否要同步更新
- 阶段性收口时主动调用 `neat-freak` skill,但要带一句"≤ 15 行原则,讲不完就丢弃"防它过度沉淀
