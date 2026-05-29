# D-104(方案)agent-only core 解耦重构

> 状态: **方案已与 Codex 对齐, 待志丹拍板执行**. 2026-05-29 · Opus 设计 + Codex rescue review 收敛.
> 关联: D-103(分发形态 B: 引擎进 skill / `uv run` 就地跑 / 18MB 数据进 skill / 状态 `~/.chisha`)→ 本案做包的 core/extras 解耦, 让 skill 分发的 agent 接入零冗余.

## 1. 目标

1. `chisha/` 拆成 **agent-only core + extras** 两层(**单包逻辑分层**, 非物理拆两个 PyPI 包).
2. **core 在静态依赖图上自然到不了 sandbox/web/debug/自调LLM** → 治本(非 build 时排除的治标), import 边界 smoke test 自动守住.
3. agent 功能零损失(含 `--at-time`).
4. **行为 0-diff**(baseline_l2_snapshot, EPSILON=1e-6)+ trace 落盘路径/业务时间不变.
5. extras 降级为 `[dev]`/`[web]` optional-dependencies(apps/debug-ui + apps/sandbox-lab 仍依赖).

## 2. 已确认依赖事实(代码证据)

| 事实 | 证据 |
|---|---|
| 地基反向依赖 debug feature | `clock.py:27` + `data_root.py:38` 顶层 `from chisha import sandbox` |
| agent 与 sandbox 互斥 | `agent_cli.py:112` sandbox 启用拒绝运行; `--at-time` 走 `_parse_at_time()` 注入 today, 不碰 sandbox(:25,:119,:313) |
| ∴ sandbox 在 agent core 是死代码 | clock 的 `sandbox.current_date()` 恒 None; data_root `is_enabled()` 恒 False |
| agent 不走 recommend_meal | 走 `agent_orchestration.prepare_candidates`(确定性到 top_k); recommend_meal 含 LLM 全流程 |
| agent 仅借 api 4 工具函数 | `agent_cli` 借 `_resolve_zone/_gen_session_id/_format_v2_candidate/_build_trace` |
| 核心纠缠 | `api._build_trace`(372-414)反向引用 `debug_recommend._build_l1_trace`; `_gen_session_id` 走 `clock.now()` → session-id 日期前缀依赖业务时钟 |
| 心脏惰性引自调 LLM | `rerank.py:1157/1532` + `refine_intent_v2.py:462/539` 惰性 `import llm_client`(agent 走 do_llm 不实调) |

## 3. core/extras 边界(Codex 对齐后)

**CORE**:
- 协议/编排: `agent_*`(cli/protocol/orchestration/choose/round_store/skill_init)
- 推荐链路: `recall, score, rerank*, refine_intent_v2*, subtype_diversity, methodology, reference_resolver, l0_constraints, l1_prefs`
- 地基: `clock*, data_root*(白名单), state_root, state_migrate, install_root, loader, manifest, context, session, collector_contract, non_dish_rules`
- 反馈/trace: `feedback_signal, feedback_store, long_term_prefs, trace_store, trace_helpers`
- **新增**: `core_api_helpers`(从 api 抽)+ `trace_build`(从 api/debug_recommend 抽)
- **`status_bar` 进 core**(Codex 纠: pure payload, 零 dev 依赖; agent 是否真消费在 Step1 确认, 但无依赖故进 core 安全)
- `*` = 需改动文件

**EXTRAS(降级 dev/可选)**:
- sandbox: `sandbox, sandbox_context, sandbox_migration, sandbox_adapter, sandbox_decision_diff`
- web/debug: `web_api, debug_server, debug_recommend(纯 debug 残余), debug_what_if`
- 自调 LLM: `llm_client, llm_client_openrouter, llm_providers/`
- 老/被取代: `cli(老), refine(老), feedback(老), l1_extractor, schemas`

## 4. 关键设计(Codex 定)

- **DI = ambient provider singleton + test override hook**(clock/data_root 同款). 拒绝构造注入(全局函数无对象生命周期, 改签名面太大)/ 拒绝 ContextVar 作顶层抽象(ContextVar 仅留 sandbox provider 内部实现).
  - core 侧只持 `get_clock_provider()` / `get_sandbox_router()` 接口, default provider == 现 production 行为 → 0-diff.
  - sandbox extras 启用时注册虚拟时钟/路由 provider. `import sandbox` 移到 extras 侧.
  - **保留 invariant**: data_root.py:78-90 "sandbox 禁用 + 显式非 default session_id → raise"(provider 路由必须保).
- **函数级拆分**(铁律: `core → debug_*` 零容忍, 单向 `extras → core`):

| 函数 | 现位置 | 移到 |
|---|---|---|
| `_resolve_zone, _gen_session_id, _format_v2_candidate` | api.py | `core_api_helpers` |
| `_build_trace` | api.py:372-414 | `trace_build` |
| `_build_l1_trace, _format_ranked_for_trace` 等 | debug_recommend | `trace_build` |

## 5. 分步计划(小步多 commit, 每步 baseline 0-diff + Codex commit 触点)

- **Step 0 — deps 瘦身(零代码逻辑改动)**: pyproject `fastapi/uvicorn/anthropic/openai/pandas` 顶层 → `[dev]`/`[web]` optional. 存改前 baseline_l2_snapshot. 验证精简 deps 下 agent 路径能跑.
- **Step 1 — 抽 core 工具(无 DI)**: 新建 `core_api_helpers.py` + `trace_build.py`, 迁函数表, 改 api/debug_recommend/agent_cli import. 守门: baseline 0-diff + trace 路径&内容对比 + pytest.
- **Step 2 — DI clock**: clock 去 `import sandbox`, 引 clock provider(default 真实时间). sandbox extras 注册虚拟时钟. 守门: 0-diff + session-id 日期前缀断言 + `--at-time` rid 前缀显式测试.
- **Step 3 — DI data_root(白名单)**: 去 `import sandbox`, 引 sandbox router provider(default prod), 保 raise invariant. 守门: 0-diff + trace 写路径前缀对比 + refine trace v2→v3 migrate 回归.
- **Step 4 — 心脏解耦 llm_client**: rerank/refine_intent_v2 的 llm_client 惰性 import 收进 extras-only 分支. 守门: 0-diff + import 边界 smoke test.
- **Step 5 — 成核 + build**: import 边界 smoke 断言 core 不可达 sandbox/web/debug/fastapi/anthropic; `build_skill_bundle.py` 切 core 子树 + 精简 requirements + SKILL.md → skill 目录; skill 隔离实装跑全链路(eat→continue→choose→refine→`--at-time`).
- **收尾**: decisions D-104 + README/ROADMAP/CONTRACTS 同步 + memory 更新.

## 6. 守门 invariant(回归网, 含 Codex 补的 5 条)

1. baseline_l2_snapshot 0-diff(EPSILON=1e-6).
2. **trace 写路径前缀对比**(DI data_root 可能静默移 trace 落盘目录, 即使结果 0-diff; trace_store.py:85-142).
3. **refine trace append v2→v3 migrate + 孤儿 refine 拒绝**(trace_store.py:720-748, 当前回归网未覆盖).
4. **session-id 日期前缀断言**(_gen_session_id 走 clock.now, 不进 baseline L2 → 单独断言).
5. **`--at-time` + sandbox disabled → rid 前缀日期 == at-time**(MEMORY 记为 not-a-bug, 但无显式 case).
6. **import 边界 smoke**: `python -c "import chisha.agent_orchestration, chisha.recall, chisha.score"` 断言无 fastapi/uvicorn/anthropic 拉入.
7. wheel/skill 隔离实装实跑全链路.

## 7. 风险

`regression_risk = high`: 动 `data_root`(白名单)+ `clock`(地基)+ `rerank`/`refine_intent_v2`(心脏). 守门见 §6 + Codex 设计(已做)/commit(每 Step)双触点.
