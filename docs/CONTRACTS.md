# chisha · Agent 契约速查

> 主读者：Coding agent（Claude Code / Codex）每次会话。
> 装什么：**跨文件隐含约束** + **反直觉规则** + **系统级 invariant**——这些改错代码局部看不出，但会让管道静默错误或破坏产品行为。
> 不装：字段表 / schema keyset / prompt 行号 / 参数值 / 测试覆盖——这些 grep 代码就有。
> 决策原因看 [decisions.md](decisions.md)。当前文件只说"必须这样"，不解释"为什么"。

---

## 推荐链路 (L1 / L2 / L3)

### L1 召回
- **`hard_max_*` 和 `prefer_max_*` 不能混。** `hard_max_*` 真硬过滤超就砍；`prefer_max_*` 是软偏好进 L2 打分。改 `recall.py` 把任一软约束升级成硬过滤前，必须在 decisions.md 加一条说明（参 D-041）。
- **combo 数量 (2/3/4 道) 由 `profile.recall` 注入，不在代码 hardcode。** 改 combo 生成时不要写魔术数字（参 D-040）。

### L2 打分
- **`apply_caps()` 只返回 head 段，不带 tail。** brand cap=2 真正生效在 L2，**不能下放到 L3 prompt**（"输入里可能含多变体请择优"是错的方向，会让 cap 失效，参 D-049）。
- **改 `score.py` / `methodology.py` / spec yaml 前后必跑回归：** `uv run python -m scripts.baseline_l2_snapshot --out-dir tmp/baseline_traces`（改前）+ 改后再跑 + `compare_traces`。top60 顺序 + 16 维 breakdown `|delta| < 1e-6` 才允许 commit（参 D-072.1）。
- **methodology spec 只搬运不改逻辑。** 改打分逻辑 / 调权重 / 加新维度走 `score.py` + decisions 修订，**不走 spec**。spec 是 yaml 化的 `V2_DEFAULT_WEIGHTS`，不是新接口（参 D-072）。

### L3 精排
- **L3 输入 = top60。** 不是 40 / 100。如果输入大小要改，先看 D-046 的边界论证再动。
- **`config_error` 必须 hard-fail，不能被外层 `except Exception` 吞成 fallback。** 否则用户以为在跑 L3 实际没跑。改 `_resolve_provider` / `_run_llm_rerank` 时保持 `status="config_error"` + `resolved_provider=None` 透传到 trace（参 D-048）。
- **`_patch_system_prompt_for_cli` 找不到 `# 输出方式` 段必须 ValueError。** 防 prompt 改标题层级后 CLI 静默继续用 tool_use schema（CLI 不支持，会全失败）。
- **L3 一次性 retry-with-feedback，二次失败立刻走规则 fallback。** 不动不动重跑（CLI 成本敏感，参 D-050）。
- **`enforce_brand_unique` 在 L3 出口保留兜底**：同 brand 不同分店不能同时出现在最终 5 条。

### Provider 抽象
- **CLI provider 不支持 tool_use。** rerank 层做分流：`anthropic / openrouter` 走 tool_use forced schema；`claude_code_cli` 走 prompt + JSON 解析。不要试图统一 schema（参 D-038/D-048）。
- **`fallback_rerank` 规则路径必须永远可调用。** V1 简化路径已删 (D-049)，V2 是唯一推荐链路，但 V2 翻车时降级靠的是 fallback_rerank，不是恢复 V1。

---

## Refine / Mood

- **`infer_refine_mood` 只服务 `want_soup`。** 不许扩为通用 mood parser。新心情维度走 refine 自由文本或 L3 prompt，**绝不在前端加 mood chip**（参 D-071）。单测 `test_refine_mood.py` 有 8 case 守门。
- **explore 默认开启（top 5 中 1-2 个），refine 路径关闭。** 用户已主动给方向就不要再 explore（参 D-015）。

---

## Profile / 学习

- **`personal_offsets` 粒度 = `(cuisine, cooking, ingredient)`，不是 `店::菜`。** 改 offsets 写入 / 读取时不要回退到单菜粒度（参 D-025）。
- **`learned_profile` 用统计聚合，不用 LLM 蒸馏。** 如果要做 LLM 推理，输出只能作为 prompt 上下文，**不能作为 source of truth**（参 D-026）。
- **`taste_description` 自然语言字段，不要结构化拆分。** 想加结构化字段先看 D-014 为什么砍（仅 oil_level / protein_g 这种打分硬维度可结构化）。

---

## 反馈 (V1.1)

- **已提交 feedback record = 永久 readonly。** 不能 in-place 修改 ratings；后续走 `comments` append-only timeline（参 D-066/D-067）。改 `feedback_store.py` 时如果引入 mutation API 就是 bug。
- **三类信号语义不可混：** `gut`（-1/0/1）/ `calibration`（reason_match, oil_calibration）/ `behavior`（fullness, repurchase_intent）。schema 字段对应固定类别，不要新增字段时跨类（参 D-063~D-065）。
- **`comments` 不直接进打分。** 可作为 LLM 推理上下文，但 numeric ranking signal 只来自 structured ratings。
- **B-001 短链路 `feedback_recency` 守门口径：** `feedback_view=[]` 或 combo 名未命中时 **不写** `feedback_recency` 进 `score_breakdown`（保 baseline_l2 老 keyset 不变）。What-if 必须显式传 `__frozen.feedback_view`，不能让 sentinel `_UNSET_FEEDBACK_VIEW` 触发 `load_store(root)`（违反 D-079 "What-if 零 runtime read"）。生产链路在 `api.py`/`refine.py`/`debug_recommend.py` 入口一次性 `build_feedback_view`，同份传给 L2 + L3。

---

## 数据 / 打标

- **打标 LLM 必须看到价格。** 改 `tag_dishes.md` prompt 不要为了省 token 砍价格字段（参 D-008）。
- **生产打标默认 = `deepseek-v4-flash` (via OpenRouter)。** 想换模型先在 `eval/dish_tagging_eval/` 跑双模型对比，准确率持平再换（参 D-036/D-037）。
- **数据按 office_zone 拆，不混合**（`data/shenzhen-bay/` ≠ `data/home/`），recall 时按 profile.zones 切换。

---

## L1 长期偏好层 (D-076 / D-076.1)

- **L1 抽取走 `claude_code_cli` text + JSON 路径，不传 tools。** CLI 不支持 tool_use，prompt 在 `prompts/l1_extract.md`；改 prompt 走 D-036 dual-model audit。
- **词表锁定 = BOOST {low_oil, wetness, spicy, sweet_sauce} / PENALTY {sweet_sauce, processed_meat, carb_heavy, spicy}。** spicy / sweet_sauce 双向有意；`processed_meat / carb_heavy` 不许 boost（违反 harvard_plate baseline）。守门测试 `test_token_vocabulary_unchanged`。进一步扩词表 = 新决策 + baseline_l2 守门。
- **`score.taste_match_bonus` 走 `l1_prefs.load_prefs`，旧 `load_runtime_hints` 已 deprecated。** `rank_combos(l1_prefs_override=...)` 用 `_UNSET_L1_PREFS` sentinel 区分"未传"（默认 → `load_prefs(root)`）vs "显式 None"（What-if 明确禁用 L1），不许静默 fallback 到 live state（D-079 Codex BLOCKER #4 锚点）。
- **L1 → L3 prompt 桥 `root` 必须透传。** `rerank()` 主入口 + `refine.py` 调 rerank 都得显式 `root=root`。`_profile_block` 默认 root=None 时走 `_project_root` 兜底——测试用 monkeypatched ROOT 或多 worktree 场景下会跨 root 串数据。守门：`test_refine_passes_root_to_rerank`（参 D-078.2）。

---

## Sandbox Time-Travel (D-077 / D-078)

- **sandbox = user web 一个 mode，不是 CLI 替代或 fixture batch。** 行为完全一致 prod（禁 fake LLM / 跳 cooldown），仅时钟 + 数据落盘根隔离。
- **改时间相关逻辑前先看 12 处时间注入。** `web_api / api / refine / feedback_store / session / long_term_prefs / l1_extractor` 已替换走 `chisha.clock.*`。不注入：`time.time` latency / corrupt backup 时间戳 / comment id 毫秒（参 D-077 PR-1a + D-078 l1_extractor 修补）。
- **`l1_extractor.aggregate_inputs / extract_and_save` 必须透传 `root`，默认 today=`clock.today(root)`。** 守门测试 `test_aggregate_default_today_uses_chisha_clock` + `test_default_llm_call_uses_existing_llm_client_symbol` 不许删（参 D-078 P0）。
- **sandbox 生命周期：reset/disable 先抢 `_L1_EXTRACTION_LOCK`（`_block_until_l1_idle_or_409`），否则 worker 中途 `save_prefs` 会污染 prod `long_term_prefs.json`。** `advance` 在 `status=pending` 时直接返 409 防 UI bypass（参 D-078 Codex S2 Q3-High/Q2）。
- **`/api/accept` 必须 hard-fail 写 `meal_log.jsonl`，与 `record_accept` 同等级别。** `meal_log` 是 diversity cooldown 的 source-of-truth，砍掉写入 = 一周内重餐厅（参 D-078 P1）。
- **`sandbox inspect` 必须同时返 `long_term_prefs`（走 `load_prefs` 三态）+ `long_term_prefs_raw`（直读磁盘 raw json）。** `load_prefs` 在 boost+penalty 都空时返 None 是 L2 等价语义，但 inspect 必须显示 `regularities_freetext / signals_not_scored / evidence`（参 D-078.3）。

---

## Trace + Debug 三模式 (D-079)

- **trace 落盘走 `trace_store.write_trace`，失败仅 `logger.warning` 不阻断 recommend。** `read_trace` fail-closed：损坏抛 `TraceCorrupt` + 备份 `.corrupt.{ts}.bak`（与 D-066/067 一致）。改 trace schema 必 bump `TRACE_SCHEMA_VERSION`。
- **What-if 零 runtime read。** `chisha/debug_what_if.py:what_if_rerun` 必须 100% 用 `__frozen.{ctx, today, l1_combos, l1_prefs_snapshot, l2_meal_log_view, profile_snapshot}`，**严禁** `clock.today()` / `dt.date.today()` / `load_prefs(root)` 任何 runtime state read。加新冻结字段 → 同步 `_build_trace` 写入 + 测试守门。
- **Live 模式永不写盘。** `/api/debug_recommend`（老 D-039 端点）+ `chisha/api.py:recommend_meal(persist_trace=False)` 是 Live 入口，永不调 `trace_store.write_trace`——为"好调试"加 trace 写盘会污染 Replay 列表。
- **refine 二轮写 trace 必须先 `read_trace(sid)` merge 进同一文件。** Sidebar 一条 session 一行不分裂。missing → warn + 不持久化；corrupt → error + 不持久化。**绝不**创 refine-only 孤儿 trace。允许同文件加 `round2` 子键存 round-2 全量 L1/L2/L3/final（参 D-079 PR-4 + D-082）。
- **改 debug-ui 前端时：** 后端是单一可信源，`localStorage` 只作 7 天离线 fallback，永不参与后端列表合并；不动 `L1 / L2 / L3 / Final / Refine / Trace` 6 个 panel 组件——What-if 是 overlay 不重设计；URL state 用 `replaceState` 不 push。

---

## 调试台 (D-039 + D-075)

- **老调试台 = 独立 FastAPI on `:8765`，与主推荐链路解耦。** 调试逻辑不要混进生产代码 (`chisha/api.py`)。改打分链路时检查 `chisha/debug_recommend.py` instrumented 管道还能跑（参 D-039）。
- **新 debug-ui SPA (`apps/debug-ui/`) 独立 Vite 项目，端口 5174，不并入 `apps/web/`。** 只通过 `/api/*` 联调，backend 只在 `chisha/debug_recommend.py` ADD 字段不动既有键（参 D-075）。改 backend trace shape 同步 `apps/debug-ui/src/api/backend-types.ts`。

---

## 范围红线 (Phase 0 内不做)

不要在 Phase 0 内启动以下工作（已被推迟到 Phase 1+，避免 scope creep）：
- data zone 拆包发布 PyPI
- OpenClaw / Hermes 接入（待 D-074 草稿落定）
- screener 设计 / 同事推广前的注册流
- 第二份 methodology spec（减脂 / 糖控变体）
- L1 词表进一步扩（cuisine 偏好 token 等）
- 调试台 React 化（D-075 已 partial 实现，更进一步定位拆/合 留 Phase 1）

如果某 PR 触及上面任一项，先回头读 ROADMAP + decisions.md 确认是否真的要提前。
