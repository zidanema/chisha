# chisha · Agent 契约速查

> 主读者: Coding agent (Claude Code / Codex) 每次会话.
> 装什么: **跨文件隐含约束** + **反直觉规则** + **系统级 invariant** — 改错代码局部看不出, 但会让管道静默错误或破坏产品行为.
> 不装: 字段表 / schema keyset / prompt 行号 / 参数值 / 测试覆盖 — 这些 grep 代码就有.
> 决策原因看 [decisions.md](decisions.md). 当前文件只说"必须这样", 不解释"为什么".

---

## 第一原则 (系统宪法)

### Faithful Refine
- **系统对 refine 文本的理解深度和执行忠实度, 是用户对 chisha 信任的唯一来源.** 冲突时, 忠实优先于多样性 / 效率 / 探索 / narrative 美观 (D-080).
- 推论 1: refine ≠ 长期偏好补丁, 是一次完整、独立、最高优先级的表达.
- 推论 2: refine 的失败必须**显式告知用户** ("没找到 X, 按相似口味推 Y"), 不能默默偷换.
- 推论 3: narrative 美观永远不能跑在执行能力前面 — 链路错时漂亮 narrative 是信任放大器, 欺骗深、失信代价大 (D-085).

### L0 三分判定表 (refine 解除政策)
- **A 医学风险类** (过敏 / 药物冲突 / 孕期 / 术后): refine **永不可破**, 触发时显式提示.
- **B 身份伦理类** (清真 / 素食 / 宗教忌口): refine **永不可破**, 只能 profile 改.
- **C 普通健康类** (油 / 糖 / 蔬菜占比 / 价格带 / 减脂目标): refine **明确表达可破**, UI 提示「破戒模式」.
- 改 L0 类别归属前必须更新 profile schema + 这条契约 (D-082).

---

## 推荐链路 (L1 / L2 / L3)

### L1 召回
- **`hard_max_*` 和 `prefer_max_*` 不能混.** `hard_max_*` 真硬过滤超就砍; `prefer_max_*` 是软偏好进 L2 打分. 把任一软约束升级成硬过滤前, 必须在 decisions.md 加一条说明 (D-041).
- **combo 数量 (2/3/4 道) 由 `profile.recall` 注入, 不在代码 hardcode** (D-040).
- **methodology 硬契约下沉 L1 hard_filter, 软偏好留 L2 加权** (D-083). 长期方法论 (蔬菜 ≥ 50% / 油上限) 不与 popularity / variety 同台 PK, 直接 L1 出局.

### L2 打分
- **`apply_caps()` 只返回 head 段, 不带 tail.** brand cap=2 真正生效在 L2, **不能下放到 L3 prompt** (D-049).
- **改 `score.py` / `methodology.py` / spec yaml 前后必跑回归:** `baseline_l2_snapshot` (改前) + 改后再跑 + `compare_traces`. top60 顺序 + 14 维 breakdown `|delta| < 1e-6` 才允许 commit (D-072.1).
- **methodology spec 只搬运不改逻辑.** 改打分逻辑 / 调权重 / 加新维度走 `score.py` + decisions 修订, **不走 spec**.
- **`health_guardrail(combo, profile, intent=None)` 是 slot-aware** (D-090). intent=None 时行为与旧 API 一致 (R1 baseline 0-diff 守门); `intent.flavor_tags` 含 "heavy" 时 oil 触发豁免. 加新豁免类型走 D-090.x + `tests/test_l2_refine_snapshot_d090.py` 更新断言.
- **`score_combo` 在 refine 模式下按 explicit slot 动态调权重** (D-091 phase-2). `_build_refine_weight_overlay(intent)` 给 dim weight 加 multiplier. intent=None 时 overlay 空 dict → R1 0-diff. 改 overlay mapping 走 D-091.x + 断言更新.
- **`intent_match_bonus` 不再把 price_band 加到 cuisine 通道** (D-091 P2-B 语义解耦). price 维度独立兜底.
- **`score_combo` breakdown 是 14 维 (D-092: 11 基础 + 3 intent).** 已删 5 死维度 (`vegetable_floor_pass / protein_floor_pass / distance / wetness / context_boost`). 函数本身保留防 import 破, 但不再进 V2_DEFAULT_WEIGHTS / parts dict / spec / adapter DIM_ORDER. `compare_traces` 允许"key 缺失且对侧=0"视为 0-diff (兼容老 baseline).

### L3 精排
- **L3 输入 = top60.** 不是 40 / 100. 改输入大小先看 D-046.
- **`config_error` 必须 hard-fail, 不能被外层 `except Exception` 吞成 fallback.** 否则用户以为在跑 L3 实际没跑 (D-048).
- **`_patch_system_prompt_for_cli` 找不到 `# 输出方式` 段必须 ValueError.** 防 prompt 改标题层级后 CLI 静默继续用 tool_use schema (CLI 不支持, 会全失败).
- **L3 一次性 retry-with-feedback, 二次失败立刻走规则 fallback** (D-050). CLI 成本敏感.
- **`enforce_brand_unique` 在 L3 出口保留兜底**: 同 brand 不同分店不能同时出现在最终 5 条.

### Provider 抽象
- **CLI provider 不支持 tool_use.** rerank 层做分流: `anthropic / openrouter` 走 tool_use forced schema; `claude_code_cli` 走 prompt + JSON 解析. 不要试图统一 schema (D-038/D-048).
- **`fallback_rerank` 规则路径必须永远可调用.** V1 简化路径已删 (D-049), V2 翻车时降级靠 fallback_rerank 不是恢复 V1.

---

## Refine / Mood

- **`infer_refine_mood` 只服务 `want_soup`.** 不许扩为通用 mood parser. 新心情维度走 refine 自由文本或 L3 prompt, **绝不在前端加 mood chip** (D-071).
- **explore 默认开启 (top 5 中 1-2 个), refine 路径关闭.** 用户已主动给方向就不要再 explore (D-015).
- **refine 与空输入必须走差异化 L1 召回分支** (per_restaurant_max / 总召回 / top_k 兜底 / ingredient 反查). 空输入路径行为变化需 baseline_l2_snapshot 0 diff 验证 (D-084).
- **refine 多 slot LLM 解析必须带 3 安全带**: schema 验证 + 失败降级到"空 refine 模式" + UI 显式告知 / trace 双存 raw + 结构化 + raw_understanding / 改 prompt 或换模型必跑 eval set (D-081).
- **refine v2 schema 字段闭包 (D-094, 推翻 D-085 第二句)**: redirect 7 slot (`cuisine_want / cuisine_avoid / cuisine_candidates_expanded / ingredient_want / ingredient_avoid / brand_avoid / cooking_method_avoid`) + constrain 2 slot (`oil / price_max`) + `reference.relation∈{lighter, similar_but_different_venue}` 全部 L1/L2/L3 真消费. 已砍 trace-only 字段: `ingredient_synonyms / food_form_avoid / quality_floor / delivery_only / max_distance_km / functional.*`. `cooking_method_avoid` 是 **9 类枚举闭包** {油炸/凉拌/生/炖/炒/煮/蒸/烤/煎}, LLM 越界值在 `_clean_parsed_to_v2` 丢弃. schema 未覆盖诉求 (例: "不要面条") narrative 不假装支持, 老实说局限. F-011 数据打标后会重新加 food_form_avoid.

---

## Profile / 学习

- **`personal_offsets` 粒度 = `(cuisine, cooking, ingredient)`, 不是 `店::菜`** (D-025).
- **`learned_profile` 用统计聚合, 不用 LLM 蒸馏.** 如果要做 LLM 推理, 输出只能作为 prompt 上下文 (D-026).
- **`taste_description` 自然语言字段, 不要结构化拆分** (D-014). 仅 oil_level / protein_g 这种打分硬维度可结构化.

---

## 反馈 (V1.1)

- **已提交 feedback record = 永久 readonly.** 不能 in-place 修改 ratings; 后续走 `comments` append-only timeline (D-066/D-067).
- **三类信号语义不可混**: `gut` / `calibration` / `behavior`. schema 字段对应固定类别, 不要跨类 (D-063~D-065).
- **`comments` 不直接进打分.** 可作为 LLM 推理上下文, 但 numeric ranking signal 只来自 structured ratings.

---

## 数据 / 打标

- **打标 LLM 必须看到价格** (D-008). 改 `tag_dishes.md` prompt 不要为了省 token 砍价格字段.
- **生产打标默认 = `deepseek-v4-flash` (via OpenRouter)** (D-037). 想换模型先在 `eval/dish_tagging_eval/` 跑双模型对比.
- **数据按 office_zone 拆, 不混合** (`data/shenzhen-bay/` ≠ `data/home/`).

---

## L1 长期偏好层 (D-076 / D-076.1)

- **L1 抽取走 `claude_code_cli` text + JSON 路径, 不传 tools.** prompt 在 `prompts/l1_extract.md`; 改 prompt 走 D-036 dual-model audit.
- **词表锁定** = BOOST `{low_oil, wetness, spicy, sweet_sauce}` / PENALTY `{sweet_sauce, processed_meat, carb_heavy, spicy}`. `processed_meat / carb_heavy` 不许 boost (违反 harvard_plate baseline). 守门 `test_token_vocabulary_unchanged`. 扩词表 = 新决策 + baseline_l2 守门.
- **`score.taste_match_bonus` 走 `l1_prefs.load_prefs`, 旧 `load_runtime_hints` 已 deprecated.** `rank_combos(l1_prefs_override=...)` 用 `_UNSET_L1_PREFS` sentinel 区分"未传"vs"显式 None", 不许静默 fallback.
- **L1 → L3 prompt 桥 `root` 必须透传.** `rerank()` + `refine.py` 调 rerank 都得显式 `root=root`. 守门 `test_refine_passes_root_to_rerank`.

---

## Sandbox Time-Travel (D-077 / D-078)

- **sandbox = user web 一个 mode, 不是 CLI 替代或 fixture batch.** 行为完全一致 prod (禁 fake LLM / 跳 cooldown), 仅时钟 + 数据落盘根隔离.
- **所有时间相关路径走 `chisha.clock.*` 注入, 默认 today 不能裸调 `dt.date.today`.** 例外见 D-077 PR-1a (latency / corrupt backup 时间戳 / comment id 毫秒).
- **`l1_extractor.aggregate_inputs / extract_and_save` 必须透传 `root`, 默认 today=`clock.today(root)`** (D-078 P0).
- **sandbox 生命周期: reset/disable 先抢 `_L1_EXTRACTION_LOCK`** (`_block_until_l1_idle_or_409`), 否则 worker 中途 `save_prefs` 会污染 prod `long_term_prefs.json`. `advance` 在 `status=pending` 时直接返 409 防 UI bypass.
- **`/api/accept` 必须 hard-fail 写 `meal_log.jsonl`, 与 `record_accept` 同等级别** (D-078 P1). meal_log 是 diversity cooldown 的 source-of-truth.
- **`sandbox inspect` 必须同时返 `long_term_prefs` (走 `load_prefs` 三态) + `long_term_prefs_raw` (直读磁盘 raw json)** (D-078.3).

---

## Trace + Debug 三模式 (D-079)

- **trace 落盘走 `trace_store.write_trace`, 失败仅 `logger.warning` 不阻断 recommend.** `read_trace` fail-closed: 损坏抛 `TraceCorrupt` + 备份 `.corrupt.{ts}.bak`. 改 trace schema 必 bump `TRACE_SCHEMA_VERSION`.
- **What-if 零 runtime read.** `chisha/debug_what_if.py:what_if_rerun` 必须 100% 用 `__frozen.{ctx, today, l1_combos, l1_prefs_snapshot, l2_meal_log_view, profile_snapshot}`, **严禁** `clock.today()` / `dt.date.today()` / `load_prefs(root)` 任何 runtime state read.
- **Live 模式永不写盘.** `/api/debug_recommend` + `chisha/api.py:recommend_meal(persist_trace=False)` 是 Live 入口, 永不调 `trace_store.write_trace`.
- **refine 二轮写 trace 走 `trace_store.append_round`.** 同 sid 多轮持久化到 `{sid}/meta.json` + `{sid}/rounds/R{n}.json`, 文件锁 `{recommend_trace_dir}/.lock-{sid}` 序列化. **绝不**创 refine-only 孤儿 trace.
- **trace 自包含原则**: 所有 LLM call 的 `system_prompt_full` / `user_message_full` / `raw_response` body 必须落 trace, 不能事后从 `prompts/*.md` 重建 (prompt 会迭代, 留 chars 丢 body 等于 trace 无法 replay). `usage` 统一 Anthropic-style 命名, 由 `trace_helpers.normalize_usage_fields` 在落盘前转换.

---

## 调试台

- **老调试台 = 独立 FastAPI on `:8765`, 与主推荐链路解耦.** 调试逻辑不要混进 `chisha/api.py`.
- **新 debug-ui SPA (`apps/debug-ui/`) 独立 Vite 项目, 端口 5174, 不并入 `apps/web/`** (D-075). 只通过 `/api/*` 联调.
- **debug-ui SPA 100% read-only.** Live / What-if / Refine submit 路径全删; 4 个 endpoint 都是 GET. 加写入入口前先在 decisions 加新条目, 不要复活已删的写入路径.
- **Trace v3 目录布局是 append_round / 多 round 持久化的唯一形式.** `read_trace_v3_view` 走 on-read migrate (v2 单文件 → 转 v3 目录). `TRACE_SCHEMA_VERSION = 3`, `ACCEPTED_TRACE_VERSIONS = {1, 2, 3}`.

---

## Sandbox Lab

- **`sandbox_context` ContextVar 注入 sid, 不靠全局 active session.** 多 tab 并发 eat 不能串 session.
- **`meal_to_trace.json` 是 sid → trace 唯一索引.** rollback / branch / trace 跳转都按此查.
- **D-077 旧签名兼容**: `sandbox.{init,advance,reset,state,...}` 接受 `sid=None` 走 `_default` session. 改签名前先检查老调用方.
- **`sessions/{sid}` 整目录拷贝/裁剪是 branch / rollback 的原子单位.** 必须同步重置 `long_term_prefs / decisions / meal_to_trace / recommend_log / recommend_trace`, 否则记忆跨分支泄漏.
- **Refine 单 round (Phase 0)**: backend 不维护跨顿 refine. `advance_meal` 后 `last_recs.applied_refine` 清空.

---

## 范围红线 (V1.0 后 Phase 1 推广前不做)

不要在 V1.0 工程里程碑收尾后启动以下工作 (推迟到 Phase 1 推广启动后):
- data zone 拆包发布 PyPI
- 外部 Agent (OpenClaw / Hermes) 接入 (待 D-074 草稿翻 active)
- screener 设计 / 同事推广前的注册流
- 第二份 methodology spec (减脂 / 糖控变体)
- L1 词表进一步扩 (cuisine 偏好 token 等)
- 调试台 React 化整合

如果某 PR 触及上面任一项, 先回头读 ROADMAP + decisions.md 确认是否真要提前.
