# chisha · 项目级指令

> 项目名:今天吃点啥 (chisha) · 个人 AI 餐饮推荐系统 (L1 数据 / L2 打分 / L3 LLM 精排)
> 当前阶段:V1 in flight — 推荐链路 (V2 + 4 层 cap + L3 tool_use D-047 + 双路径收口 D-048) 已就绪; **Web SPA D-051~D-055 + V1.1 反馈系统 D-056~D-068 已落地 (2026-05-15, `apps/web/`)**; FastAPI V1 端点接入 + 自用一周采集采纳率是下一步。
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
```

## 提醒(给未来的 Claude Code)

- DECISIONS.md 已经发生过定位漂移 (62.5% 条目漂成工程日志);P0 拆分后**严格守边界**,新条目写之前先过判别准则
- 改完任意 D-XXX 后,**主动检查** README / ROADMAP 是否要同步更新,不要等用户发现漂移
- 阶段性收口时主动调用 `neat-freak` skill,不要等漂移堆积
