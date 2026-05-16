# chisha · 项目级指令

> 项目名:今天吃点啥 (chisha) · 个人 AI **原则派点餐执行外包**工具 (L0 方法论 spec / L1 数据 / L2 打分 / L3 LLM 精排)
> 当前阶段:**Phase 0 工程侧收尾** — 推荐链路 + Web SPA + V1.1 反馈 + FastAPI 23 端点 + 砍 mood picker + methodology spec 抽象 + **D-076 / D-076.1 L1 真兑现 (LLM 抽取)** + **D-077 sandbox time-travel** + **D-078/D-078.1/2/3 真实演练 + Codex S2 闭环修补** + **D-079 推荐链路 trace 持久化 + Debug 三模式 (Replay / What-if / Live, PR-1/2/3/4 全落)** 全部 ready (D-001~D-079, 2026-05-17)。L1 (LLM 抽取) → L2 (taste_match_bonus) → L3 (prompt 注入"行为信号") 三层贯通, 真实 LLM 两轮演练验证 (low_oil + spicy boost). Step 2 用户自用走 sandbox 一次会话压缩验证, 不必等真实日历日; 差评 trace 事后回溯 + What-if overlay 试 weights 全跑通。
> 主语言:Python (后端) + TypeScript (前端) · 包管理:uv / npm · 测试:pytest

## 必读(首次接触本项目)

按顺序读:
1. [README.md](README.md) — 项目状态与文档体系总表
2. [docs/PRD.md](docs/PRD.md) — 产品定位
3. [docs/ROADMAP.md](docs/ROADMAP.md) — V1/V2/V3 边界、已砍清单
4. [docs/CONTRIBUTING_DOCS.md](docs/CONTRIBUTING_DOCS.md) — 文档纪律(改任何文档前必读)
5. `docs/decisions.md`(提炼中)+ `docs/CONTRACTS.md`(待建) — 替代已归档的 DESIGN / DECISIONS / IMPL_LOG

改 `apps/web/` 用户视图前必读 [docs/style-guide.md](docs/style-guide.md)(D-052~D-055 + D-060/D-066/D-067 锁定的交互不可重设计);改 `apps/debug-ui/` debug 台 SPA 前必读 [apps/debug-ui/README.md](apps/debug-ui/README.md)(D-075 独立 Vite SPA / V12 DAG / 5 主题,不并入 apps/web);改 `/api/*` 前必读 [docs/api.md](docs/api.md)。
改推荐链路 / L3 精排:历史背景在 [docs/archive/DECISIONS_phase0.md](docs/archive/DECISIONS_phase0.md) + [docs/archive/RECOMMEND_PRINCIPLES_phase0.md](docs/archive/RECOMMEND_PRINCIPLES_phase0.md) + [docs/archive/L3_RERANK_REDESIGN_phase0.md](docs/archive/L3_RERANK_REDESIGN_phase0.md),活约束在 `docs/CONTRACTS.md`。

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

## 推荐链路改动红线 (D-070~D-079 沉淀)

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
- **trace 落盘走 trace_store, 失败不阻断 (D-079)**: `chisha/api.py:recommend_meal` 写 trace 走 `trace_store.write_trace`, 失败仅 `logger.warning`, recommend response 不阻断. `read_trace` 走 fail-closed: 损坏抛 `TraceCorrupt` + 备份 `.corrupt.{ts}.bak` (与 feedback_store D-066/067 一致). 改 trace schema 必 bump `TRACE_SCHEMA_VERSION`
- **What-if 零 runtime read (D-079)**: `chisha/debug_what_if.py:what_if_rerun` 必须 100% 用 `__frozen.{ctx, today, l1_combos, l1_prefs_snapshot, l2_meal_log_view, profile_snapshot}`, **严禁** `clock.today()` / `dt.date.today()` / `load_prefs(root)` / 任何 runtime state read. 加新冻结字段 → 同步 `_build_trace` 写入 + 测试守门
- **Live 模式永不写盘 (D-079)**: `/api/debug_recommend` (老 D-039 端点) + `chisha/api.py:recommend_meal(persist_trace=False)` 是 Live 入口, 永不调 `trace_store.write_trace`. 改 Live 链路必须保留这条约束, 不许"为了好调试"加 trace 写盘 — 会污染 Replay 列表
- **改 debug-ui 前端时 (D-079)**: 后端是单一可信源, localStorage 只作离线 fallback, 永不参与后端列表合并 (DESIGN §8.2). 不动 L1/L2/L3/Final/Refine/Trace 6 个 panel 组件 — what-if 是 overlay, 不重设计原 panel. URL state 用 `replaceState` 不 push
- **改 refine 端点写 trace 时 (D-079 PR-4)**: 必须先 `read_trace(sid)` merge 进同一文件 (Sidebar 一条 session 一行不分裂). missing → warn + 不持久化; corrupt → error + 不持久化. **绝不**创 refine-only 孤儿 trace (Replay 列表读不到也不需要专门处理)
- **Phase 1 (同事推广) 才考虑**: data zone 拆包 / OpenClaw 接入 / screener 设计 / 第二份 methodology spec / L1 词表进一步扩 (cuisine 偏好 token 等) — Phase 0 内不做

## 前端自测(强制,改 apps/web 或 apps/debug-ui 必走)

本项目装了 `chrome-devtools-mcp` (user scope, 2026-05-16). 改 `apps/web/src/**` (用户视图 :5173) 或 `apps/debug-ui/src/**` (D-075 SPA :5174) 任意 `.tsx` / `.css` / `vite.config.ts` / proxy 后, **必须用 `mcp__chrome-devtools__*` 工具自驱浏览器验证**,不许只跑 vitest/tsc 就宣告完成,也不许让志丹去当眼睛。

最小流程:

1. 确认两个 server 在跑:后端 `uv run python -m chisha.debug_server` (:8765) + Vite (`apps/web` :5173 或 `apps/debug-ui` :5174)
2. `mcp__chrome-devtools__navigate` 打到改动涉及的路由
3. 走一遍 golden path + 至少一个 edge case
4. 看 `console_messages` 有没有 error/warn,看 `network_requests` 有没有 4xx/5xx
5. 必要时截图反馈;**跑不通就直说"Vite 没起来 / 后端 502 / 没验"**,不要假装通过

不适用:纯后端 (`chisha/**` Python) / 脚本 (`scripts/**`) / 测试 (`tests/**`) 改动 — pytest + baseline_l2_snapshot 已经够。

## 提醒(给未来的 Claude Code)

- **文档体系 2026-05-16 重构过**:DECISIONS/IMPL_LOG/DESIGN 已归档,新决策只写 `docs/decisions.md`,且 ≤ 15 行/条。超过就是你在写实施,删掉重写
- 改完任意 D-XXX 后,**主动检查** README / ROADMAP 是否要同步更新
- 阶段性收口时主动调用 `neat-freak` skill,但要带一句"≤ 15 行原则,讲不完就丢弃"防它过度沉淀
