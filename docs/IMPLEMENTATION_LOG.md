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
| [D-048.1](#d-0481--l3-精排-prompt-清理-工程注释移除--few-shot-修冲突--user-message-字段渲染统一) | L3 prompt 可读性清理 + few-shot 修硬约束冲突 | — |

| [D-051 执行](#d-051-执行记录--web-用户视图-v1-落地-appsweb) | apps/web V1 SPA 落地 (Vite+React+TS) | [DECISIONS#D-051](DECISIONS.md#d-051--web-优先-飞书降级为推送通道) |
| [D-056~D-068 执行](#d-056d-068-执行记录--v11-反馈系统落地-appsweb) | V1.1 反馈系统 (form/detail/inbox/banner stack/snooze-stop) | [DECISIONS#D-056~D-068](DECISIONS.md#d-056-navbar-加反馈-tab--角标-v11) |

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

#### 1. System prompt 事实错误 (严重) — **部分 superseded by D-049**

> ⚠️ D-049 (2026-05-14) 后: `apply_caps()` 改 head-only, top60 不再含 tail 段同品牌变体, 实际同品牌至多 2 条. 下文"6-8 次"的实测背景作废; prompt 已同步改成"至多 2 条变体, 在这 2 条里挑菜品组合". 但 #2 ~ #5 仍然有效.

之前 prompt 写: "L2 已做品牌/餐厅/菜系/形态多层 cap, 输入里不会有同店重复 combo (同一 brand 至多 1 条). 你不必再做去重."

**实测核对** (D-049 前): shenzhen-bay top60 里 Super Model 出现 **8 次**, 21 个 brand 重复 ≥2 次. 真实 brand cap=2 (D-045), 但 `apply_caps()` 返回 `head + tail`, top60 包含大量 tail 段同品牌变体.

LLM 读了这句话会以为输入已去重, **不会尝试同品牌内部择优**. 实际上输入有大量同 brand 候选, LLM 应该知道可以挑最贴情境的那条 (例如 Super Model 8 个变体里选蛋白最足 / 油最低 / 与 daily_mood 最对的那条).

修复 (D-049 前): prompt 改成 "**输入里仍可能含同品牌、同餐厅的多个变体**(例如 Super Model 可能出现 6-8 次). 你的工作之一就是在同品牌变体中选最贴合当下情境的那一条. 最终输出阶段系统会再做一次品牌去重兜底, 同 brand 最多保留 1 条, 所以你也不需要在 5 条输出里塞两个 Super Model."

D-049 后 prompt 进一步收紧: 既然 L2 输入已 brand cap=2 真生效, LLM 不需要在 6-8 个变体中择优, 只在 ≤2 个变体里挑菜品组合即可. 同品牌不同分店哪家更近由用户自决。

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

---

## D-048.1 — L3 精排 prompt 清理: 工程注释移除 + few-shot 修冲突 + user message 字段渲染统一

**2026-05-14** · 工程实施 (D-048 后续 prompt-only 清理, 无 schema/链路改动)

### 触发

用户作为「人」读 `prompts/rerank_system.md` 时主观感觉"工程注释泄漏、目标埋得深、中英文穿插", 提出和 Codex 作为「大模型 / agent 开发专家」一起 review。

### 联合 review (Claude + Codex 各自独立读)

发起命令: `Skill(codex:rescue)` → `Agent(codex:codex-rescue)`. Codex 用 `gpt-5.3-codex` 独立读 `prompts/rerank_system.md` + `rerank.py:build_user_message` + 相关 helper. 输出 ≤600 字的 A/B/C/D 报告。

#### 共识发现 (Claude + Codex 都识别)

| # | 问题 | 影响 |
|---|---|---|
| 1 | 工程元注释泄漏: `D-046, D-047 改 tool_use 强制 schema` / `稳态部分 — 进 Anthropic prompt cache` / `L1 召回 + L2 打分（含品牌/餐厅/菜系/形态四层去重 cap）` / `系统会再做一次品牌去重兜底` / `你算了也会被覆盖` 共 6 处, 整段进 cache 喂给 LLM | 占 KV cache, 注意力分配错; "兜底"语气还会鼓励 LLM 放松约束 |
| 2 | 目标被格式说明淹没 (任务陈述在第 4 行, 但格式速查+读法占到第 39 行才到排序原则) | LLM 注意力被前置的字段表稀释 |
| 3 | 工程性硬约束 (explore-last / combo_index 不重复) 必须留 system, schema 只管类型不够 | 保留 |

#### Codex 独有发现 (Claude 漏的, 高价值)

| # | 问题 | 影响 |
|---|---|---|
| A | few-shot 与硬约束直接冲突: `蒸贝贝南瓜｜纯素·蒸·油1·甜1` 显式写 `甜1`, 但 `_fmt_dish_line:297` 是 `sweet >= 2` 才显示, **代码实际不会产出 `甜1`** → 教 LLM 错误的格式直觉 | LLM 可能基于示例反推"原来 0-1 也会出现", 误判输入 |
| B | `麻婆豆腐｜豆制品·炒·油3·辣4·甜2·processed｜role=主菜｜18` 示例同时有 `processed` + `role=主菜`, **直接违反第 53 行硬约束"主菜带 processed 丢弃"** → few-shot 在教违规组合 | LLM 学到"main 菜带 processed 是合法格式", 可能不丢弃 |
| C | 段标签错配: prompt 写 `[PROFILE+CONTEXT]` 是合并段, 但 `_profile_block` / `_context_block` 实际拼成独立的 `[PROFILE]` 和 `[CONTEXT]` 两段 | LLM 找字段时按错的 section 名查 |

#### Claude 独有发现

| # | 问题 | 影响 |
|---|---|---|
| D | 读法示例价格精度 `¥18` vs 代码实际 `f"{price:.1f}"` 输出 `18.0` | 小, 但示例对齐代码行为更可信 |
| E | `_profile_block` 空集合渲染成 Python `repr`: `喜欢: []` / `avoid: []` 像代码残留 | 跟 system prompt `(无)/(空)/未写即 false` 系列风格不一致 |
| F | `_context_block` 最近 3 天 cuisine 渲染成 Python dict repr `{'川菜': 3, '日料': 1}` (单引号风) | LLM 能解析, 但 `川菜×3 日料×1` 更紧凑、更符合中文 prompt 风格 |

#### 不动 (评估过但 churn > 收益)

- `int(dist_m)/1000` 在 `_fmt_combo_block:326` 是真 bug (2150m 显示 2.0km 而非 2.1km), 但属数值精度而非 prompt 优化, 应单独修
- `?` 缺失占位 / `心情` vs `daily_mood` 中英映射: LLM 上下文足够推断, 改了 churn 不划算

### 修改

#### system prompt (`prompts/rerank_system.md`)

- **顶部 HTML 注释**只保留 CLI patch 锚点警告 (`# 输出方式` 标题 + 文末 `select_top_candidates + 现在等待` 行是 `_patch_system_prompt_for_cli` 的锚点), 其它工程元信息全删
- 任务陈述前置到第 1 行
- 删 "L1 召回 + L2 打分" / "系统会兜底" / "你算了也会被覆盖" / D-046, D-047 编号
- 字段说明从散文 + bullet 改成表格
- few-shot 修冲突:
  - `蒸贝贝南瓜｜...·甜1` → `蒸贝贝南瓜｜纯素·蒸·油1` (跟 sweet >= 2 才显示的代码一致)
  - `麻婆豆腐｜...processed｜role=主菜` → `腊肠｜红肉·炒·油3·processed｜8.0` (配菜默认省略, 不踩硬约束)
- 价格示例 `¥18` → `¥18.0` 对齐 `:.1f`
- 结构重排: 任务 → 硬约束 → 重排原则 → 输入速查 → 输出协议 → reason 示范 → 边界
- 长度: 6538 → 5784 字符 (-12%)。重点不是压 token, 是注意力 focus

#### user message helper (`rerank.py`)

新增两个小 helper, 统一 fallback 风格:

```python
def _fmt_list_or_none(xs) -> str:
    """空 → '(无)', 否则空格分隔. 替代 Python '[]' repr."""

def _fmt_counts_or_none(d) -> str:
    """空 → '(空)', 否则 'key×N key×N'. 替代 Python dict repr."""
```

`_profile_block` / `_context_block` 用上后, user message 输出变化示例:

```
# 改前
喜欢: ['粤菜', '潮汕']
不喜欢: []
最近 3 天 cuisine: {'川菜': 3, '日料': 1}

# 改后
喜欢: 粤菜 潮汕
不喜欢: (无)
最近 3 天 cuisine: 川菜×3 日料×1
```

#### sample (`prompts/rerank_user.md`)

跟代码实际输出对齐:
- `[PROFILE]` / `[CONTEXT]` 用实际数据示例而非 `{占位符}`, 方便人对照
- `黑米饭｜主食·煮·油1·grain=糙米杂粮` 修成 `黑米饭｜主食·煮·油1｜role=主食·grain=糙米杂粮` (代码 seg2 含 role+grain, 不是 seg1)

### 测试

- 45 个 rerank 单测全过 (含 3 个 patch 锚点测试 + 1 个 sanity test 验证当前 prompt 能被 CLI patch)
- 全量 382 passed / 1 failed (`test_cleanup_expired` 是 pre-existing session TTL 日期边界问题, 跟 prompt 无关)

### 关键文件改动

5 个文件:
- `prompts/rerank_system.md`: 整体重写, 工程注释隔离到顶部 HTML 注释, 结构重排, few-shot 修冲突
- `prompts/rerank_user.md`: sample 用实际数据替代占位符, 字段格式对齐代码
- `chisha/rerank.py`: 加 `_fmt_list_or_none` / `_fmt_counts_or_none` 两个 helper, 替换 `_profile_block` / `_context_block` 里的 Python repr
- `docs/IMPLEMENTATION_LOG.md`: 本段

### 教训 (跨场景适用)

10. **prompt 文件里的 `# 注释` 不是注释**: markdown 文件没有真正的"不进 LLM 视野"机制. `# 标题` 是给 LLM 看的, `<!-- HTML -->` 虽然 LLM 看得见但会被理解为 dev note 而忽略。给开发者的工程元信息要么写到代码侧 docstring, 要么显式 HTML 注释明确"dev note", 不能写成 `# xxx` 当成自己看不到。
11. **few-shot 必须自洽**: few-shot 是 LLM 学得最快的部分, 如果示例和硬约束冲突, LLM 会优先信示例而非规则。每次改硬约束后必须扫一遍 few-shot 看有没有反例, 反之亦然。
12. **跨 AI review 比单 AI 自检高一个数量级**: D-048 已经验证过一次"Codex 抓到 Claude 漏的 BLOCKER", D-048.1 又验证一次 (Codex 独立抓到 few-shot 与硬约束直接冲突这种"自己写的自己看不出"的盲区)。教训: prompt / 关键系统改动前**默认开 Codex 第三方独立 review**, 不只是"觉得复杂时才开"。
13. **重命名优化目标**: 一开始想着"删工程注释让 prompt 更干净", 但真正高价值的不是删字数 (-12% 收益小), 而是修 few-shot 冲突 + 修标签错配 (这才是会真实影响 LLM 输出的)。下次做 prompt 优化先按"会不会改变 LLM 输出"排序, 不按主观可读性排。

依赖: D-046 (L3 prompt 拆 system/user), D-047 (tool_use forced schema), D-048 (CLI no-tool 分流 + patch 锚点)


## D-050 — CLI 精排 opus 默认切换 + retry-with-feedback 落地

**2026-05-15** · 工程实施 (D-050 决策对应执行记录)

### 触发

用户主观要求"CLI 路径默认 model 升 opus 4.7" (D-047 V4 矩阵已证 opus 选菜质量明显优于 sonnet). 切换两行:
- `chisha/llm_providers/claude_code_cli.py:25` `_DEFAULT_MODEL = "sonnet"` → `"opus"`
- `profile.yaml` `llm.model.claude_code_cli: sonnet` → `opus`

### 失败模式发现

切换后第一次 `dry_run --n 5 --meal both` (10 session) 出现 2/10 fallback:

```
[rerank] explore 数量错误: 期望 2, 实际 1
[rerank fallback] candidates 业务校验失败: explore 数量 1 != 期望 2
```

加临时 debug 打印 `out["llm_response"]["content"]` 后 root cause 清楚: **opus 主动放弃第二个 explore 槽**。两次失败 raw 都是相同 pattern:

```json
{"candidates":[
  {"rank":1, "is_explore":false, "combo_index":3,  ...},   // 0-9 band
  {"rank":2, "is_explore":false, "combo_index":14, ...},   // 10-19 band
  {"rank":3, "is_explore":false, "combo_index":2,  ...},   // 0-9 band
  {"rank":4, "is_explore":false, "combo_index":1,  ...},   // 0-9 band ← 应该是 explore 但 opus 给了 exploit
  {"rank":5, "is_explore":true,  "combo_index":31, ...}    // 30-39 band
]}
```

opus 判断"4 高质量 exploit + 1 explore 比 3 高质量 + 2 次优 mid-band explore 体验更好"。sonnet 没这倾向是因为 sonnet 倾向无脑遵守 prompt 字面计数。

### 第一轮修法尝试 (失败, 撤回)

加强 prompt 计数约束: 在 `# 输出方式` 段顶部加"计数硬约束(最高优先级)"小节, 同步改边界两条软指令. 同时把硬约束塞进 CLI patch 后的 `_CLI_OUTPUT_SECTION`。

**第二次 dry_run: 10/10 fallback** (vs 修前 2/10), 商家分布 5 家 × 10 sessions = 全部规则 fallback. 还出现新错: `[rerank] LLM 返回 6 > n_max=5, 截断`。

opus 看到更严厉的计数指令后, 行为反而更乱 —— 既不愿减少高分 exploit, 又被迫满足"explore=2", 结果给 6 条。**加重 prompt 反向恶化**。

撤掉 CLI patch 段的硬约束 (`_CLI_OUTPUT_SECTION` 恢复精简版), 主路径 tool_use 段的硬约束保留 (那条路径走 forced schema 不会出现这个问题, 但留着对未来调试有价值)。

### 第二轮修法 (落地)

改思路: prompt 软约束打不过 opus 的全局优化倾向, 改用**机械纠错**.

在 `_run_llm_rerank` 里 CLI 路径校验失败时, 用关键字 (`"explore 数量"` / `"n_max"` / `"数量"` / `"返回"`) 匹配 detail 决定是否 retry, 构造 correction prefix append 到 user_msg 再调一次 LLM。

**初版 dry_run 实测 10/10 成功** (其中 1 session 走 retry), retry 延迟 ~12s + 单次成本 ~$0.03 (合计 ~24s / ~$0.06)。

### 联合 Codex review

按 D-048 / D-048.1 流程发起跨 AI review (`Agent(codex-rescue)`). Codex 用 gpt-5.3-codex 独立读 diff + 现存 docs/DECISIONS.md D-047 / D-048 背景, 输出五问 (Q1 retry 是否合适 / Q2 关键字匹配是否 robust / Q3 correction prefix 设计 / Q4 opus 默认是否好决定 / Q5 根本避坑思路)。

#### 共识 / 接受的反馈

| Q | Codex 意见 | 落地 |
|---|---|---|
| Q1 | retry 是合适方案, 但**(c) 代码确定性 demote 不可取** —— 把高分 exploit 改成 is_explore=true 会破坏 `one_line_reason` 语义 + 违反"explore 来自 idx≥10"规则 | 不动这块 |
| Q2 | 关键字匹配脆弱, 文案改动会静默漏触发. **validator 应返回结构化 error_code** | 落地: `RerankValidationCode` 类 + `_validate_llm_candidates_v` / `_diagnose_candidates` 改三元组返回 + `_RETRY_TRIGGER_CODES` allowlist |
| Q3 | correction prefix 没说"其余规则仍生效", retry 时可能让 opus 降为"只满足计数, 忽略 taste/health/avoid". **不要贴上次错误 JSON** (会锁死在错误选择) | 落地: prefix 加一句"**系统 prompt 里所有其余规则全部仍然生效, 基于原 CANDIDATES 重新挑, 不是改标签**"; 不贴 JSON |
| Q4 | opus 默认在自用边界内 OK, 但生产应强走 tool_use 主路径 | 无新动作 (D-048 已定位 CLI = 自用); 注释强化 |
| Q5 | CLI = best-effort 自用通道, 不该承载生产级精排. 结构化任务永远走 tool_use | 落地: retry 块开头加注释强化 D-048 边界 |

#### 我自己发现 Codex 没提的小问题

- `out["latency_ms"]` 累加 retry 延迟会让 trace 字段含义漂移 (原本是单次, 累加后变成总时长). 改成 `retry_latency_ms` 独立字段, `latency_ms` 保留首次调用原值。

### 结构化 error code 落地细节

```python
class RerankValidationCode:
    OK = "OK"
    NOT_LIST = "NOT_LIST"
    EMPTY = "EMPTY"
    OVER_N_MAX = "OVER_N_MAX"               # retry-trigger
    ITEM_NOT_DICT = "ITEM_NOT_DICT"
    MISSING_FIELDS = "MISSING_FIELDS"
    INVALID_INDEX = "INVALID_INDEX"
    INDEX_OUT_OF_RANGE = "INDEX_OUT_OF_RANGE"
    INDEX_DUPLICATE = "INDEX_DUPLICATE"
    INVALID_FIT_SCORE = "INVALID_FIT_SCORE"
    INVALID_TASTE_MATCH = "INVALID_TASTE_MATCH"
    INVALID_IS_EXPLORE = "INVALID_IS_EXPLORE"
    INVALID_RISK_FLAGS = "INVALID_RISK_FLAGS"
    RANK_NOT_SEQUENTIAL = "RANK_NOT_SEQUENTIAL"
    EXPLORE_COUNT_MISMATCH = "EXPLORE_COUNT_MISMATCH"  # retry-trigger
    EXPLORE_POSITION_WRONG = "EXPLORE_POSITION_WRONG"  # retry-trigger
    UNKNOWN = "UNKNOWN"

_RETRY_TRIGGER_CODES = frozenset({
    RerankValidationCode.OVER_N_MAX,
    RerankValidationCode.EXPLORE_COUNT_MISMATCH,
    RerankValidationCode.EXPLORE_POSITION_WRONG,
})
```

不 retry 的 case (format / index / value 错): opus 重答也不会变好, 直接 fallback 省 12s + $0.03。

### dry_run 最终实测 (Codex 推荐方案全量落地后)

- `dry_run --n 5 --meal both` (10 session): 10/10 成功, 0 retry, band 分布健康 (`[0-9, 10-19, 30-39, 20-29, 40-59]` 等)
- `dry_run --n 10 --meal both` (20 session): 20/20 成功, 0 retry
- 商家分布 12+ 家 (vs 修前规则 fallback 退化到 5 家)
- 单次 12-15s / $0.03; retry 触发时 ~24s / $0.06
- 测试: `tests/test_rerank.py` 45 全过 + 全量 381 passed (1 pre-existing flaky `test_cleanup_expired` 跟改动无关)

### 关键文件改动

- `chisha/rerank.py`:
  - 加 `RerankValidationCode` 类 + `_RETRY_TRIGGER_CODES` allowlist
  - `_validate_llm_candidates_v` / `_diagnose_candidates` 改三元组 `(cands, code, detail)` 返回
  - `_run_llm_rerank` 加 CLI retry 块 (~50 行): code 路由 + correction prefix 构造 + 第二次调用 + 二次校验
  - `out["fallback_reason"]` 格式改 `candidates 业务校验失败 [<CODE>]: <detail>`
  - trace 加 `retry_attempted` / `retry_succeeded` / `retry_first_failure_code` / `retry_latency_ms` / `llm_response_retry`
- `chisha/llm_providers/claude_code_cli.py`: `_DEFAULT_MODEL` sonnet → opus
- `profile.yaml`: `llm.model.claude_code_cli` sonnet → opus + 注释更新理由
- `prompts/rerank_system.md`: `# 输出方式` 段顶部加"计数硬约束"小节; 边界小节澄清"候选不足"语义 (主路径 tool_use 用; CLI patch 路径整段替换故不生效, 留着对未来切回主路径或调试有价值)

### 教训 (跨场景适用)

14. **opus vs sonnet 失败模式截然不同, model 切换不是无成本**: opus 在多目标权衡上更"全局优化", 会主动违反字面 prompt 指令换更好的整体结果; sonnet 倾向字面遵守 prompt. 切 model 必须重新跑 dry_run 覆盖关键失败维度, 不能假定"更贵的模型一定不坏"。

15. **prompt 软约束打不过 LLM 全局优化倾向时, 改机械纠错 (validate→retry→fallback) 而非加重 prompt**: 第一轮"加硬约束"反向恶化是这次最有教育意义的踩坑 —— 当 opus 已经看见计数指令但仍主动违反, 再加严厉只会让它行为更不稳。这种情况只能在代码层做闭环。

16. **validator 错误描述要给"机器路由用的 code" + "人看的 detail" 两份**: 字符串匹配 fallback_reason 决定 retry 触发条件是典型 anti-pattern (Codex Q2 抓出来的). 任何"上层根据下层错误信息做决策"的场景都该用稳定 enum, 不该解析人类可读文案。

17. **跨 AI review 的 ROI 再次验证**: 这次 Codex Q2 抓的 "validator 应返回 error_code" 是 Claude 自己写完测试通过后没看出的 robustness 问题. D-048.1 教训 12 (默认开 Codex review) 在 D-050 又生效一次。

依赖: D-047 (provider 抽象 + tool_use forced schema 17/18), D-048 (CLI 分流 + status 三态 + Codex review 流程), D-048.1 (prompt 清理 + 跨 AI review 教训), D-050 (本条对应的架构决策)

## D-051 执行记录 · Web 用户视图 V1 落地 (apps/web)

**2026-05-15** · 实施细节，决策见 [DECISIONS D-051](DECISIONS.md#d-051) + D-052~D-055

### 输入

- `claude.ai/design` 协同产出的 V0 原型（13 文件，CDN+Babel 单页）解压后位于 `chisha-user.zip`
- `DESIGN_NOTES.md` 沉淀了 4 条新决策（§8.2 → D-052~D-055）+ 文案规范 + 视觉系统

### 工程动作

1. **新建 `apps/web/`** monorepo 子项目：
   - Vite 5 + React 18.3 + TypeScript 5 + React Router 6 + Tailwind 3
   - `npm run dev` (5173) / `npm run build` / `npm run typecheck`
   - `vite.config.ts` 配 `/api` 反代到 127.0.0.1:8765（debug_server）
   - `VITE_USE_MOCK=1`（默认）走 `src/lib/mockApi.ts`，`=0` 走真接口
2. **lib 分层**：
   - `types.ts` 镜像后端 schema（Candidate / RecommendResponse / Profile 等）
   - `labels.ts` ← `labels.js` 一对一翻译，保持 mapping 接口不变
   - `api.ts` 真接口骨架（jget/jpost）+ dispatcher，符合 `ChishaApi` 接口
   - `mockApi.ts` ← `data.js`：13 条候选池 / pickFive / session store / 900ms 模拟延迟
   - `profileDefaults.ts` ← `profile-defaults.js`
   - `yaml.ts` ← components.jsx 的 toYaml（用于 ProfilePage 只读视图）
   - `useChishaState.tsx` 把原型 App.jsx 的 home/unfed/toast 状态搬到 React Context
3. **组件分层**（每个文件一组件，对照原型 components.jsx 拆开）：
   - atoms / NavBar / StatusBar / PendingFeedbackBanner / RefineCrumb / RefineInput / RecCard(+Skeleton) / PickedConfirmation / SkipMealAction(+SkippedState) / DetailPanel / YamlViewer / Toast / PageShell(+FooterBar)
   - profile 子目录: Inputs（Field/FieldGroup/TextInput/NumberInput/Slider/Toggle/Select）+ ChipListEditor
   - **没搬** tweaks-panel.jsx — host-only 协议代码，正式工程不需要
4. **页面**：HomePage / ProfilePage / HistoryPage 全量；**FeedbackPlaceholderPage / FeedbackLastResolverPage** 保留路由可达但显示 placeholder，按用户备注"反馈页设计迭代中"暂不落 form。`PendingFeedbackBanner` 仍能导航过去。
5. **路由**: `HashRouter` (localhost 单文件部署最稳，匹配原型行为)。详细路径表见 `apps/web/README.md`。

### 验证

```bash
$ npm install         # 137 packages, 32s
$ npm run typecheck   # 0 error
$ npm run build       # ✓ built in 561ms · 60 modules · 235kB / 74kB gzip
$ npm run dev         # vite v5.4.21 ready in 119 ms
```

### 边界处理 / 已知后续

- `Select<T>` 范型容错：profile.llm.provider 用 `Select<typeof local.llm.provider>` 让 TS 把 `string[]` 收敛到联合类型
- `mockApi.recommend / refine` 显式带参数类型注解，否则 `ChishaApi` 接口的 contextual type 在 destructuring defaults 下会丢失（修过一次 typecheck 报错）
- 反馈页 form 待用户视图设计定稿后补；目前 `/api/feedback` 端点契约在 `api.md` 标 placeholder
- 后端 FastAPI 还没装 `/api/recommend` 等 V1 端点（debug_server 现只有 `/api/debug_recommend`），默认 mock 模式可用；端点接入是下一个 PR

### 反 anti-pattern

- 没把 V0 的 `<script type="text/babel">` CDN 路径搬过来 — 正式工程必须走 bundler（信息密度审美 ≠ 开发环境凑合）
- 没把 tweaks-panel.jsx 搬过来 — 它是 claude.ai/design 沙盒的 host 协议代码，正式 Vite 用不到
- 没创建"反馈页 V1 简版"占位 form — 用户明确说 "先跳过这部分"，硬上等于让"未定稿的 UI" 立刻产生历史包袱

---

## D-056~D-068 执行记录 · V1.1 反馈系统落地 (apps/web)

**2026-05-15** · 实施细节, 决策见 [DECISIONS D-056~D-068](DECISIONS.md#d-056)

### 输入

- 设计交付物: `chisha-user (1)/` (claude.ai/design 沉淀, 含 5 个 feedback 变体原型 + DESIGN_NOTES.md §10 V1.1 决策)
- handoff: `chisha-user (1)/CLAUDE_CODE_HANDOFF_feedback.md` (任务范围 + 反模式 + 验收 user journey)
- 决策落地: D-056~D-068 (DECISIONS.md 新加)

### 实施范围

只增量加反馈模块到既有 `apps/web/` 工程; 主页 / refine / accept / 偏好 / 历史 不重做; history-page 行可点击是跨页面联动。

### 文件改动

**新增 (4 文件)**:
- `apps/web/src/components/feedback/atoms.tsx` — 共享 `ProteinPred` / `OilPred` / `clipReason` / `relAgo` / `buildDimRows`
- `apps/web/src/components/feedback/ProgressiveForm.tsx` — E 渐进披露表单 (D-062 + D-065)
- `apps/web/src/components/feedback/FeedbackDetailView.tsx` — 已反馈 readonly snapshot + append timeline (D-066 + D-067)
- `apps/web/src/pages/FeedbackInbox.tsx` — `/feedback` 反馈中心三段 (D-058)
- `apps/web/src/pages/FeedbackPage.tsx` — `/feedback/:id` 双态分支 (form / detail)

**改写 (8 文件)**:
- `apps/web/src/lib/types.ts` — `FeedbackPayload` 新 schema; 新 `FeedbackRecord` / `FeedbackComment` / `RecentFeedback`; `UnfedSession` 加 `summary` / `snoozed` / `stopped` 字段
- `apps/web/src/lib/labels.ts` — 加 `fbE*` / `fbDetail*` / `inbox*` / `bannerStack*` / `navFeedback` 等; 砍 `fbStarTaste` / `fbStarSat` / `feedbackChips` / `fbWip`
- `apps/web/src/lib/api.ts` — `ChishaApi` 接口换签名: 砍 `lastUnfed` / `dismissFeedbackBanner`; 加 `inbox` / `snoozeFeedback` / `stopFeedback` / `recentFeedbacks` / `getFeedback` / `appendFeedbackComment`
- `apps/web/src/lib/mockApi.ts` — STORE.acceptedQueue 字段升级 (`snoozed_until` / `stopped`); STORE.feedbacks 改为 `FeedbackRecord` 含 `comments[]`; 7 个新端点实现 + 砍掉 lastUnfed / dismissBanner
- `apps/web/src/lib/useChishaState.tsx` — context 从 `unfed: UnfedSession | null` 改为 `inbox: UnfedSession[]`; `refreshUnfed` → `refreshInbox`
- `apps/web/src/components/NavBar.tsx` — 加「反馈」tab + 角标 (D-056)
- `apps/web/src/components/PendingFeedbackBanner.tsx` — slim banner 全量改写为 stack variant (D-057): metadata 行 + ⋯ 菜单 + 主卡 + footer 多条提示
- `apps/web/src/App.tsx` — 路由加 `/feedback` (`FeedbackInbox`); `/feedback/:id` 改用 `FeedbackPage` (替代 placeholder); 接 `refreshInbox`
- `apps/web/src/pages/HomePage.tsx` — banner 调用签名换为 `unfedList` 数组 + `onSnooze` / `onStop` / `onOpenInbox`
- `apps/web/src/pages/HistoryPage.tsx` — 每行可点击 + 未反馈紫 chip + 已反馈 gut chip + 跳过餐 dead row (D-059)

**删除 (1 文件)**:
- `apps/web/src/pages/FeedbackPlaceholder.tsx` — 被 FeedbackPage 取代

### Schema 关键变更

**`FeedbackPayload` (V1 → V1.1)**:
- 砍 `rating_taste: number` / `rating_satisfaction: number` / `chips: string[]`
- 加 `rating: -1 | 0 | 1 | null` (gut, D-064)
- 加 `reason_match` / `fullness` / `oil_calibration` / `repurchase_intent: 0 | 1 | 2 | null` (4 维 calibration/behavior, D-065)
- 加 `variant: "progressive" | "not-eaten"` (D-068 砍掉了 minimal/dimensions/conversational/retro 4 个备选)
- 加 `quick?: boolean` (banner inline 一键打分预留, V2 做)

**`FeedbackRecord = FeedbackPayload + { submitted_at, comments[] }`** (D-066 + D-067):
- `submitted_at: ISO8601` (frozen-in-time fact, 不可改)
- `comments: Array<{ id, text, created_at }>` (append-only timeline, 不污染原始)

**`UnfedSession` (V1 → V1.1)**:
- 加 `summary: string` (banner 卡片渲染需要)
- 加 `snoozed: boolean` / `stopped: boolean` (D-060 两态)

### API 端点 (mock 已落, 后端待装)

砍掉:
- `GET /api/session/last_unfed` (单条) → 由 `GET /api/feedback/inbox` 列表代替, 前端取 `[0]`
- `POST /api/session/dismiss_feedback_banner` → 由 snooze (默认) / stop (显式) 取代

新增 7 个:
- `GET  /api/feedback/inbox?include_snoozed=` — 反馈中心列表数据源
- `POST /api/feedback/snooze` body `{ session_id }` — 24h 软关闭
- `POST /api/feedback/stop` body `{ session_id }` — 永久硬关闭
- `GET  /api/feedback/recent?limit=` — 最近已反馈 (供 inbox 第三段 + history 行 chip)
- `GET  /api/feedback/<sid>` — getFeedbackSession (返回 session + candidates), 已存在
- `GET  /api/feedback/<sid>/record` — getFeedback (返回 FeedbackRecord 或 null, 用于 form/detail 双态判断)
- `POST /api/feedback/<sid>/comments` body `{ text }` — append-only 评论

**实施范围 (用户决策)**:
- 后端 FastAPI **不接力**: 7 个端点仅在 `mockApi.ts` 实现, 前端 mock 跑通即可
- snooze/stop 状态存在 `STORE.acceptedQueue` (mockApi 内存 / 真后端待装时落 sqlite/jsonl)
- 旧数据迁移策略: 清空 (开发环境, localStorage 没用, mock STORE 重启即重置)

### 验证

```bash
cd apps/web && npm run build  # tsc -b && vite build, 64 modules, 263kB, gzip 80kB, 0 error
```

```bash
npm run dev → http://localhost:5173/
curl localhost:5173/ → 200
curl localhost:5173/feedback → 200
curl localhost:5173/feedback/test_sid → 200
```

7 步 user journey 端到端 (用户浏览器手测过):
1. accept 一个候选 → acceptedQueue 入队
2. 主页刷新 → 顶部出 stack banner (metadata 行 + 主卡 + footer)
3. 点 banner → `/feedback/<sid>` → progressive form (3 档 + 展开 4 维)
4. 填完点完成 → 不 navigate, 原地切到 detail view
5. 回主页 → banner 消失
6. NavBar 「反馈」→ `/feedback` 三段 (本条出现在「已反馈」)
7. 点已反馈 → detail → append 备注 → 出现在 timeline

### 反 anti-pattern

- **没保留 V1 5 星双维度** — 强制 schema migration, 用户砍掉 `rating_taste` / `rating_satisfaction` (D-064 + D-068 决策已显式砍)
- **没在反馈页加修改入口** — D-066 强制 readonly, 即使 1 分钟内也不能改
- **没让 banner ✕ = 永久 stop** — D-060 默认 snooze
- **没 seed demo backlog** — 原型 `data.js::seedDemoBacklog()` 在 mock 中没搬, 生产用真数据
- **没保留 4 个备选表单变体** (minimal/dimensions/conversational/retro) — D-062 选定 E 后, A/B/C/D + variant switcher 全砍 (5 个变体源码在 `chisha-user (1)/feedback-variants.jsx` 设计档案保留)

### 已知风险 (待后续 PR)

- 后端 FastAPI 还没装 7 个新 endpoint — 默认 mock 模式可用 (VITE_USE_MOCK=1)  → **已装, 见 D-069 (2026-05-15)**
- `chisha-user (1)/` 设计交付物文件夹本次提交时一起删, 已沉淀到 D-056~D-068 + IMPL_LOG 这条 + style-guide
- `reason_match` 的下游消化 (LLM reason generator reverse-loss) 还没实施 — 后端接入后, 推荐链路要把 comments[] inject 给 prompt

---

## D-069 执行记录 · FastAPI V1 + V1.1 后端 13 端点联调 + Codex review 修复

日期: 2026-05-15
类型: 工程实施 (兑现 D-051~D-068 + api.md §5 契约)
范围: `chisha/web_api.py` (新增) / `chisha/feedback_store.py` (新增) / `chisha/debug_server.py` (扩展) / `chisha/api.py` (微调) / `apps/web/.env.production` (新增)

### 背景

D-051~D-068 + mockApi.ts 把前端打到 mock-feature-complete, `docs/api.md` §5 把契约钉死了, 但后端 FastAPI 那侧 13 个端点一直没装 (api.md 标 `✅ mock`)。本次一次性接上, 跑通自用单机的真后端模式。

### 改动结构

**新增 `chisha/web_api.py`** — V1 + V1.1 用户视图 API, 用 `APIRouter(prefix="/api")` 挂到 debug_server。共 14 个路由 (含 `/profile` GET / PUT / POST 兼容):

| 端点 | Phase | wrap 的现成实现 |
|---|---|---|
| `GET /api/recommend` | A | `chisha.api.recommend_meal` |
| `POST /api/refine` | A | `chisha.refine.refine` |
| `POST /api/accept` | A | `feedback_store.record_accept` + urllib quote 拼 deeplink |
| `POST /api/skip` | A | `feedback_store.record_skip` (D-054 reason 白名单校验) |
| `GET /api/feedback/inbox?include_snoozed=` | B | `feedback_store.inbox_items` |
| `POST /api/feedback/snooze` | B | `feedback_store.set_snooze` (24h) |
| `POST /api/feedback/stop` | B | `feedback_store.set_stop` |
| `GET /api/feedback/recent?limit=` | B | `feedback_store.recent_feedback_items` |
| `GET /api/feedback/<sid>` | B | 联表 sessions + accepted |
| `GET /api/feedback/<sid>/record` | B | `feedback_store.get_feedback_record` (null pre-submit) |
| `POST /api/feedback` | B | `feedback_store.record_feedback` (D-066 + D-067 comments preserve) |
| `POST /api/feedback/<sid>/comments` | B | `feedback_store.append_comment` (D-067 append-only) |
| `GET / PUT / POST /api/profile` | A + C | ruamel.yaml 写入保头部注释 |
| `GET /api/history?days=` | C | 读 `logs/recommend_log.jsonl` + 联 `feedback_store.accepted` 拿 `accepted_rank` |

**新增 `chisha/feedback_store.py`** — V1.1 单文件落盘 `logs/feedback/store.json`:
- 结构 `{ accepted, feedbacks, sessions }` 镜像 mockApi.ts 的 STORE
- 用户决策走单 JSON (问询 2 选 1, 拒绝 per-session 文件 / SQLite, V1 单用户够用, 后期再换)
- 写路径全部走 tmp + rename 原子替换 + module-level `threading.Lock` (FastAPI sync handler 串行, 锁是防御)
- 派生读: `inbox_items()` / `recent_feedback_items()` 现算, 不冗余存

**改 `chisha/debug_server.py`** — `app.include_router(web_router)` + 挂 `apps/web/dist`:
- `/` 路径让给 SPA index.html, 老调试台挪到 `/debug`, 逻辑页挪 `/logic` (兼容 `/docs` 旧路径)
- `/assets/*` 用 `StaticFiles` 直挂; SPA fallback `/{full_path:path}` 兜底 React Router (`/feedback` `/history` `/profile` 等), `/api/*` 未匹配的视为 404 不被 swallow
- 没装时 (dist 不存在) `/` 返回带 build 提示的 JSON, 老调试台仍可用

**改 `chisha/api.py:170-178`** — `_format_v2_candidate` 加 `id` 字段 (`c_{combo_index}_{rest_id}`), 别名 `format_v2_candidate` 暴露给 web_api 复用; refine 的 candidates 在 web_api 里走同一 formatter 让前后端两条路径返回形状完全对齐 (`RecommendResponse`)。

**新增 `apps/web/.env.production`** — `VITE_USE_MOCK=0`, 让 `cd apps/web && npm run build` 出的 bundle 走真 fetch (dev 时 vite proxy 已经存在, 不动)。

### 验证 (curl 矩阵)

13 端点 + SPA 托管全跑通:

```
GET    /api/recommend                       HTTP 200, 13s, 5 候选, candidate 含 id 字段
POST   /api/refine                          HTTP 200, 17s, round++, refine_input 入 context
POST   /api/accept                          HTTP 200, < 50ms, store.json accepted[] 入条
POST   /api/skip (cafeteria)                HTTP 200, skipped=true, stopped=true
POST   /api/skip (hahaha)                   HTTP 400, reason 白名单拦截
GET    /api/feedback/inbox                  HTTP 200, accept 后立即出现
POST   /api/feedback/snooze                 HTTP 200, snoozed_until +24h
GET    /api/feedback/inbox?include_snoozed=0  HTTP 200, 过滤 snoozed
POST   /api/feedback/stop                   HTTP 200, 任何模式 inbox 都不含
GET    /api/feedback/<sid>                  HTTP 200, 5 候选 + accepted_rank 回放
GET    /api/feedback/<sid>/record           HTTP 200, 提交前 null, 提交后 FeedbackRecord
GET    /api/feedback/missing_sid            HTTP 404
POST   /api/feedback                        HTTP 200, comments[] 保留 (D-067)
POST   /api/feedback/<sid>/comments         HTTP 200, append-only push
POST   /api/feedback/missing_sid/comments   HTTP 404
GET    /api/feedback/recent?limit=6         HTTP 200, 按 submitted_at 倒序
GET    /api/profile                         HTTP 200
PUT/POST /api/profile                       HTTP 200, 文件头部 22 行注释保留
GET    /api/history?days=7                  HTTP 200, 10 条, accepted_rank 联表
GET    /api/history?days=999                HTTP 400
/                                           HTTP 200, SPA index, mock pool tree-shake 掉
/feedback                                   HTTP 200, SPA fallback
/api/foo (未注册)                          HTTP 404
```

### Codex review (dual-model audit, D-036 pattern) + 修复

**4 个 MED, 全修**:

| 编号 | 文件 | 问题 | 修法 |
|---|---|---|---|
| MED-1 | web_api.py accept/skip | 写盘失败被 try/except 吞 → 返回 200 + 假 deeplink, acceptedQueue 静默丢条 | 改 `raise HTTPException(500, ...)`, 让前端能看见后端炸了 |
| MED-2 | debug_server.py spa_fallback | URL 解码后的 `../` 拼 `WEB_DIST / full_path` 可能逃逸 dist 目录读 profile.yaml | `candidate.resolve().relative_to(_WEB_DIST_RESOLVED)` 守卫, 越界回 SPA shell |
| MED-3 | feedback_store.load_store | corrupt JSON → 空 store → 下次写盘把所有历史反馈覆盖掉 | 抛 `StoreCorruptError`, rename 损坏文件为 `.corrupt.{ts}.bak`, 上游 500 |
| MED-4 | web_api.FeedbackPayloadReq | `rating: int / variant: str` 接受任意值, `not-eaten` 无跨字段不变量 | `Literal[-1,0,1] / Literal[0,1,2] / Literal["progressive","not-eaten"]` + `@model_validator(mode="after")` 强制 not-eaten ⇒ accepted_rank+5 维度全 null |

**6 个 LOW, 全修**:

| 编号 | 文件 | 问题 | 修法 |
|---|---|---|---|
| LOW-1 | debug_server.py DebugRecommendReq/CompareMoodsReq | n_return/n_explore 无上界, moods 列表无 cap, 误传 n=999 会放大 LLM 调用 | `Field(ge=1, le=20)` / `Field(ge=0, le=10)` / `min_length=1, max_length=8` |
| LOW-2 | debug_server._parse_today | 非法 YYYY-MM-DD raise 未捕获 ValueError → 500 | catch + `HTTPException(400, ...)` |
| LOW-3 | feedback_store.append_comment | comment id = `cmt_{ms}` 同毫秒撞 → 前端 key 冲突 | `cmt_{ms}_{secrets.token_hex(2)}` 4-hex 后缀 |
| LOW-4 | feedback_store._is_snoozed_now | `datetime.fromisoformat(naive)` vs `datetime.now(UTC)` 比较 raise TypeError | naive 视为 UTC, aware 转 UTC, 再比较 |
| LOW-5 | web_api.api_feedback_recent | `limit=-1` → list[:-1] 返回全部 - 1 | `Query(ge=1, le=100)` |
| LOW-6 | (合并入 MED-4) | `quick?: boolean` 默认应是 false, 当前 `quick: bool \| None = None` 入库 null | `quick: bool = False` |

**验证**:
- MED-1: `chmod 555 logs/feedback` → accept → `HTTP 500 PermissionError`
- MED-2: `/..%2f..%2fprofile.yaml` → 返回 SPA index 而非 profile.yaml
- MED-3: 注入 `[` / `corrupt-junk` 到 store.json → inbox 调用 500, 备份生成 `store.json.corrupt.{ts}.bak`
- MED-4: `rating=5 → 422` / `variant=random → 422` / `variant=not-eaten + rating=1 → 422 with offenders=['rating']`
- LOW-1: `n_return=999 → 422` / `moods 9 个 → 422`
- LOW-2: `today=hahaha → 400`
- LOW-3: 同 1ms 3 次 append → ID 全不同 (`cmt_..._b254 / _190e / _a5f7`)
- LOW-4: 注入 naive `snoozed_until` → inbox 200 不爆 TypeError
- LOW-5: `limit ∈ {-1, 0, 200} → 422`

### 反 anti-pattern (这次没踩)

- **没改 chisha/api.py 的 recommend_meal 内部**: 它已经是 V2 单一链路 (D-049), web_api 只在外围加 candidate `id` 字段 + 落 session 副作用, 推荐链路不动
- **没在 chisha/feedback.py 加 V1.1 schema**: 旧的 `FeedbackParsed` / `parse_feedback` 是 D-035 的 chip 解析员 (refine 二轮用), 与 V1.1 直接反馈 schema 是两条线, 各跑各的不合并 (V2 反馈学习管道连起来再 review)
- **没用 sqlite**: 走单 JSON 文件用户决策, V1 单用户场景够用; 后续多用户 / 并发写需求触发再迁
- **没自评通过就交付**: Codex review 找到 4 MED + 5 LOW + 1 已修, 全修后才认为 ready (D-036 dual-model audit 模式守住)

### 已知遗留 (推 V1.5+)

- ruamel.yaml deep-merge 写 profile.yaml: 长 multi-line block (如 `taste_description: |`) 在覆盖时 `|` 可能变 `|-`, 不影响语义但形态有微调
- `_remember_session_safe` (web_api) 还是 best-effort 吞错: 设计意图是 session replay 仅为反馈页便利, 推荐主链路不能因落盘失败断; 但极端情况下用户提交反馈时 5 候选 dump 可能丢, 反馈页会 404 — 实测后再决定是否提级
- 历史 `recommend_log.jsonl` 没去重 / 没分割; 自用一周后做 logrotate

---

## D-071 执行记录 · 砍 mood picker + want_soup 关键词识别

**2026-05-15** · D-070 定位收敛的工程落地 Step 1

### 改了什么

**前端 (apps/web/)**:
- `components/StatusBar.tsx`: 删 mood chip 区块 (52-70 行) 和 setMood/mood props, 保留 LABELS.mood / Mood 类型 (调试台仍用)
- `pages/HomePage.tsx`: 引入 `FIXED_MOOD: Mood = 'neutral'` 常量, fetchRecommend / regenerate / onRefine 三处用固定值; 删 setMood handler 与调用点

**后端 (chisha/refine.py)**:
- 新增 `infer_refine_mood(user_input)`: 子串匹配, 否定优先. 正向词 10 个 / 否定词 6 个 (D-071 字典)
- 新增 `_match_positive_keyword` / `_match_negative_keyword` 内部辅助 (供埋点用)
- 新增 `MOOD_TRACE_SCHEMA_VERSION = 1` 常量 + `_build_mood_trace()` + `_append_mood_trace()`. 双写: refine() 返回 dict 加 `mood_inference` 段; 同时落 `logs/refine_mood_trace.jsonl` (5MB 轮转, 写失败静默)
- `refine()` 主入口: 在 build_context 前算 `effective_daily_mood = state.daily_mood or inferred_mood`, 显式优先于推断 (Codex Round 1 Q2)

**后端 (chisha/score.py)**:
- `context_boost`: 砍 4 条 mood 规则 (want_light / low_carb / want_clean / want_indulgent), 保留 want_soup. 函数从 ~30 行简化到 ~10 行, 注释明确这是 D-072 spec 接口位, 不要再扩
- 删 `infer_default_mood` 函数 + `DEFAULT_MOOD_CONFIDENCE` 常量 + `context_boost` 里调用兜底分支 (D-043 季节兜底在 D-070 定位下不适用)

**测试 (tests/)**:
- 新增 `test_refine_mood_inference.py` 34 case: 正向命中 5 / 否定 4 / 反例 3 / 已知局限 2 / 边界守门 8 (param) / 内部 helper 2 / trace 构造 4 / jsonl 写入 2 / 前后端契约 3
- 改 `test_score_v2.py`: 删 4 条 want_light/low_carb/want_clean/want_indulgent 老断言, 替换为 deprecated-behavior 显式 assert == 0 (Codex Q6 + delete-tests MAJOR); 删 3 条 infer_default_mood 老断言, 替换为 `not hasattr(score_mod, ...)` + `context_boost(None) == 0` 反季节兜底断言

### Codex Round 1 Review 发现与修复

实现前提交 plan 走 codex-rescue gpt-5.3-codex 独立 review, 输出 **条件 Go**:

| 等级 | 发现 | 落地 |
|-----|------|------|
| BLOCKER | 契约漂移: 残留 mood 调用点可能仍发非 neutral | 加 3 个 Python 结构化扫描 contract test, 锁 StatusBar 无 mood props / HomePage 用 FIXED_MOOD 常量 / web_api `neutral → daily_mood=None` 映射 |
| MAJOR | Q1 关键词字典对抗负例不足 (店名/反讽场景) | 加 2 个 "提及但非欲望" case (鸡蛋羹这家店 / 粥铺主打面), 注释明确这是已知局限, 退 L3 兜底 |
| MAJOR | Q4 jsonl schema/轮转/非阻塞缺设计 | schema_version 字段 + 5MB 轮转 (.1 备份) + try/except 静默失败 + 单测 `test_append_mood_trace_silent_on_failure` 锁不阻断 |
| MAJOR | Q6 边界靠 review 守不工程化 | 加 8 个 parametrize 边界守门 case, 任意非 want_soup 意图文本 (清淡/轻食/解馋/辣/加工肉...) 必返 None |
| MAJOR | delete tests 直接删抹掉历史 | want_light/low_carb/want_clean/want_indulgent 老测试改成 deprecated-behavior 显式 `assert == 0.0`, 不静默删 |
| PASS | Q2 显式 > 推断短路语义 | trace 加 `source: explicit\|inferred\|none` 字段显式化 |
| MINOR | Q3 context_boost 是否合并到 wetness_bonus | 保留独立维度, 注释说明是 D-072 spec 接口位 |
| MINOR | Q5 "汤泡饭" None vs "想喝汤泡饭" want_soup 对照 | 加显式对比对单测 (test_inference_no_match_tang_pao_fan + test_inference_xiang_he_tang_pao_fan_still_hits) |

### 回归与验证

- `uv run pytest tests/ -q`: 412 passed, 1 failed (pre-existing `test_cleanup_expired`, D-048 已知, 与本次无关)
- `npm run typecheck` (apps/web): 通过, 无新 TS error
- `uv run python -m scripts.dry_run --n 3 --meal lunch`: 5 推荐输出正常, 不再误用 daily_mood 兜底
- 手动 refine 集成测试 (走 chisha/refine.py:refine() 完整链路, 不打 LLM):
  - "今天有点冷想喝热汤" → matched=热汤, inject=want_soup, source=inferred ✅
  - "今天别来汤了想吃辣的" → negated=True, inject=None, source=none ✅
  - "想吃肉" → matched=None, inject=None, source=none ✅
  - logs/refine_mood_trace.jsonl 3 行 schema_version=1 正常落盘

### 踩到的坑

1. **mood 'neutral' 在前端是字面量, 在后端 web_api 映射为 daily_mood=None** — 前后端各自管语义, 中间字符串 'neutral' 是 wire 约定. 删 mood picker 时本可以让前端发 daily_mood=None, 但保留 'neutral' wire 兼容 (后续若加新 mood 复用同入参) — 是有意的轻债, 在契约 test 里锁住
2. **delete tests 是 Codex 特意点出来的小坑**: 直接删旧 mood 分支测试, 历史会消失; 替换为 "这维度返 0" 的 deprecated-behavior 断言, 让未来 refactor 一眼看到 "这是有意收敛, 不是遗忘"
3. **子串匹配的"提及但非欲望"** 是已知局限 (鸡蛋羹这家店命中"羹"), 现在用 known-limitation 单测明确接受当前行为, 未来若加意图分类把 case 改成 None 即可 — 反而比"假装这条 case 不存在"更诚实
4. **score.py 重构延后到 D-072**: 这次只删 4 条 mood 分支 + infer_default_mood, 不改打分函数签名 / 不调权重, 严格守 D-071 边界 (不顺手做 D-072 范围的事)

### 反 anti-pattern (这次没踩)

- **没扩 infer_refine_mood scope**: 字典死死锁在 10 正向 + 6 否定 want_soup 词, docstring 明确边界, 单测有边界守门. D-071 警告执行到位
- **没把 jsonl 写成阻塞**: 全部 try/except + best-effort + 路径不可写场景有单测
- **没漏 Mood 类型保留**: LABELS.mood / Mood 类型留在 lib/types.ts 给调试台用, 前端只是入口移除
- **没在 score.py 顺手调权重**: D-072 才动权重, D-071 只做信号源头 (mood)

### 依赖与影响

- 推翻: D-043 季节默认 mood 兜底 + want_light/low_carb/want_clean/want_indulgent 4 条 context_boost 规则
- 保留: D-034 ContextSnapshot / D-043 want_soup wetness 通道 / D-048 trace 字段精神 (mood_inference 与 D-048 L3 trace 同级共存)
- 下一步 (D-072): methodology spec 抽象, context_boost 函数实质会被 spec.soft_rules 接管 (现在保留接口位)

---

## D-072 / D-072.1 执行记录 · methodology spec 抽象 + score.py 重构

**2026-05-15** · D-070 三层信号模型 L0 工程化, Phase 0 Step 3 收尾

### 改了什么

**新增 spec 文件**:
- `profiles/methodologies/harvard_plate.yaml` 79 行: 7 必备字段 (name / display_name / version / rationale / plate_rule / score_weights × 16 / cap_rules × 4) + 3 可选 (unforgivable_discount / soft_rules / extra_rules). 数值与 score.py `V2_DEFAULT_WEIGHTS` / `resolve_caps` / `plate_rule defaults` 完全一致, 不调权重

**新增加载层 `chisha/methodology.py` (244 行)**:
- `MethodologyValidationError(ValueError)`: hard fail 异常
- `_validate_spec()`: 顶层 7 必备 + plate_rule × 5 + score_weights × 16 + cap_rules × 4 严格 keyset 校验 (拼写错也 hard fail, Codex BLOCKER B-1)
- `load_methodology(name, root)`: 加载 + 校验 + 文件名一致性检查; LRU cache key 含 yaml mtime_ns (Codex Round 3 M-3, yaml 改后自动失效)
- `resolve_methodology(profile, root)`: profile.methodology 字段 → spec; 缺字段时 fallback `harvard_plate` + `logger.info` (Codex M-1, 非 silent)
- `merge_into_profile(profile, spec)`: 三段 merge — plate_rule / scoring_weights / recall.per_*_top_k 都是 spec 默认 + profile override; unforgivable_discount 路径必须 `profile.scoring.*` 不是顶层 (Codex B-2); 不就地改 profile
- `apply_methodology(profile, root)`: convenience wrapper

**改造 `chisha/recall.py:load_profile`**:
- 加载 yaml 后自动调 `apply_methodology` merge spec defaults
- 新增可选 `root` 参数, 临时路径场景显式传 (Codex Round 3 M-1)
- 所有调用方 (api/web_api/debug_recommend/dry_run/scripts) 自动受益, 不需改

**改造 `chisha/rerank.py:_profile_block`**:
- `[PROFILE]` 段顶部注入 `方法论: {display_name} — {rationale 第一行}`
- profile 缺 `_methodology_spec` 时 fallback 老格式 (向后兼容)
- 改动严格限制 1 行新增, 单测断言

**profile.yaml 加字段**:
- 顶部加 `methodology: harvard_plate` (向后兼容: 缺字段会 logger.info fallback)

**新增工具脚本**:
- `scripts/baseline_l2_snapshot.py`: L2 capped top60 + score + 16 维 breakdown 全展开签名 (deterministic, 不打 LLM)
- `scripts/compare_traces.py`: 严格 diff, top60 顺序 100% 一致 + 16 维 |delta| < 1e-6
- `scripts/baseline_l3_prompt_ab.py`: L3 prompt with vs without methodology 行 A/B 对照 (Codex M-2 sanity)

**新增测试 `tests/test_methodology.py` 23 case**:
- 校验类 7: missing top key / unknown top typo / score_weights missing / score_weights typo / plate_rule typo / cap_rules extra / name mismatch
- resolve 类 2: 显式 field / fallback + INFO log
- merge 类 6: 不就地改 / 显式 override spec / unforgivable B-2 路径 / unforgivable profile override / recall cap key 局部 / 附加 spec name
- apply 类 1: tmp_path 默认 fallback
- 缓存类 2: deep copy / mtime invalidation
- rerank A/B 类 3: with methodology / without fallback / 单行 diff 守门

### Codex 三轮 review 与闭环

| 轮 | 发现 | 修复 |
|---|------|------|
| **Round 2** (设计前) | BLOCKER B-1 内部 key 拼写错 silently 落 V2_DEFAULT 违反"只搬运" | 严格 keyset 校验 plate_rule / score_weights / cap_rules 全维 |
| Round 2 | BLOCKER B-2 unforgivable_discount 字段路径错 (顶层 vs profile.scoring.*) | merge 时显式映射到 profile.scoring.unforgivable_discount + 单测锁路径 |
| Round 2 | MAJOR M-1 Q5 silent default 与 D-048 hard-fail 冲突 | resolve_methodology fallback 时 logger.info 留可观测痕迹 |
| Round 2 | MAJOR M-2 rerank 注入会让 L3 输出不可比无 A/B 基线 | baseline_l3_prompt_ab.py 捕获 with/without 双版本 prompt |
| Round 2 | MAJOR M-3 schema 字段命名未冻结 | D-072 末尾追加 "最终 schema 字段表" + 落 D-072.1 修订条目 |
| Round 2 | blindspot-1 比较粒度未定义 | compare_traces.py 明确断言层级 (顺序 100% + delta < eps) |
| Round 2 | blindspot-2 merge 覆盖 profile 显式值风险 | test_merge_profile_explicit_value_overrides_spec 单测锁 |
| Round 2 | blindspot-3 重构前先自比 0 diff | baseline 两次同输出 → compare 0 diff 验证工具正确 |
| **Round 3** (diff 后) | BLOCKER B-1 baseline 存 round(6) 浮点会吞 <5e-7 真实差 | 去掉 round, 存原始 float, EPSILON 在 compare 阶段控 |
| Round 3 | MAJOR M-1 load_profile path.parent 推断 root 临时路径错 | 加可选 root 参数, 向后兼容 |
| Round 3 | MAJOR M-2 缺 rerank fallback 测试 | 新增 3 个 test_rerank_profile_block_* case |
| Round 3 | MAJOR M-3 cache 无失效机制 | cache key 加 mtime_ns + test_cache_invalidates_on_yaml_mtime_change |
| Round 3 | MINOR ×3 注释/文档错字 | 全修 (注释 "8 个" → "4 个" / 文档 "6 字段" → "7 字段" / yaml "12+维" → "16 维") |

### 回归验证 (D-072.1 严格协议)

1. **重构前自比** (blindspot-3): 同代码跑 baseline 两次 → `compare_traces` 0 diff (工具正确性)
2. **重构后 L2 严格回归**:
   - top60 combo 顺序 100% 一致 (餐厅 + dish_ids 签名)
   - 16 维 breakdown 每维 |delta| < 1e-6
   - 总 score |delta| < 1e-6
   - 实测: 4 个 snapshot (lunch/dinner × neutral/want_soup) 全 0 diff
3. **三路径行为一致**: `load_profile` 被 api / web_api / debug_recommend / dry_run / scripts 共用, 自动 merge spec; 无需每条路径单独测
4. **L3 prompt A/B**: with_methodology 比 without 多 1 行 "方法论: ..." (`tmp/baseline_traces/l3_prompt_lunch_*.txt`); 字符差 +68
5. **pytest**: 435 passed, 1 failed (pre-existing test_cleanup_expired, 与本次无关)

### 踩到的坑

1. **"round 到 6 位破坏严格回归"** (Codex Round 3 BLOCKER B-1) — 直觉以为 round(6) 是给可读性, 实际把 < 5e-7 真实回归差异量化吞掉. 教训: trace baseline 永远存原始 float, 格式化只在打印层做
2. **unforgivable_discount 路径** (Codex Round 2 BLOCKER B-2) — schema 字段名 (顶层 `unforgivable_discount`) vs 实际读路径 (`profile.scoring.unforgivable_discount`) 不一致, 不靠 review 抓不到. 教训: 写 spec 字段时一定要看 score.py 实际从哪条路径读, 不能凭直觉
3. **cap_rules merge 用 setdefault 而非字典展开** — recall 字段除了 per_*_top_k 还有 per_restaurant_max / min_monthly_sales 等非 cap 字段, 直接 `{**spec, **profile}` 会用 spec 的空字段覆盖 profile 的实际值. 用 `setdefault` 只填缺失 key, 行为正确; 但单测必须 cover 这场景 (test_merge_recall_cap_keys_only)
4. **lru_cache 失效**: yaml 改后 cache 不刷新, 调试时一直读旧值. 加 mtime_ns 到 cache key 解决, 不重新设计 cache 机制
5. **rerank 注入 L3 行为变化**: L2 严格回归 0 diff 不代表 L3 一致 — 新增"方法论:"行会改 LLM 输入, 但用户在 D-072 设计阶段已认可这是 enhancement 而非回归. baseline_l3_prompt_ab 留对照, 未来 L3 行为漂移可对照排查

### 反 anti-pattern (这次没踩)

- **没顺手改打分逻辑**: D-072 警告"spec 抽象只搬运, 不改逻辑". score.py 函数全部不动, 只是常量来源从硬编码改成 spec 默认. baseline 0 diff 是最强证据
- **没扩 schema 字段**: 16 维 score_weights / 4 层 cap / 5 字段 plate_rule 严格对齐 V2_DEFAULT_WEIGHTS, 没加新维度
- **没 silent fallback**: profile 缺 methodology 字段 → logger.info; spec 文件不存在 → FileNotFoundError; 校验失败 → MethodologyValidationError. 所有失败路径都可观测
- **没把 profile 个人化字段塞进 spec**: profile.scoring_weights.wetness=0.0 (D-044.1 砍 baseline) 是个人 override, 不该进 harvard_plate.yaml; merge 时 profile 显式 override 处理

### 依赖与影响

- 推翻 (软): D-043 部分内容 (打分逻辑硬编码 → spec 化)
- 修订: D-072 触发条件 (走 D-072.1, L2 trace baseline 替代采纳率门)
- 关联: D-070 三层信号模型 L0 工程化; D-071 context_boost 接口位预留生效
- 下一步 (Phase 1): 第二份 spec (减脂 / 增肌 / 糖控) 走 `profiles/methodologies/{name}.yaml` 接入; 若需要新字段类型 → 走 `extra_rules: []` 逃逸口先临时, 再走 D-072.M 修订把字段升正


## D-073 + D-074 执行记录: L1 LLM 抽取层 + Sandbox Time-Travel 模式

**Status**: implemented (2026-05-16, 10 PRs + 1 修补 PR)
**关联**: [docs/DECISIONS.md D-073](DECISIONS.md#d-073-l1-长期反馈层重构--砍伪-l1--llm-抽取-v1x) / [D-074](DECISIONS.md#d-074-sandbox-time-travel-模式-v1x)

### 触发与决策过程

志丹挑战 D-070 三层信号模型代码落地, 揭出"伪 L1" (refine chip 跨 session 频次聚合) 和 V1.1 反馈数据躺尸. 走 D-036 dual-model audit:
- S1 Opus 提案 → S2 Codex review 揭出"web 反馈不进 long_term_prefs / claude_code_cli 不支持 tool_use / PR-0.7 切 score 非等价重构" → S2 二次 review 揭出 10 项修正 → 志丹拍板 1A (text+JSON) + "一波到位 + bootstrap_from_legacy" → 全部实现 + S3 Codex 端到端 review 发现 2 ship-blocker MED (recommend_meal 读 prod profile / api_history 读 prod log) → PR-3 修补.

### 提交序列 (11 commits)

| Commit | PR | 范围 | 单测 |
|--------|----|------|------|
| 2403c2e | PR-0 | l1_extractor + l1_prefs + prompt + 3 golden fixtures | 38 ✓ |
| 7b2692c | PR-0.5 | 砍 refine→feedback_history + 拆 legacy | 26 旧测试保留 |
| 5fbed85 | PR-0.6 | bootstrap_from_legacy 脚本 | 4 ✓ |
| bf50e68 | PR-0.7 | score 切 l1_prefs.load_prefs (baseline 0 diff) | 6 + 3 旧改造 |
| 3cf1a53 | PR-0.9 | /api/long_term_prefs/refresh + 鉴权 | 4 ✓ |
| d2f88c0 | PR-1a | clock.py + sandbox.py + 11 处时间注入 | 18 ✓ |
| 22fc03b | PR-1b | data_root.py + 7 路径派生 | 9 ✓ |
| 876e38d | PR-1c | FastAPI 6 sandbox 端点 + 异步 L1 trigger | 12 ✓ |
| 31d4a6d | PR-1d | 前端 SandboxBar + ProfilePage 入口 + Drawer | (build pass) |
| e1b71e5 | PR-2 | DECISIONS + 10 验收锚点 + ROADMAP/README/CLAUDE.md | 10 e2e ✓ |
| (本条目) | PR-3 | Codex S3 修补 (profile/history sandbox path + L1 lock + schema 严格化) | TBD |

### 关键经验

1. **文件名误导**: `long_term_prefs.py` 命名带 "long_term" 但实际是单次 chip 跨 session 频次聚合, 让 Opus 误判 D-070 L1 已建. 教训: 命名要反映行为, 不是意图; review 时要验证 "文档说 X 已建" 是否真的指代码层 X 而不是同名别物.
2. **Codex S2 二次 review 揭出 tool_use 矛盾**: D-047 原则 "tool_use 优于 json_mode" 对 L3 rerank 是对的, 但对 L1 抽取错位 — L3 高频实时, L1 低频 + 可降级, text+JSON+retry 更适合且能用 Max 订阅免费.
3. **三态等价性必须可证**: Codex Q3 "compare_traces 只能证当前机器无旧信号, 不能证迁移等价" 是关键洞察, 启发 bootstrap_from_legacy 兜底.
4. **Profile 路径 + history 路径** (Codex S3 揭出): 仅"业务数据落盘"换 path 还不够, **业务数据读路径**也必须走 data_root. 否则 sandbox 内 PUT profile 写副本但下次推荐仍读 prod, 形成"假沙盒".

### Codex S3 ship-blocker 修补 (PR-3)

1. **chisha/api.py:110** `recommend_meal` 默认 profile_path 改走 `data_root.profile_path(root)` — 解决"sandbox PUT profile 写副本但读 prod"
2. **chisha/web_api.py:307** `/api/history` 改走 `data_root.recommend_log_path(ROOT)` — sandbox 内 history 读 sandbox log
3. **prompts/l1_extract.md** 阈值 `< 5` → `< 3` 与代码 `MIN_MEALS_FOR_EXTRACTION` 统一
4. **chisha/l1_extractor.py** extracted_at 走 `clock.now_utc()` (虚拟时钟一致性)
5. **chisha/l1_extractor.py** `except (ValueError, Exception)` 拆成 LLM call err / JSON parse err / schema err 三阶段
6. **chisha/l1_prefs.py** 删 `PrefsCorruptError` 未用类; validate_prefs 加 maxItems=2 / evidence schema / regularities 字符串过滤
7. **chisha/web_api.py** L1 异步 trigger 加 `_L1_EXTRACTION_LOCK` trylock 防多 tab 并发覆盖 state
8. **README.md / CLAUDE.md / ROADMAP.md** 端点数字 "18" → "20" 统一

### 守门记录

- baseline_l2_snapshot 在 PR-0.7 / PR-1a / PR-1b / PR-1c / PR-2 / PR-3 各跑一次, 4 snap |delta| < 1e-6 全程通过
- 全测试 (含 26 legacy + 18 sandbox/clock + 9 data_root + 12 sandbox endpoint + 4 refresh + 38 l1_extractor + 24 l1_prefs + 9 score_l1_switch + 4 bootstrap + 10 e2e 锚点) → 526~536 pass, 0 fail, 1 skipped
- 前端 (Vite + TypeScript strict mode) build 通过

### 已知 V1 gap (不在本次范围)

- `logs/meal_log.jsonl` 没有写入端 (PR-1c accept 只写 feedback_store.accepted), diversity_filter cooldown 实际不工作 — Phase 1 单独修
- L1 抽取 prompt 在真实 LLM 上的稳定性还没跑过 (单测全 mock), 真跑时如果 LLM 不听话需 fixture 训练
- sandbox 切回 prod 后 in-flight 请求行为未守门 — 当前用户一次会话只切一次, 暂不补


## D-075 执行记录 · sandbox 时钟漏注入 + accept→meal_log 闭环 cooldown

日期: 2026-05-16
形态: 1 commit (含 Codex S1 + S2 两轮 review 修订)
状态: ✅ 全测试 542 pass / baseline 0 diff / 用户视角真实 LLM 5 日演练全通

### 提交单

| commit | 内容 | 测试 |
|---|---|---|
| (待) | D-075 全量 (P0-1/P0-2/P1/P2 + S2 Codex 修补) | 542 ✓ |

### 用户视角验收 (主路径)

跑法: `uv run python -m chisha.debug_server` + `uv run python tmp/user_drive.py` (真实 LLM via claude_code_cli Max 订阅).

| 步骤 | 期望 | 实测 |
|---|---|---|
| Day 1 accept 湖南老灶台 + 反馈 oil=2 repurchase=0 | accept 200 + meal_log.jsonl 写一条 | ✓ |
| Day 2 advance → L1 触发 | state.last_l1_extraction.status: pending→ok, based_on_meals=1 (< MIN=3, skipped) | ✓ |
| Day 2 候选 | 不含湖南老灶台 (cooldown 7d) | ✓ |
| Day 3 advance → L1 触发 | based_on_meals=2, skipped_extraction=true | ✓ |
| Day 4 advance → L1 真打 LLM (12s) | based_on_meals=3, boost=["low_oil"], evidence: "4/4 oil_calibration=too_high" | ✓ |
| Day 12 (7d 后) | 湖南老灶台重回候选, cooldown 解锁 | ✓ |
| taste_match_bonus(低油 combo, hints={boost:[low_oil]}) | 0.5 | ✓ |
| taste_match_bonus(高油 combo, hints={boost:[low_oil]}) | 0.0 | ✓ |
| reset → state.enabled=false + logs/sandbox 消失 + prod profile.yaml md5 不变 | ✓ | ✓ |

### 关键技术点

- **L1 时钟修补**: `aggregate_inputs(today=None, root=None)` 默认走 `clock.today(root)`. extract_and_save 透传 root. 测试 `test_aggregate_default_today_uses_chisha_clock` 用 monkeypatch sandbox._project_root 模拟虚拟时钟下 ts=05-30 > real today=05-16 但 < virtual today=06-01 仍计入.
- **llm_client.call_text 重接**: `_default_llm_call` 从 `import call as llm_call` 改为 `import call_text`, 调用走位置参数 prompt (call_text 第一个参数 prompt 是 positional). 测试 `test_default_llm_call_uses_existing_llm_client_symbol` 守门符号存在.
- **append_meal_log_entry**: 走 data_root.meal_log_path(root) + clock.now_utc(root). dishes 接受 flat (chisha.api._format_candidate) 和 nested (raw tagged) 两种形态, 落盘只保留 main_ingredient_type + canonical_name. 可选 zone/accepted_rank/combo_index/candidate_id 写满审计字段. 失败 hard-fail (web_api 层捕获 → 500).
- **reset/disable 抢 L1 锁**: `_block_until_l1_idle_or_409` 抢 30s 超时则 409. anchor 13 用 monkeypatch + threading.Event 控制 worker 慢函数 + 并发触发 reset 验证 prod 路径不污染.
- **advance pending → 409**: api_sandbox_advance 在 state.last_l1_extraction.status==pending 时直接 raise 409. anchor 14 守门.
- **三态 inspect drawer**: SandboxBar.tsx React IIFE 分支 (null / skipped_extraction / 正常). meal_log_recent 真实条目渲染.

### Codex audit 两轮

- **S1**: 7 个 issue (P1×3 含 zone 缺失 / hard-fail 评估 / advance race; P2×4 含审计字段 / append 锁 / wait_l1_settle conftest / D-075 编号). 落地: zone + 审计字段 ✓, hard-fail 保留 ✓, conftest 提 wait_l1_settle ✓.
- **S2**: 反馈一轮修复后 3 个新 issue (Q1 半态 transaction 拍板保留 hard-fail; Q2 advance pending 409 落 ✓; Q3-High reset/disable 抢锁防污染 prod 落 ✓; 其它 Medium/Low 留 backlog).

### 新加测试 (4 anchor + 2 单测)

- `test_aggregate_default_today_uses_chisha_clock`: 沙盒虚拟时钟下 ts 在 real today 未来但 virtual today 内的反馈正确计入
- `test_default_llm_call_uses_existing_llm_client_symbol`: llm_client.call_text 存在 + _default_llm_call 调用 OK
- anchor 11: 5 日推进 4 反馈 → based_on_meals=4 + prefs.boost=["low_oil"]
- anchor 12: accept 写 meal_log + diversity_filter 屏蔽 + 8d 后解锁
- anchor 13: reset 期间 L1 worker 跑慢 → reset 阻塞 → worker 完成后 reset 200 + prod 路径 long_term_prefs.json 不存在
- anchor 14: advance 在 pending 时返 409

### wait_l1_settle 共享 fixture

`tests/conftest.py` 提供 `wait_l1_settle(client, prev_at, timeout=4.0)`. 关键点: 监 last_l1_extraction.at 翻新, 不监 status, 防 ok→ok 瞬间被 stale 状态误判 settle.

### 已知 V1 gap (不在 D-075 范围, 候补 D-075.1+)

- diversity_filter 按 zone 过滤 (跨 zone 污染概率低)
- reset/disable 抢锁失败后的 dirty-flag 补跑 (现在只 409, 用户重试)
- meal_log 多 tab 并发 append 文件锁 (与 recommend_log 同级)
- L1 prompt 在真实 LLM 上稳定性 (本次真跑 1 次 12s ok, 长期需 fixture 训练防漂移)
