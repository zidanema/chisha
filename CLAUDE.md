# chisha · 项目级指令

> 项目名:今天吃点啥 (chisha) · 个人 AI **原则派点餐执行外包**工具 (L0 方法论 spec / L1 数据 / L2 打分 / L3 LLM 精排)
> 当前阶段:**Phase 0 工程侧收尾** — 推荐链路 + Web SPA + V1.1 反馈 + FastAPI 20 端点 + 砍 mood picker + methodology spec 抽象 + **D-070 L1 真兑现 (LLM 抽取)** + **D-074 sandbox time-travel 模式** 全部 ready (D-001~D-074, 2026-05-16)。Step 2 用户自用验证现在可走 sandbox 一次会话内压缩验证, 不必等真实日历日。
> 主语言:Python (后端) + TypeScript (前端) · 包管理:uv / npm · 测试:pytest

## 必读(首次接触本项目)

按顺序读:
1. [README.md](README.md) — 项目状态与文档体系总表
2. [docs/PRD.md](docs/PRD.md) — 产品定位
3. [docs/ROADMAP.md](docs/ROADMAP.md) — V1/V2/V3 边界、已砍清单
4. [DESIGN.md](DESIGN.md) — 当前架构与实现
5. [docs/CONTRIBUTING_DOCS.md](docs/CONTRIBUTING_DOCS.md) — 文档纪律(改任何文档前必读)

改推荐链路前额外读 [docs/RECOMMEND_PRINCIPLES.md](docs/RECOMMEND_PRINCIPLES.md);改 L3 精排前必读 [docs/L3_RERANK_REDESIGN.md](docs/L3_RERANK_REDESIGN.md)。
改 `apps/web/` 用户视图前必读 [docs/style-guide.md](docs/style-guide.md) (D-052~D-055 + D-060/D-066/D-067 锁定的交互不可重设计);改 `/api/*` 前必读 [docs/api.md](docs/api.md);改反馈链路前必读 DECISIONS D-056~D-068 信号框架与生命周期约束。

## 文档纪律(强制)

每次决策落地或代码大改后,过 3 项 checklist:

1. **新条目写哪边?**
   - 产品/架构/方法论/schema 决策 → [docs/DECISIONS.md](docs/DECISIONS.md)
   - 工程实施细节 (prompt 改 N 行 / 参数 / batch / bug 排查) → [docs/IMPLEMENTATION_LOG.md](docs/IMPLEMENTATION_LOG.md)
   - 判别准则: **半年后做下一次大重构会不会回头查这条?** 会查 → DECISIONS;不会 → IMPL_LOG
2. **是否推翻了旧决策?** 推翻就在旧条目标 `superseded by D-NNN`,不删
3. **是否需要联动更新?** ROADMAP 当前状态 / README 进度章节 / DESIGN §7 速查表

详细判别表与反 anti-patterns 见 [docs/CONTRIBUTING_DOCS.md](docs/CONTRIBUTING_DOCS.md)。

## 决策编号约定

- D-XXX 编号**全项目共享**,跨 DECISIONS / IMPLEMENTATION_LOG 唯一
- 推翻型条目用 D-NNN.M 形式(如 D-046.1 是 D-046 后的修订)
- 新条目追加到文件尾部,禁止插队改编号

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

## 推荐链路改动红线 (D-070~D-074 沉淀)

- **不要让用户主动选 mood**: D-071 砍掉 mood picker. 新心情维度走 refine 文本或 L3 prompt, 绝不在前端加 chip
- **`infer_refine_mood` 只服务 want_soup**: 不许扩为通用 mood parser (D-071 边界, 单测有守门 8 case)
- **methodology spec 抽象只搬运不改逻辑**: 改打分逻辑 / 调权重 / 加新维度都不走 spec, 走 score.py + DECISIONS 修订. spec 是 yaml 化的 V2_DEFAULT_WEIGHTS, 不是新接口
- **改 score.py / methodology / spec 前后必跑 baseline_l2_snapshot + compare_traces**: top60 顺序 + 16 维 breakdown |delta| < 1e-6 才允许 commit (D-072.1)
- **L1 词表锁定**: `score.taste_match_bonus` 现支持 6 token (low_oil/wetness/sweet_sauce/processed_meat/carb_heavy/spicy), 扩词表 = 改打分逻辑, 违反 D-072 边界, Phase 1 独立决策 (D-073)
- **L1 抽取走 claude_code_cli text 路径**: 不传 tools (CLI 不支持 tool_use). prompt 在 `prompts/l1_extract.md`, 改 prompt 走 D-036 dual-model audit (D-073)
- **sandbox 是 user web 一个 mode**: 不允许做 CLI 替代或 fixture batch (D-074 原则 #1). 行为完全一致 prod (#2), 仅时钟 + 数据落盘根隔离 (#3)
- **改时间相关逻辑前先看 11 处时间注入**: web_api/api/refine/feedback_store/session/long_term_prefs 已替换走 `chisha.clock.*`. 不注入: time.time latency / corrupt backup ts / comment id 毫秒 (D-074 PR-1a)
- **Phase 1 (同事推广) 才考虑**: data zone 拆包 / OpenClaw 接入 / screener 设计 / 第二份 methodology spec — Phase 0 内不做

## 提醒(给未来的 Claude Code)

- DECISIONS.md 已经发生过定位漂移 (62.5% 条目漂成工程日志);P0 拆分后**严格守边界**,新条目写之前先过判别准则
- 改完任意 D-XXX 后,**主动检查** README / ROADMAP 是否要同步更新,不要等用户发现漂移
- 阶段性收口时主动调用 `neat-freak` skill,不要等漂移堆积
