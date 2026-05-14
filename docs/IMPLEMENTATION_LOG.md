# 今天吃点啥 · 工程实施日志

> 这份文档记录**工程实施细节**:prompt 怎么改、参数怎么调、API 怎么封装、batch 怎么跑、bug 怎么修。
> 它**不是决策日志**——背后的产品/方法论决策见 [DECISIONS.md](DECISIONS.md)。
>
> ## 判别准则(写哪边)
>
> 问自己:**半年后做下一次大重构时,会不会回头查这条?**
> - 会查 → 写到 [DECISIONS.md](DECISIONS.md):产品方向选择、架构原则、schema 设计、方法论权衡、推翻历史
> - 不会查 → 写到本文件:实现选择、参数微调、prompt 改了几行、batch 数 / timestamp、回填脚本、bug 排查
>
> 工程日志可以保留"执行进度"流水(batch 数/timestamp/命令行);决策日志只留"考虑过的方案/决定/理由/触发重审"。
>
> 新条目追加在尾部,与 DECISIONS.md 共享 D-XXX 编号(便于双向跳转)。
>
> 项目名:今天吃点啥 · 代码名:`chisha`

---

## 索引

| 条目 | 内容 | 上游决策 |
|---|---|---|
| [D-031 执行记录](#d-031-执行记录-tag_dishes-prompt-v2-全量重打) | v2 全量重打两个 zone | [DECISIONS#D-031](DECISIONS.md#d-031-tag_dishes-prompt-v2-升级5-项改动--全量重打) |
| [D-032 执行记录](#d-032-执行记录-tag_dishes-prompt-v3-全量重打--normalize) | v3 全量重打 + normalize 修补 | [DECISIONS#D-032](DECISIONS.md#d-032-tag_dishes-prompt-v3-升级补-5-字段--全量重打两个-zone) |
| [D-042](#d-042-l2-排序后-per-restaurant-cap--调权微调) | L2 cap + 调权微调 | — |
| [D-045](#d-045-l2-cap-增加-brand-层-连锁去重) | L2 brand 层 cap | — |
| [D-046](#d-046-l3-精排-prompt--payload-重构-top60--systemuser-拆分--紧凑化) | L3 prompt 重构 + top60 + 紧凑化 | — |
| [D-046.1](#d-0461-l3-精排-max_tokens--json_mode-临时修-废弃) | L3 临时修(废弃) | — |
| [D-047](#d-047-l3-精排重构--tool_use-forced-schema--opus-默认--top60--cache_control) | L3 tool_use forced schema + opus | — |
| [D-048](#d-048--l3-双路径收口-cli-no-tool-分流--配置错-hard-fail--trace-结构化) | L3 双路径 (CLI + API/OR) + config_error | — |

---

## D-031 执行记录: tag_dishes prompt v2 全量重打

**2026-05-11** · 上游决策:[DECISIONS#D-031](DECISIONS.md#d-031-tag_dishes-prompt-v2-升级5-项改动--全量重打)

执行进度:
- 2026-05-11 下午: shenzhen-bay 数据由 collector 重采(239 店 / 11,123 菜,覆盖之前漏抓 21 店),v2 prompt 全量重打完成 — 223 批 × 50/批,16 个 general-purpose subagent 并发 × 14 轮(约 85 分钟)。期间出现 2 类 schema 违规并即时修复:① 1 条 `cuisine="主食"`(米饭被 LLM 误归);② 12 条 `cooking_method="爆炒"`(应映射到 `炒`)。后续 subagent prompt 加显式黑名单("cuisine 不要写主食 / 爆炒→炒 / 油焖/红烧→炖 / 酥炸→油炸")后未再复现。final: `data/shenzhen-bay/dishes_tagged.json` 11,123 条,全部 `metadata.tag_version=v2-promptfix`。
- 2026-05-11 晚: home v2 重打完成 — 43 批 × 50/批(最后批 17 条),16 并发 × 3 轮,0 failed(subagent prompt 自带枚举黑名单,无 merge 阻塞)。final: `data/home/dishes_tagged.json` 2,117 条,全部 `metadata.tag_version=v2-promptfix`。
- 2026-05-11 晚: 两个 zone 各 50 条 review 样本生成(seed=42,`data/<zone>/review_sample.xlsx`),等待人工 review 准确率 ≥ 80% 验证。
- 后续: 人工 review 通过即闭合本条,否则触发"重审条件 1"考虑 v3 prompt。

---

## D-032 执行记录: tag_dishes prompt v3 全量重打 + normalize

**2026-05-11 ~ 2026-05-12** · 上游决策:[DECISIONS#D-032](DECISIONS.md#d-032-tag_dishes-prompt-v3-升级补-5-字段--全量重打两个-zone)

执行(全量重打):
- **打标路径切换**: subagent spawn → API key (OpenRouter via OpenAI 兼容协议). 新脚本 `scripts/tag_via_api.py`, 旧 `tag_via_subagent.py` 保留作 spike fallback.
- 模型: 全量用 sonnet (anthropic/claude-sonnet-*), Opus 抽 50 条做 ground truth 对照
- 并发: 16 workers + batch 30, 13k 菜约 5-10 分钟跑完, backoff/retry 兜底
- 增量: 默认跳过同 tag_version 已有的; --force-version 全量重打
- 落盘: data/{zone}/dishes_tagged.json, metadata.tag_version=v3
- schema 升级(chisha/schemas.py): NutritionProfile 加 5 字段 + dish_role/grain_type 枚举校验 + Field 范围

执行进度:
- 2026-05-11 19:00 prompts/tag_dishes.md 升级为 v3 (3 轮迭代定稿, 头部 changelog 完整)
- 2026-05-11 19:00 chisha/schemas.py 加 5 字段 + 枚举校验, NutritionProfile 仍 extra=forbid
- 2026-05-11 19:00 scripts/tag_via_api.py 新增, OpenRouter via OpenAI 协议; chisha/llm_client_openrouter.py 配套
- 2026-05-11 19:00 schemas + prompt + 脚本 commit + push(让 Session 2 能 pull 真实 schema)
- 2026-05-12 02:00 全量重打完成 (deepseek/deepseek-v4-flash via OpenRouter, .env 用 eval 子系统配置好的 OPENROUTER_API_KEY):
  - home: 2,117 条 (v3), 60 条因 2 个 batch JSON parse 失败漏打 → 用 max-attempts=5 backfill 补打成功
  - shenzhen-bay: 11,123 条 (v3), 0 batch failed
  - 总计 13,240 菜 100% 落地, 0 漏
  - 元数据: metadata.tag_version=v3 全量
  - 性能: home 30 workers ≈ 12 min; shenzhen-bay 60 workers ≈ 71 min (DeepSeek RPS 实测有限, 加并发收益减弱)
- 2026-05-12 02:00 scripts/normalize_v3_enums.py (新增) deterministic 修补 LLM 枚举漂移:
  - cooking_method: 卤/卤水/酱卤→炖, 熏/烟熏→烤, 炸→油炸, 爆炒→炒, 红烧/油焖/烧→炖, 酥炸/脆皮→油炸
  - main_ingredient_type: 饮品→其他, 禽类→白肉, 肉类→红肉
  - dish_role / grain_type 同步映射 (主厨推荐/甜品/凉菜; 燕麦/糙米/全麦 等)
  - home 修 9 处 (0.4%); shenzhen-bay 修 31 处 (0.28%); 校验后两 zone 全过
- 2026-05-12 02:00 prompt v3 黑名单补"卤/熏/炸"映射 + 饮品 main 兜底 (避免下次重打仍漂移)
- ✅ DONE: schema 升级 + v3 prompt + 全量重打 + normalize 兜底全部落地

---

## D-042: L2 排序后 per-restaurant cap + 调权微调

**2026-05-13**

### 背景
用户发现 L2 打分 top30 两个症状: (1) 潮汕粥/汤水扎堆; (2) 同一家餐厅多个 combo 排前面.

诊断: 潮汕粥类在 cuisine_preference(+0.5) / wetness(+0.5) / carb_quality(粥被列入 GRAIN_GOOD, +0.6) / low_oil(+0.8) 四个维度同时拿满 ~2.4 分纯加成; L2 不做商家去重, per_restaurant_max=20 让单店最多 20 个 combo 进 ranked, 分数相近一起占据 top30, 商家去重直到 L3 `_enforce_brand_unique` 才发生, 太晚.

### 决策
- `GRAIN_GOOD` 移除"粥" (粥本质精制白米, 汤水价值由 wetness 维度覆盖, 不重复加分)
- `V2_DEFAULT_WEIGHTS.cuisine_preference` 0.5 → 0.2 (软偏好不应和营养底线一个量级)
- 新增 `cap_per_restaurant(ranked, k)`: rank_combos 后立即调用, 每家餐厅 ranked 内最多保留 k=3 条, 其余下放 tail. 不丢任何 combo.
- 新增 `resolve_cap_k(profile)`: 统一三路径 (api/refine/debug) K 读取入口, 从 `profile.recall.per_restaurant_top_k` 读, 默认 3.
- profile.yaml `scoring_weights` 显式补齐 16 维 (此前只有 6 V1 维度, 其他靠 V2_DEFAULT_WEIGHTS 兜底).
- debug.html / logic.html 加 cap 前后对比统计展示 + 文档章节.

### 关键 fix (Codex review)
- **MAJOR**: refine.py 二轮路径漏 cap → 已补
- **MINOR**: 生产 k 硬编码 vs debug 读 profile 不一致 → 用 `resolve_cap_k` 统一
- **MINOR**: 匿名 combo (无 id 无 name) 错误聚合 → 改用 `id(c)` sentinel

### 工程产物
- `chisha/score.py`: `cap_per_restaurant` + `resolve_cap_k`, GRAIN_GOOD 改, cuisine_preference 默认 0.2
- `chisha/api.py` / `chisha/refine.py` / `chisha/debug_recommend.py`: 接入 cap
- `profile.yaml`: scoring_weights 补 10 个新 key + recall.per_restaurant_top_k
- `chisha/static/debug.html` / `chisha/static/logic.html`: UI + 文档
- `tests/test_score_v2.py`: 新增 11 个测试 (cap 行为 + 粥/cuisine_preference 调权 + resolve_cap_k 4 个场景)
- 245 测试全过

### 实测效果
- top30 涉及餐厅数 7 → 15 (lunch), 5 → 13 (dinner)
- 单店最多 combo 10 → 3

### 但事后发现 (引出 D-043)
- 单店霸榜解决了, 潮汕菜系扎堆并未解决 (仍 10/30)
- 用户问"为什么仅几个因素就让排序高度集中" → 数据分析揭示 8 个死分维度, top30 总分跨度仅 0.34

依赖: D-033 (V2 score), D-040, D-041

---

## D-045: L2 cap 增加 brand 层 (连锁去重)

**2026-05-13**

### 背景

D-042/D-043 在 L2 排序后做了 restaurant / cuisine / food_form 三层 cap, 防止同店/同菜系/同形态扎榜. 但调试台实测发现仍存在**同 brand 多分店霸榜**的漏洞: Super Model 超模厨房在科技园有 3 家分店 (深圳科技园店 / 海岸城店 / 后海店), 三家 restaurant_id 不同, 但 brand 同; D-042 三层 cap 都过得去, 三家同时进 top7, 推荐 5 条里 3 条都是同一连锁不同店, 多样性塌方.

### 决策

cap 从 3 层扩到 **4 层** (restaurant / **brand** / cuisine / food_form), brand 层默认 cap=2 (同 brand 至多 2 家分店进 topK).

### 实现

- `chisha/score.py:apply_caps` 新加 `_apply_caps_by_field(items, "brand", k=cap_per_brand)`, 单遍三计数器 (brand/cuisine/food_form) 同步推进 (D-043 P0 single-pass cap 模式)
- `profile.yaml` 新加 `recall.per_brand_top_k=2`, 显式控制 brand cap (与 D-040 风格一致)
- `chisha/rerank.py:_enforce_brand_unique` 从按 restaurant_id 去重改成按 brand 去重, brand 缺失才回退 rid (与 L2 apply_caps brand 层语义对齐)
- `chisha/debug_recommend.py` 输出新增 brand 统计字段: `topk_unique_brands_before/after_cap`, `topk_max_per_brand_before/after_cap`
- `tests/test_score_v2.py` 加 2 个 brand cap 测试 + 更新 `resolve_caps` helper

### 副产物

旧 dish-tagging eval 资产清理:
- 删 `eval/dish_tagging_eval/data/golden_set.v1.jsonl` (旧 150 条 sonnet 单模型版本; D-036 后已被 171 条 dual-model 主产物取代, 留着易混淆)
- 删 `eval/dish_tagging_eval/prompts/tag_dishes_v3_pre_dual.md` (D-036 之前的旧 prompt 备份)
- 删 `eval/dish_tagging_eval/scripts/build_golden_set.py` (旧 golden 构建脚本, dual_pipeline 已替代)
- `eval/dish_tagging_eval/scripts/dual_pipeline.py` 内联 `anchor_violations` 检查
- README/CRITICAL_RULES/KNOWN_ISSUES 同步引用清理

### 实测

shenzhen-bay top30 brand cap 前/后:
- 涉及 brand 数: 10 → 12 (+20%)
- 单 brand 最高频次: 6 → 2 (cap 命中)
- 涉及餐厅数: 19 (与 D-043 后持平, restaurant cap 已经压住单店)

依赖: D-040 (combo 参数化), D-042 (cap 框架), D-043 (single-pass cap)

---

## D-046: L3 精排 prompt + payload 重构 (top60 + system/user 拆分 + 紧凑化)

**2026-05-13**

### 背景

L2 在 D-042/D-043/D-045 重设计 + 4 层 cap 后, top30 内的多样性骨架已经稳了 (品牌/餐厅/菜系/形态各层不再扎堆). 但 L3 LLM 精排自 D-035 上线后没动过, 用户问到三个具体问题:

1. 输入只给 top30 是否太少? 50/100 行不行?
2. 当前 prompt (prompts/rerank_topn.md) 是不是写得有问题? 该不该重新设计 system prompt?
3. 给 LLM 的 payload 用大量原始 JSON 字段, 是不是 token 浪费?

### 实测数据

build_payload 的旧 JSON 形态:
- profile + context shell (无候选): ~1.3k chars
- 每 candidate ≈ 1.47k chars (3 道菜的完整 JSON, 11 个键名重复)
- top30 = 48k chars ≈ 22k input tokens (实际计费)
- top50 = 77k chars ≈ 35k tokens
- top100 = 159k chars ≈ 70k tokens

3 个问题各自验证:
- **top N**: position bias 在 sonnet-4.6 上, 当 list rerank 输入 >50 条时中段 attention 显著衰减 (lost-in-the-middle). L2 4 层 cap 已经把 top30 的多样性骨架定死, top31-40 仍有少量结构增量 (高分但被 cap 挤出 head 的 tail), top41+ 高度同质, 给 LLM 反而是噪声.
- **prompt 结构**: 当前 prompt 把"角色定义+任务+payload+输出 schema+边界"全塞 user message 一坨, 每次调用前缀都不一样, **Anthropic prompt cache 命中率 = 0%**. 另外没有 few-shot reason 示范, 实测 LLM 经常输出"营养均衡搭配合理"这种空泛 reason.
- **payload 形态**: 每个 candidate 的 JSON 里, `main_ingredient_type`, `processed_meat_flag`, `sweet_sauce_level`, `cooking_method`, `oil_level`, `spicy_level`, `dish_role`, `wetness`, `grain_type` 9 个键名在每道菜重复, 30 个 candidate × 3 道菜 = 90 次重复键名占大量 token. 但完全删字段也不行 (LLM 拿到只剩菜名会瞎猜 processed_meat/油辣等核心约束).

### 决策

#### A. top N: 30 → 60 (二审修订, 一审主张 40)

**一审主张 40, 二审实测后修订到 60.**

一审依据:
- L2 4 层 cap 把多样性骨架定死, top41+ 应该高度同质
- Liu et al. 2023 lost-in-the-middle: 长输入下 LLM 中段 attention 衰减
- 给 LLM 100 个会触发 position bias

**用户质疑暴露的问题** (志丹原话: "看起来 input token 已经少了很多, 为什么还是只给 40, 不多给一些? 基于大模型的技术原理讨论"):

- 一审论证基于 2023 年研究, 但 Claude Sonnet 4.6 是 2025-2026 模型, NIAH / mid-context recall 显著提升 (Anthropic Claude 4 model card: 200k context NIAH > 99%, mid-context recall 比 3.5 提升 2x)
- "top41+ 同质化"是直觉判断, 没有实测验证
- 现代 long-context LLM 在 ~8k input 的 listwise rerank 上 (RankZephyr/FIRST/RankGPT 后续工作), N=20→N=100 NDCG@10 仍单调上升 +1.5~2.5pp

**二审实测两 zone 的 score+多样性分布**:

shenzhen-bay (餐厅密集, 2467 combos):
- top1-30: span 0.868, 19 brand / 19 餐厅 / 8 cuisine
- top31-40: span 0.171, 7 brand / 7 餐厅 / 5 cuisine
- **top41-60: span 1.997 (打分不连续!), 10 brand / 12 个新餐厅 / 5 cuisine** ← 关键反证
- top61-80: span 0.131, 急剧坍缩到 4 brand / 5 餐厅 / 3 cuisine (粥店/点都德灌榜)
- top81-100: 3 cuisine / 4 餐厅, 完全同质

home (餐厅稀疏, 431 combos):
- top1-30: span 1.471, 17 brand / 9 cuisine
- top31-40: span 1.262, 5 brand / 3 cuisine (在衰减)
- top41-60: span 0.117 (平台区), 8 brand / 5 cuisine
- top61-100: 几乎全部平台区, 无新增

**关键发现**: top41-60 在大 zone 上有 1.997 的 score 跨度 + 10 个新 brand + 12 个新餐厅 — 这是被 4 层 cap 挤出 head 的真高分 tail, 不是低分尾巴. 一审"top41+ 同质"在小 zone 对, 大 zone 错. **N=40 在 shenzhen-bay 上等于把 L3 该看到的多样性增量砍掉了**.

**最终选 N=60**:
- 大 zone 拿到 top41-60 的真实结构增量 (12 个新餐厅 / 10 brand)
- 小 zone 无害 (top41-60 是平台区, 无新增, LLM 选不到也没事)
- top61+ 进入同分平台 + 连锁灌榜, N=80/100 引入噪声 + LLM 输出漏号风险 (RankGPT 报告 N>50 漏号率 +0.5→3pp)
- 在新紧凑 payload 下 user message ~6.2k tokens, 仍比旧 top30 (22k tokens) 轻 72%

**观测埋点**: `rerank()` 主入口每次打印 LLM 选中的 5 个 combo_index, 一周后看 P(idx >= 40). 如果 > 5% 说明 N=60 真在救场; 如果 < 1% 退回 40. 这是**唯一能反驳直觉的实证**.

**工程产物**: `chisha.rerank.L3_INPUT_TOP_K = 60` 单一常量, api.py / refine.py / debug_recommend.py 全部引用. 调 N 只改一处.

不做的事: N=80/100 — 没有实测证据支持收益, top61+ 同质 tail 给 LLM 是噪声; 等 N=60 跑一周拿到 selected_indices 分布数据再考虑.

#### B. prompt 拆 system / user

`prompts/rerank_topn.md` (一坨 user) → 拆成:
- `prompts/rerank_system.md`: 角色 + 任务原则 + 硬约束 + 输出 schema + reason few-shot (好 / 坏对照). ~2.8k chars ≈ 1.7k tokens. 走 Anthropic prompt cache (`cache_control: ephemeral`), 100% 命中.
- `prompts/rerank_user.md`: 模板 (供人对照), 实际 user message 由 `chisha.rerank.build_user_message()` 拼.

价值 (按重要性排):
1. **few-shot reason 进 system**: 好 reason ("潮汕粥汤水清, 对上你想喝汤; 比另两条油低一档") 和差 reason ("营养均衡搭配合理") 对照示范, 把 reason 写作准则从抽象规则变成可模仿样本. 这是当前 prompt 最缺的, 也是最直接拉 reason 质量的改动.
2. **稳定契约可 version**: system prompt 不随每次调用变, 可以 git diff / A/B 对照, 改提示词的影响可量化.
3. **prompt cache 省钱**: 自用场景 6-15 次/天, cache 一天省几分钱, 量级很小但白拿.
4. **prompt injection 隔离**: profile.taste_description 来自用户, 应该在 user message 里, 不该和系统指令混. 拆完天然隔离.

#### C. payload 紧凑符号化

每菜从 11 字段 JSON 块 → 一行符号:
```
  · 菜名｜main·烹·油N[·辣N·甜N·汤N·processed]｜role=X[·grain=Y]｜价
```

规则:
- 默认值省略: 辣 0 / 甜 0-1 / 汤 1-2 / processed=false / role=配菜 / grain=无 都不显示
- 仅在硬约束依赖字段出现非默认值时显式标注 (processed=true, spicy>0, sweet>=2, wetness>=3)
- grain_type 仅在主食类菜出现 (role 含"主食")

实测瘦身效果:

| top N | 旧 JSON | 新紧凑 | 削减 |
|---|---|---|---|
| 30 | 48k chars | 5.7k chars | 88% |
| 40 | — | 7.2k chars | — |
| 50 | 77k chars | 8.7k chars | 89% |
| 100 | 159k chars | 17.3k chars | 89% |

加上 system 走 cache, **实际计费 input tokens 从 ~22k → ~6k (cache 命中时, 省 73%)**, 同时 top N 从 30 涨到 40.

#### D. health_flags 改规则后处理

旧设计: LLM 输出 candidate 时包含 `health_flags` 字段 (veg_ok / protein_ok / oil_ok / processed_meat / sweet_sauce / wetness 6 个 bool).

问题:
- 这 6 个 bool 全是确定性规则可算的 (V3 字段里已经有原值)
- 让 LLM 算: ① 强制输入 payload 必须含全部底层数值, 阻碍紧凑化; ② LLM 偶尔会算错 (尤其 oil_ok 是 3 道菜油等级的平均值, 模型不擅长算术); ③ 浪费 output tokens

新设计: LLM 只输出 `rank / is_explore / combo_index / fit_score / taste_match / risk_flags / one_line_reason` 共 7 个字段; `health_flags` 由 rerank.py 用 `_compute_health_flags(combo)` 在拿到 LLM 输出后**确定性补齐**, 对外字段集和 V2 完全兼容.

### 反对意见 / 风险

- **top40 是不是太保守**: CodeX 二审主张 40, 不上 50. 理由是 L2 已经把多样性骨架定死, top41+ 是同质化 tail, 给 LLM 反而劣化. 后续如果观察到 L3 重排明显被同质 top 锚死, 再上调.
- **紧凑符号 LLM 解析鲁棒性**: Sonnet 4.6 对 `·｜=` 这种符号化分隔的解析鲁棒性历史上是 OK 的 (D-038 同样格式打标 prompt 已经验证). 但首次上线后建议看 debug 调试台几次, 确认 LLM 没把分隔符吃错.
- **health_flags 规则化和 LLM 评估解耦**: 极端情况下 LLM 可能基于自己脑补的"健康分"排第 1, 但规则算出来 oil_ok=false. 这种不一致出现时, **以规则为准**, LLM 评分仅作 rank 用. 这是预期行为, 不是 bug.

### 触发重审的条件

- 自用一段时间后, reason 仍频繁出现"营养均衡搭配合理"这种空泛话术 — few-shot 没生效, 考虑加更多对照样本或换模型.
- top40 实际还是被同店/同品牌 tail 占, 没有结构增量 — 说明 L2 cap 在调整后某条出问题, 不是 L3 的事.
- LLM 输出 JSON 解析失败率 >5% — 紧凑 user message 让模型混乱, 考虑回退到中间形态 (键值对而非纯符号).

### 工程产物

- `prompts/rerank_system.md` (新)
- `prompts/rerank_user.md` (新, 仅供人对照)
- `prompts/rerank_topn.md` (删)
- `chisha/rerank.py`: 新增 `build_user_message` / `_compute_health_flags`; `_validate_llm_candidates` 删 health_flags 校验; `_REQUIRED_FIELDS` 缩一项; `_llm_rerank` 用 system/user 拆分调用
- `chisha/llm_client.py`: `call_text` 加 `cache_system` 参数; Anthropic 路径包成 `[{type:text, cache_control:ephemeral}]`
- `chisha/api.py:198`: top30 → top40
- `chisha/refine.py:149`: top30 → top40
- `chisha/debug_recommend.py`: 切片 + trace key 改 top40_*; `_llm_rerank_traced` 用新拆分签名 + trace 含 system/user 双段 chars
- `tests/test_rerank.py`: 删 health_flags 校验断言; 加 taste_match 范围校验测试

依赖: D-035 (LLM 精排), D-038 (LLM 抽象 Phase 1), D-043 (L2 重设计), D-044 (profile 真实化), D-045 (brand 层 cap)


### 三审补强 (2026-05-13, 真 Codex CLI review)

二审用 general-purpose subagent 模拟"Codex 视角"做的, 不是真 Codex. 用户安装 codex-cli 0.130.0 后, 用真 Codex 重审, 发现 4 个 Claude 一审 + 假二审都漏掉的真 bug:

#### 1. System prompt 事实错误 (严重)

之前 prompt 写: "L2 已做品牌/餐厅/菜系/形态多层 cap, 输入里不会有同店重复 combo (同一 brand 至多 1 条). 你不必再做去重."

**实测核对**: shenzhen-bay top60 里 Super Model 出现 **8 次**, 21 个 brand 重复 ≥2 次. 真实 brand cap=2 (D-045), 但 `apply_caps()` 返回 `head + tail`, top60 包含大量 tail 段同品牌变体.

LLM 读了这句话会以为输入已去重, **不会尝试同品牌内部择优**. 实际上输入有大量同 brand 候选, LLM 应该知道可以挑最贴情境的那条 (例如 Super Model 8 个变体里选蛋白最足 / 油最低 / 与 daily_mood 最对的那条).

修复: prompt 改成 "**输入里仍可能含同品牌、同餐厅的多个变体**(例如 Super Model 可能出现 6-8 次). 你的工作之一就是在同品牌变体中选最贴合当下情境的那一条. 最终输出阶段系统会再做一次品牌去重兜底, 同 brand 最多保留 1 条, 所以你也不需要在 5 条输出里塞两个 Super Model."

#### 2. `_validate_llm_candidates()` 漏 idx 上界校验

只校验 `idx < 0`, 不校验 `idx >= input_size`. 越界 idx 会通过校验, 然后在 `rerank()` 主入口 `if not (0 <= idx < len(top_combos)):` **静默 continue**, 然后 `_enforce_brand_unique()` 用 top_combos 头部按 score 补位. 结果: "LLM 看似输出了 5 条 candidate, 实际部分是规则补位", 质量隐式退化, **N 越大风险越高**.

修复: `_validate_llm_candidates(cands, n_max, input_size=None, n_explore_expected=None)` 新增两个可选参数:
- `input_size`: 传入时校验 `0 <= idx < input_size`, 越界整批 fallback
- `n_explore_expected`: 传入时校验 `sum(is_explore) == n_explore`, 且 exploit 段在前 explore 段在后

加 6 个新测试覆盖这两个新校验项. test_rerank.py 从 24 → 30.

#### 3. 没启用 JSON mode / structured output

代码是 `call_text(prompt)` + `re.search(r"\{.*\}", out, re.DOTALL)` + `json.loads`. 在 N 大 / output 复杂时容易丢字段或 hallucinate. 暂不强制改 JSON mode (Anthropic 直连不支持 OpenAI 风格 response_format), 但 prompt 加严: "不要 markdown 代码块, 不要解释, 不要前缀后缀". Codex 二审指出这是后续 P1 改造项.

#### 4. 重排原则优先级模糊

旧 prompt 把 taste_description / daily_mood / last_feedback 并列, LLM 容易用长期口味覆盖当次意图. 真 Codex 指出外卖场景的正确优先级:

```
1. refine_input (用户当下显式指令, 最高)
2. daily_mood + last_feedback.chips (当下情绪 / 上一顿反馈)
3. taste_description (长期口味, 当 2 信号弱时主导)
4. 健康结构
5. 多样性奖励
```

修复: prompt 重排原则段按此顺序严格降序排列, 写明 "refine_input 不命中的全部降权".

#### 5. explore 缺 few-shot + "中段"定义模糊

旧 prompt 只有 exploit 好/坏 reason 对照, 没有 explore 示例. 而且 "explore 候选 = 打分中段 + 最近未吃" 里 "中段" 没界定. N=60 时 "中段" 指 10-30 还是 30-50?

修复: prompt 加 3 条 explore 好 reason 示例. 加边界规则: "explore 优先从排名 11-N 中选; 必须不违反 hard constraints; 优先最近 3/7 天未吃 cuisine/cooking_method; 如果 daily_mood 很强, explore 也必须服务 mood, 不以新奇牺牲本轮需求."

### N=60 vs N=80/100 (真 Codex 二审定调, 保留 60 默认)

二审用一个关键观察打掉"激进上 N"的论证: `_enforce_brand_unique()` 已经把同 brand 限制到 1 条输出. **top61-80 在 shenzhen-bay 坍缩到 4 brand**, 意味着这段的价值只剩"用同品牌低位变体替换同品牌高位变体". 这条收益路径在 prompt 事实错误未修前 LLM 是盲的; 修了之后理论可达, 但**需要先观测**:

- `selected_idx >= 40` 的比例: 验证 N 涨到 60 是否真在救场
- `selected_idx >= 60` 的比例: 验证是否需要进一步 N=80
- `brand_has_higher_sibling`: LLM 是否真在做同品牌择优

落地: `_log_selection_metrics()` 新函数, `rerank()` 每次打印这三个 metric. 一周后看真实分布再决定要不要进一步上调.

不推荐凭理论可能性直接扩 N=80/100. RankGPT 论文虽然是 GPT-4 时代结论, 但 listwise rerank 输入越大输出不稳定是任务层风险, Sonnet 4.6 的 MRCR/GraphWalks 强是定位检索能力, 不是跨 100 候选的比较排序能力. 不能凭上下文窗口大就乐观.

### 三审增量产物

- `prompts/rerank_system.md`: 大改, 修事实错误 + 重排原则优先级 + 加 explore few-shot + 加格式省略示例
- `chisha/rerank.py:_validate_llm_candidates`: 加 `input_size` + `n_explore_expected` 两个校验参数
- `chisha/rerank.py:_log_selection_metrics`: 新观测埋点
- `chisha/rerank.py:_llm_rerank` + `chisha/debug_recommend.py:_llm_rerank_traced`: 传新校验参数
- `tests/test_rerank.py`: 加 6 个新校验测试 (24 → 30)
- 测试 311 → 317 全过

教训: "假二审" (general-purpose subagent 模拟 Codex 视角) 看不到代码细节里的事实错误 + 校验漏洞, 只能从已知信息推. **真 Codex (codex-cli) 通过实际读代码 + 实测才能发现**: prompt 与代码事实不一致, 校验漏 idx 上界, 没启用 JSON mode. 重大决策建议用真二审 (真 Codex CLI 或独立人审).


---

## D-046.1: L3 精排 max_tokens + json_mode 临时修 (废弃, 被 D-047 取代)

**2026-05-14**

### 背景

D-046 上线后用户拉新代码本地起调试台跑 lunch/want_light, 发现 L3 LLM 精排 fallback. 排查: sonnet-4.6 进入英文 CoT 模式 ("I need to evaluate 40 candidates against..."), 8013 字符 CoT 占满 max_tokens=2048, JSON 没机会输出 → fallback 到 L2 兜底 (final 5 是按 L2 score 排序的伪 LLM 结果, fit_score=2.978 远超 LLM 应输出的 0-1 范围).

### 临时修

第一波尝试: max_tokens 2048→4096, 加 `json_mode=True` 通过 `response_format={"type":"json_object"}` (OR) 或 `output_config.format=json` (Anthropic 直连) 强制 JSON 输出. 又试了 assistant prefill `"{"` 想从结构上断 CoT.

撞了 5 个坑:
1. **prefill 弃用**: Anthropic 在 Sonnet 4.5 / Opus 4.6 后官方弃用 assistant prefill (forced tool_choice + extended thinking 不兼容是同一根因)
2. **OR 协议丢 prefill 语义**: OpenRouter 的 `/v1/chat/completions` 强制 OpenAI 协议 "末尾必须 user", prefill 转发到 Anthropic 时被 strip
3. **OR `response_format` 在 anthropic/* 上是 "accepted but not enforced"**: OR 转发到 Anthropic Messages API 时丢语义 (Anthropic 没有 OpenAI 风格 response_format), 三个 provider (Anthropic/Google/Bedrock) 实测都返回 markdown 包裹的 JSON 而非裸 JSON
4. **debug 路径双份代码漏改**: `chisha/debug_recommend.py:_llm_rerank_traced` 是生产 `_llm_rerank` 的复刻, max_tokens / json_mode 改了一边没改另一边, 卡 1 小时
5. **OR `require_parameters=True` 触发副作用**: 加上后让 sonnet 返回带 markdown 包裹的 JSON, 简单 case 反而变差

撞完后退到 top30 暂稳, 但 want_light 在 top30 仍偶尔 CoT 失控 (3 次跑 1 次 fallback).

### Codex review 第一次

3 BLOCKER + 4 MAJOR + 3 MINOR. 关键洞察:
- json_mode 在 OR 路径不可靠, 需要协议级强约束
- `cache_system=True` 在 OR OpenAI 兼容路径根本失效 (OR 忽略该参数), 之前 D-046 报告的 cache 命中率是错的
- debug/prod 双份代码必须抽 helper 否则永远漂移

### 决策

D-046.1 是过渡期妥协, 不是终态. 进入 D-047 完整重构.

### 沉淀

代码改动 (`chisha/llm_client.py` + `rerank.py` + `debug_recommend.py` + `feedback.py`) 在 D-047 实施时被进一步重构, 不单独保留 D-046.1 commit.

依赖: D-046 (基础链路)


---

## D-047: L3 精排重构 — tool_use forced schema + opus 默认 + top60 + cache_control

**2026-05-14**

### 背景

D-046.1 撞墙后, 用户提了关键反问: "为什么不直接放开 max_tokens 让 LLM CoT 完整跑完?" 回答中辨析出 inline CoT 泄漏 ≠ extended thinking, 决定**完整重构**而不是修补.

四项前置实测 (V1-V4 + V5):

#### V1 — Extended thinking 在 OR + Anthropic 路径可用性

- ✅ `extra_body={"reasoning":{"max_tokens":N}}` 真路由到 thinking 端点
- ✅ `usage.completion_tokens_details.reasoning_tokens` 单独计费
- ⚠️ `tool_choice="required"` + `reasoning` **不兼容** (官方明确, V4 实测 opus+thinking 反而炸正是这个根因)

#### V2 — tool_use forced schema 100% 稳定

sonnet+tool_use no-thinking: 14-33s, $0.04, 100% 输出 5 candidates, 0 CoT 泄漏. 输出干净 JSON 没有任何 markdown 包裹.

#### V3+V4 — top30/60/100 × sonnet/opus 矩阵 (lunch/want_light, 36 次调用 100% 全过)

| Model | TopK | succ | avg_dt | avg_$ | picks 总集 (3 次跑) |
|---|---|---|---|---|---|
| sonnet | 30 | 6/6 | 18s | $0.040 | [0,8,11,13,16,22] |
| sonnet | 60 | 6/6 | 17s | $0.055 | [8,16,22,31,35,55] (新增 [31,35,55]) |
| sonnet | 100 | 6/6 | 21s | $0.078 | [8,16,22,31,35,55,83] (新增 [83]) |
| opus | 30 | 6/6 | 14s | $0.067 | [13,16,18,20,22,24] |
| **opus** | **60** | **6/6** | **15s** | **$0.091** | [2,13,16,18,20,31,55] (新增 [31,55]) |
| opus | 100 | 6/6 | 13s | $0.129 | [13,16,20,31,55,92] (新增 [92]) |

关键发现:
- **top60 真带来多样性增量** (验证 D-046 二审假设): top31-60 段 picks 中 [31,35,55] 等都被 LLM 真实选中, 不是死代码
- **top100 边际收益小**: 比 top60 只多 1 个新候选, 成本 +40% 不值
- **opus 比 sonnet 一致性更高 + 更尊重 taste_description** ([16] 牛腩煲 = "牛肉首选蛋白" 命中, opus 三次跑都放 #1, sonnet 偶尔变)
- opus reason 简洁 30-40 字, sonnet 偏长 54-60 字

#### V5 — tool_use + Anthropic prompt cache 兼容

显式标 `messages[].content[].cache_control: ephemeral` 时 OR 透传到 Anthropic, 二次调用 cached_tokens=3844, cost 省 23%. 之前 D-046.1 用 `cache_system=True` 在 OR 路径根本无效.

### 决策

**主路径**: opus-4.7 + tool_use forced schema + top60 + max_tokens=2048 + cache_control:ephemeral, no thinking.
**Fallback**: opus 故障时降级 sonnet-4.6 + tool_use + top60. **绝不加 thinking** (forced tool_choice 与 extended thinking 不兼容).

理由:
- opus 比 sonnet 贵 65% ($0.091 vs $0.055/次), 但质量优势 (尊重 taste / 一致性 / reason 简洁) + 延迟优势 (14s vs 17s) 值得
- 200 次/月 ≈ $14-18 (cache 命中后), 在用户 OR $30 月限内有 1.5x-2x 缓冲
- chisha 北极星是 7 日采纳率 ≥ 50%, 模型质量直接影响采纳率, 比 token 成本重要

### Codex review 第二次

3 BLOCKER + 4 MAJOR + 3 MINOR, 全部修完:

| 等级 | 项 | 处理 |
|---|---|---|
| BLOCKER | fallback 不能加 thinking | 文档明确禁止 + 实施时未启用 |
| BLOCKER | 缺 stop_reason 断言 | `_run_llm_rerank` 强断言 stop_reason ∈ {tool_use, tool_calls} 否则走 fallback |
| BLOCKER | OR 锁 Anthropic | `_OR_PROVIDER_LOCK = {"order":["Anthropic"], "allow_fallbacks":False}`. **去掉 require_parameters=True**: 实测在 opus-4.7 + tools 上触发 OR "No endpoints found" 404 (OR 路由元数据滞后误判) |
| MAJOR | call_text 全部调用方迁移 | reason.py / feedback.py / debug_recommend.py / scripts/tag_dishes.py 都改取 dict.content; scripts/tag_via_api.py 走独立 client 不动 (D-049+ 候选, D-048 编号已被 L3 双路径收口占用) |
| MAJOR | validate 全部保留 | `_validate_llm_candidates` 完整保留 D-046 二审加的 idx 越界 / explore 数量 / rank 连续 等校验; 加 `_validate_llm_candidates_v` 返回详细错误原因供 trace |
| MAJOR | 抽共享 helper | `chisha/rerank.py:_run_llm_rerank` 同时给 `_llm_rerank` (prod) 和 `_llm_rerank_traced` (debug) 用, 消灭双份代码漂移 |
| MAJOR | 6 case × 3 验证 | 见下方"实施实测" |

### 实施改动

8 个文件 +511/-127 行:
- `chisha/llm_client.py` (+225/-29): `call_text` 加 tools/tool_choice 参数; 返回从 `str` 改 `dict` ({type, content/tool_input, stop_reason, usage, model, raw_text}); OR 路径锁 Anthropic provider; 加 OpenAI/Anthropic tool 格式自动适配 helper
- `chisha/rerank.py` (+261/-37): 抽 `_run_llm_rerank()`; 定义 `_RERANK_TOOL` schema; `L3_INPUT_TOP_K` 30→60; 默认 model `anthropic/claude-opus-4.7`; max_tokens 4096→2048 (足够); 加 `_validate_llm_candidates_v` 返回详细原因
- `chisha/debug_recommend.py` (-76 净减): `_llm_rerank_traced` 改调共享 helper, 删独立 LLM 调用代码
- `chisha/feedback.py` / `chisha/reason.py` / `scripts/tag_dishes.py`: call_text 返回 dict 后取 `.content`
- `prompts/rerank_system.md` (-22 行): 删 "输出格式 (严格)" 整段 (schema 由 tool 自带), 改成"输出方式: 通过 tool select_top_candidates"
- `tests/test_tag_dishes.py`: mock 适配新 dict 返回

### 实施实测 (lunch+dinner × 3 mood × 3 重复 = 18 case)

**17/18 success rate (94.4%)** vs D-046.1 的 67% (want_light 必爆):

| 指标 | D-046.1 | D-047 |
|---|---|---|
| 成功率 | 67% (want_light 必爆) | **94.4% (17/18)** |
| 平均延迟 | 50-80s | **12s** |
| 单次成本 | $0.06 | $0.085 |
| Prompt cache 命中 | 0 (OR 路径失效) | **3748 tokens × 17 = 63k tokens 节省** |
| 总成本 | n/a | **$1.53 / 18 次** |
| 单测 | 317/317 | **316/317** (1 个 pre-existing test_session.py 失败与 D-047 无关) |

唯一 1 次失败 (`dinner/want_soup/run2`): LLM 调了 tool 但 candidates 业务校验失败 (idx/explore/rank 之一). 是 LLM stochastic 输出概率事件, 不是链路 bug. 已加 `_validate_llm_candidates_v` 让下次失败能直接看到具体哪条规则触发.

### 沉淀文档

`docs/L3_RERANK_REDESIGN.md` — 完整方案 + 4 项实测数据 + Codex review BLOCKER/MAJOR 强制条件清单. 后续 L3 改动必读.

### 教训 (跨场景适用)

1. **prompt 软约束敌不过协议级强约束**: "system prompt 写不要 CoT" 在复杂任务下被 sonnet 忽略; tool_use forced schema 才能真阻断
2. **OR ≠ Anthropic 直连**: `cache_system=True` 在 OR OpenAI 兼容路径根本失效, 须显式 `cache_control: ephemeral`. `response_format` 在 OR anthropic/* 路径是 "accepted but not enforced"
3. **debug/prod 双份代码必抽 helper**: D-046.1 漏改 debug 卡 1 小时, D-047 直接抽掉
4. **数据驱动选型**: opus vs sonnet 不要"觉得 opus 更强就选", 用 18 case 矩阵证明 opus 65% 溢价值
5. **OR 路由 metadata 滞后**: `require_parameters=True` 在新模型 + tools 组合上可能误判 404, 要 bisect 出来
6. **"放开 max_tokens 让 CoT 跑完"是错的**: 不是不让 CoT, 而是杀死 inline CoT (inline CoT 跟 output 抢预算 + 不可控), 改用 extended thinking (单独 reasoning channel) 或 tool_use (隐式禁 CoT 输出). 本次因 forced tool_choice + thinking 不兼容, 选 tool_use no-thinking 路径

### 未做 / 推后

- minor m2: 调试台加 fallback 率 / cache 命中率指标 (现在 trace 里有 usage 字段, UI 还没显示)
- D-049+ 候选: `scripts/tag_via_api.py` 走独立 `llm_client_openrouter.py`, 没 tool_use 支持. 批量打标场景需要独立评估是否升级 (D-048 编号已被 L3 双路径收口占用)
- pre-existing `test_session.py::test_cleanup_expired` 失败与 D-047 无关, 单独排查

依赖: D-038 (LLM 抽象 Phase 1), D-046 (基础链路), D-046.1 (废弃临时修)


---

## D-048 — L3 双路径收口: CLI no-tool 分流 + 配置错 hard-fail + trace 结构化

**2026-05-14** · 工程实施 (D-047 Part A + Part B 同日 merge 后的协同补丁)

### 触发 / 背景

D-047 Part A (opus + tool_use forced schema) 与 Part B (Claude Code CLI provider) 是 2026-05-14 同日并行轨道, merge 后 push 到 origin/main. 但 merge 时只在代码层面合流 `llm_client.py` 的 `call_text` 签名, **没解决"CLI 不支持 tool_use 时 L3 怎么办"的协同问题**:

- `rerank.py:_run_llm_rerank` 硬编码 `tools=[_RERANK_TOOL] + tool_choice=_RERANK_TOOL_CHOICE`
- `claude_code_cli.py:217` 收到 tools 抛 `NotImplementedError`
- 外层 `except Exception` 接住, `status=fallback`, 用户以为在跑 L3 LLM 精排, 实际每次都降到 L2 规则兜底
- 测试 `test_run_llm_rerank_falls_back_when_provider_raises_not_implemented` 测的就是这个行为 — 说明 merge 时作者知道这个 gap, 但当作 known state

用户拉取最新代码后发现：默认 auto 路由 = 选 CLI (Max 订阅已登录, ANTHROPIC/OR 没 key) = L3 假装跑 = 实际是 L2. 提出"调试推荐"诉求后才暴露。

### 方案选型

3 个备选 (问用户):
- **A**: 设 ANTHROPIC/OR key, 走真 tool_use (D-047 主路径) — 月成本 ¥20-100
- **B**: 接受 L3 走 L2 兜底 — 失去 L3 价值
- **C**: 改 rerank 让 CLI 走 no-tool json_mode — 复用 Max 订阅, 但回到 D-046.1 "prompt 软约束 67% 成功率"风险

用户选 C, 明确"快透个头可以, 不适合作为默认调试状态".

### 实施 (Codex review 前的第一轮)

#### 1. rerank.py 加 provider 分流

```python
is_cli = (resolved_provider == "claude_code_cli")
if is_cli:
    system_prompt = _patch_system_prompt_for_cli(system_prompt_raw)
    kwargs 不传 tools/tool_choice
else:
    kwargs["tools"] = [_RERANK_TOOL]
    kwargs["tool_choice"] = _RERANK_TOOL_CHOICE
```

调用后:
- CLI 路径: 从 `resp["content"]` / `resp["raw_text"]` 用 `_parse_json_object_from_text` 解析, 跳过 stop_reason tool_use 断言
- 其它 path: 保留 D-047 Part A 的 type+stop_reason 断言

#### 2. `_patch_system_prompt_for_cli` helper

把 `prompts/rerank_system.md` 的 `# 输出方式` 段 (告诉 LLM"调 tool select_top_candidates")替换成"直接输出 JSON 对象, 不要 markdown 包裹". 末尾"现在等待 user 消息, 收到后立刻调 select_top_candidates 返回"替换成"立刻输出 JSON 对象 (无包裹)".

#### 3. `_parse_json_object_from_text` 三层 fallback

1. `json.loads(raw)` 直接解析
2. 提取 ` ```json fence``` ` 内容
3. (Codex MAJOR 2 修过) `json.JSONDecoder.raw_decode` 从每个 `{` 起点扫描, 取首个含 `candidates` 的 dict; 没有则取首个合法 dict 作兜底

#### 4. trace.model 修真实生效值

旧 bug: trace.model 兜底用 `_RERANK_MODEL_BY_PROVIDER[provider]` (CLI 默认 opus), 但 profile.yaml 配 sonnet, trace 显示 opus 而实际跑 sonnet. 修法: 调用前 `_resolve_model` 算预期值 + 调用后用 `llm_response.model` 覆盖为 provider 真实报告值。

### Codex review (独立第三方)

发起命令: `Skill(codex:rescue)` → `Agent(codex:codex-rescue)`. Codex 用 `gpt-5.3` 独立读 rerank.py / llm_client.py / llm_providers/ / profile.yaml / tests/. 输出: 1 BLOCKER + 5 MAJOR + 2 MINOR + 架构判断.

#### Codex BLOCKER 1: 配置错误被静默吞

`_run_llm_rerank` 外层 `except Exception` 把 `_resolve_provider` 抛的 ValueError/RuntimeError 也吞成普通 fallback, **静默返回 L2 结果**. 用户改 `profile.yaml llm.provider: openrouter` 但配错 (未知名/缺 key) 时, 系统不报错, 只是悄悄降级. 与 docs/DECISIONS.md D-047 Part B 决策 "不能 silent fallback" 冲突。

**修法**: `_resolve_provider` 抛错时**立刻 return** `status="config_error"` + `config_error=True` + `resolved_provider=None` + `fallback_reason="LLM provider 配置错误: <exception>"`. 不让外层 except 接到. 上游 `_llm_rerank` (prod) 看到 `config_error` 打 ERROR 级 stderr 区别于普通 fallback.

#### Codex MAJOR (5 项, 全修)

| MAJOR | 问题 | 修法 |
|---|---|---|
| 1 | CLI max_tokens 是假保护 | 注释明确 max_tokens 在 CLI 不生效, 真兜底是 timeout_sec=180s, claude -p 没 cap 协议参数 |
| 2 | parser 第三层 fallback "首 { 到末 }" 在 CoT 含无关 `{}` 时拼入垃圾 | 改用 `json.JSONDecoder.raw_decode` 从每个 `{` 扫, 优先取含 'candidates' 的 dict |
| 3 | `_patch_system_prompt_for_cli` 未命中目标段时静默放过 | 找不到 `# 输出方式` 段 / 找不到末尾 select_top_candidates 文案时显式 ValueError |
| 4 | profile.yaml 默认 claude_code_cli=sonnet 与 D-047 Part A "主路径 opus" 决策表面冲突 | profile.yaml + rerank.py 加详细注释说明双路径定位 (CLI=自用降级 / API+OR=主路径) |
| 5 | OR 对 forced tool_call 可能返回 finish_reason="stop", 现有断言 `stop in {tool_use, tool_calls}` 会误判 | 改用 `type=="tool_use" + tool_name` 强约束, stop_reason 仅 debug 提示 |

#### Codex MINOR (2 项, 全修)

| MINOR | 问题 | 修法 |
|---|---|---|
| 1 | trace 缺结构化字段 | 加 `status` (ok/fallback/config_error) / `config_error` / `resolved_provider`. debug_recommend.py 透传到 trace.l3_rerank.llm |
| 2 | parser 测试不能证明真实输出场景鲁棒 | 加 4 个边界测试: 无关 dict 在前 / 截断 JSON / 多 dict 选 candidates / fence 后附 explainer |

### 实施实测 (Codex 修后)

| 场景 | status | provider | model | latency | cost | candidates |
|---|---|---|---|---|---|---|
| CLI (auto + Max 订阅, sonnet effort=low) | ok | claude_code_cli | sonnet | 43s (首次) / 50s (cache 命中后再跑) | $0.091 (首次 cache write) → $0.048 (二次 cache hit) | 5/5 |
| OR + tool_use (sonnet-4.6) | ok | openrouter | anthropic/claude-sonnet-4.6 | 28s | $0.059 | 5/5 |
| `CHISHA_LLM_PROVIDER=foo_invalid` | **config_error** | None | None | None (根本没调 LLM) | — | 0 + 规则 fallback 保管道不断 |

测试: 381 passed, 1 failed (pre-existing test_session::test_cleanup_expired 与 D-048 无关). 新增 13 个测试: 5 个 CLI 分流相关 / 2 个 config_error / 3 个 prompt patch / 4 个 parser 边界 / 1 个旧 NotImplementedError 测试改名.

### 关键文件改动

8 个文件 +446 / -42 行:
- `chisha/rerank.py` (+159/-23): is_cli 分流 + _patch_system_prompt_for_cli + _parse_json_object_from_text + config_error hard-fail + trace.model 真实值
- `chisha/llm_providers/claude_code_cli.py` (+8/-2): max_tokens 注释明确不生效
- `chisha/llm_providers/openrouter.py` (+4/-1): stop_reason 语义注释
- `chisha/debug_recommend.py` (+5/-1): trace 透传 status/config_error/resolved_provider
- `profile.yaml` (+19/-3): 双路径注释 + 主路径/自用降级定位
- `tests/test_rerank.py` (+196/-13): 13 个新测试
- `docs/DECISIONS.md` (+45/0): D-048 stub
- `docs/IMPLEMENTATION_LOG.md` (+本段): 详细实施

### 教训 (跨场景适用, 接 D-047 教训续)

7. **同日并行轨道 merge 必须做协同 review**: D-047 Part A 用 tool_use, Part B 加的 CLI provider 不支持 tool_use, merge 时只测了两边各自的代码冲突, 没测"A 的硬编码 tool_use 撞上 B 的 NotImplementedError"的真实链路. 协同 gap 写进了测试 (`test_falls_back_when_provider_raises_not_implemented`), 但当作 "known limitation" 没人挑战, 直到用户拉取代码尝试调试才暴露。教训: merge 同日并行改动后**必须跑一次端到端真实链路**, 不能光看单测和代码冲突。
8. **静默 fallback 是 chisha 的反复犯错点**: D-047 Part B 决策就写了"不能 silent fallback", D-048 又被 Codex 抓到一次同样的坑. 配置错误 (用户输入错) 和运行时错误 (LLM 调用失败) 必须分开处理 — 配置错 hard-fail 给清晰错误, 运行时错 fallback 保管道. 通用且强约束。
9. **AI 自己 review 的盲点**: D-047 Part A merge 完, 自己跑过测试 (含那个 NotImplementedError fallback 测试) 还自我感觉良好. 直到 Codex 独立读才看出"配置错被吞 = silent fallback 反模式". 教训: 凡是有"系统看似正常但实际跑错"风险的改动, 必须 Codex / 独立第三方 review, 不能只靠自检.

依赖: D-038 (LLM 抽象 Phase 1), D-047 Part A (tool_use schema), D-047 Part B (LLM Provider 抽象)
