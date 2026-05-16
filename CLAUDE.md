# chisha · 项目级指令

> 项目名:今天吃点啥 (chisha) · 个人 AI **原则派点餐执行外包**工具 (L0 方法论 spec / L1 数据 / L2 打分 / L3 LLM 精排)
> 当前阶段:**Phase 0 工程侧收尾** — 推荐链路 + Web SPA + V1.1 反馈 + FastAPI 20 端点 + 砍 mood picker + methodology spec 抽象 + **D-076 L1 真兑现 (LLM 抽取)** + **D-077 sandbox time-travel** + **D-078/D-078.1/2/3 + D-076.1 真实演练 + Codex S2 闭环修补** 全部 ready (D-001~D-078.3 + D-076.1, 2026-05-16)。L1 (LLM 抽取) → L2 (taste_match_bonus) → L3 (prompt 注入"行为信号") 三层贯通, 真实 LLM 两轮演练验证 (low_oil + spicy boost). Step 2 用户自用走 sandbox 一次会话压缩验证, 不必等真实日历日。
> 主语言:Python (后端) + TypeScript (前端) · 包管理:uv / npm · 测试:pytest

## 必读(首次接触本项目)

按顺序读:
1. [README.md](README.md) — 项目状态与文档体系总表
2. [docs/PRD.md](docs/PRD.md) — 产品定位
3. [docs/ROADMAP.md](docs/ROADMAP.md) — V1/V2/V3 边界、已砍清单
4. [DESIGN.md](DESIGN.md) — 当前架构与实现
5. [docs/CONTRIBUTING_DOCS.md](docs/CONTRIBUTING_DOCS.md) — 文档纪律(改任何文档前必读)

改推荐链路前额外读 [docs/RECOMMEND_PRINCIPLES.md](docs/RECOMMEND_PRINCIPLES.md);改 L3 精排前必读 [docs/L3_RERANK_REDESIGN.md](docs/L3_RERANK_REDESIGN.md)。
改 `apps/web/` 用户视图前必读 [docs/style-guide.md](docs/style-guide.md) (D-052~D-055 + D-060/D-066/D-067 锁定的交互不可重设计);改 `apps/debug-ui/` debug 台 SPA 前必读 [apps/debug-ui/README.md](apps/debug-ui/README.md) (D-075, 独立 Vite SPA / V12 DAG / 5 主题, 不并入 apps/web);改 `/api/*` 前必读 [docs/api.md](docs/api.md);改反馈链路前必读 DECISIONS D-056~D-068 信号框架与生命周期约束。

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
# 老调试台 (D-039 vanilla HTML) + 新 debug-ui (D-075 Vite SPA) 共用同一后端
uv run python -m chisha.debug_server  # :8765 (老:/debug, SPA:/, swagger:/swagger)

# 新 debug 台 SPA (D-075, 端口 5174, proxy /api → :8765)
cd apps/debug-ui && npm install && npm run dev  # http://127.0.0.1:5174

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

## 推荐链路改动红线 (D-070~D-078.3 + D-076.1 沉淀)

- **不要让用户主动选 mood**: D-071 砍掉 mood picker. 新心情维度走 refine 文本或 L3 prompt, 绝不在前端加 chip
- **`infer_refine_mood` 只服务 want_soup**: 不许扩为通用 mood parser (D-071 边界, 单测有守门 8 case)
- **methodology spec 抽象只搬运不改逻辑**: 改打分逻辑 / 调权重 / 加新维度都不走 spec, 走 score.py + DECISIONS 修订. spec 是 yaml 化的 V2_DEFAULT_WEIGHTS, 不是新接口
- **改 score.py / methodology / spec 前后必跑 baseline_l2_snapshot + compare_traces**: top60 顺序 + 16 维 breakdown |delta| < 1e-6 才允许 commit (D-072.1)
- **L1 词表 (D-076.1 后)**: `score.taste_match_bonus` 现支持 BOOST 4 token (low_oil/wetness/**spicy**/**sweet_sauce**) + PENALTY 4 token (sweet_sauce/processed_meat/carb_heavy/spicy). spicy/sweet_sauce 双向 (boost + penalty 都有). 不加 processed_meat/carb_heavy boost (违反 harvard_plate baseline). 进一步扩词表仍需独立决策 + baseline_l2 守门 (D-076.1 边界)
- **L1 抽取走 claude_code_cli text 路径**: 不传 tools (CLI 不支持 tool_use). prompt 在 `prompts/l1_extract.md`, 改 prompt 走 D-036 dual-model audit (D-076)
- **sandbox 是 user web 一个 mode**: 不允许做 CLI 替代或 fixture batch (D-077 原则 #1). 行为完全一致 prod (#2), 仅时钟 + 数据落盘根隔离 (#3)
- **改时间相关逻辑前先看 12 处时间注入**: web_api/api/refine/feedback_store/session/long_term_prefs/**l1_extractor** 已替换走 `chisha.clock.*`. 不注入: time.time latency / corrupt backup ts / comment id 毫秒 (D-077 PR-1a + D-078 l1_extractor 修补)
- **改 sandbox 生命周期相关时**: reset/disable 必须先抢 `_L1_EXTRACTION_LOCK` (web_api `_block_until_l1_idle_or_409`), 否则 worker 中途 save_prefs 会污染 prod long_term_prefs.json. advance 在 status=pending 时直接返 409 防 UI bypass (D-078 Codex S2 Q3-High/Q2)
- **改 /api/accept 时**: meal_log.jsonl 是 diversity cooldown source-of-truth. record_accept 和 append_meal_log_entry 必须同等 hard-fail. 砍掉 meal_log 写入 = 一周内重餐厅 (D-078 P1)
- **L1 抽取必须接虚拟时钟**: l1_extractor.aggregate_inputs/extract_and_save 必须透传 root, 默认 today=clock.today(root). 守门测试 test_aggregate_default_today_uses_chisha_clock + test_default_llm_call_uses_existing_llm_client_symbol 不许删 (D-078 P0)
- **L1 → L3 prompt 桥 root 必须透传** (D-078.2 + Codex S2 修补): rerank() 主入口 + refine.py 调 rerank 都必须显式 `root=root`. _profile_block(profile, root=None) 默认 root=None 时 load_prefs 走 _project_root 兜底 — 测试用 monkeypatched ROOT / 多 worktree 场景下会跨 root 串数据. 守门: test_refine_passes_root_to_rerank
- **改 sandbox inspect 时**: 必须同时返回 long_term_prefs (走 load_prefs 三态) + long_term_prefs_raw (直读磁盘 raw json). load_prefs 在 boost+penalty 都空时返 None 是 L2 等价语义, 但 inspect 必须显示 regularities_freetext / signals_not_scored / evidence (D-078.3)
- **Phase 1 (同事推广) 才考虑**: data zone 拆包 / OpenClaw 接入 / screener 设计 / 第二份 methodology spec / L1 词表进一步扩 (cuisine 偏好 token 等) — Phase 0 内不做

## 提醒(给未来的 Claude Code)

- DECISIONS.md 已经发生过定位漂移 (62.5% 条目漂成工程日志);P0 拆分后**严格守边界**,新条目写之前先过判别准则
- 改完任意 D-XXX 后,**主动检查** README / ROADMAP 是否要同步更新,不要等用户发现漂移
- 阶段性收口时主动调用 `neat-freak` skill,不要等漂移堆积
