# Prompt Step 3 续 — reason 示例精简 + 多 cache breakpoint

**日期**: 2026-05-21
**状态**: **closed — 两项都不做** (2026-05-21 志丹拍板). 项 A: codex 共识信号都不重复; 项 B: codex SHIP 但志丹砍 (9h + 3 high-risk 文件, ROI 限 5min 连续 refine 长尾, 立 F-012 留 follow-up)
**来源**: 2026-05-20 prompt review brief 附录 B Step 3 剩余项 (top-K 60→40 已砍 — 与 D-047 实测冲突)
**第一原则**: 砍/拆要有 ROI 数据支撑, 不做机械数量目标; 跟已有 D-XXX 实测决策冲突的建议**默认 D-XXX 优先**.

**收口标记**: prompt 优化大题 (Step 1 + 2 + 3) **全部收口**. Step 1 已 commit (T-PR-01~07); Step 3 🔴 refine cache bug 已 commit (D-095); 剩余项全部 BACKLOG (F-012 / Step 2 可读性 / Step 4 model 切换).

---

## 0. 调研后已砍的一项 (上下文)

**❌ L3 top-K 60 → 40**: `chisha/rerank.py:35-48` 注释有 D-047 矩阵实测 (sonnet+opus × top30/60/100 × 3 重复 = 18 调用):

> sonnet picks 跨 K: top30 → top60 新增 [31, 35, 55]; opus 新增 [2, 31, 55]. 验证 **top31-60 真有多样性增量**. K=60 是稳定 + 多样性 + 成本的最优平衡.

Brief 附录 B 写"31-60 仅 3 新候选边际低"用的就是 D-047 数据, 但 D-047 解读为"3 个真增量值得保留". **review 没看 D-047 全文留的盲点**, 本次砍掉这项不做.

---

## 1. 项 A — reason 示例精简

### 1.1 现状

| Prompt | 示例数 | 分布 |
|---|---|---|
| `prompts/rerank_system.md` (reason 示范段, L121-135) | **10 例** | 4 exploit ✅ + 3 explore ✅ + 3 ❌ 禁止 |
| `prompts/parse_refine_intent_v2.md` (示例段, L96-159) | **10 例** | 涵盖 cuisine_want / cuisine_avoid+price / brand_avoid+cooking / cooking_method_avoid / oil 走构 / reference / 冲突表达 / schema 未覆盖 / 用户放权 / 用户陈述场景 |

Brief 附录 B 写"8 例减到 4-5 例" — 用的是早期版本, **D-094 实施反而增加了示例** (新加"schema 未覆盖诉求 / 用户放权 / 用户陈述场景" 三个新 pattern, 覆盖第一原则边界).

### 1.2 真信号重复 audit

#### `rerank_system.md` 4 exploit 示例

| 示例 | 演示信号 |
|---|---|
| 潮汕粥汤水清→想喝汤；比另两条油低一档 | 命中 mood + 比较条件化 |
| 蛋白稍弱但你今天想清淡，配粗粮饭凑结构 | 健康风险披露但仍上 |
| 辣度 1 在你耐受内，牛肉粉提鲜，距离最近 | spicy_level 命中 + 距离 |
| 这家 8 个变体里这条蛋白最足、油最低，命中你健身餐需求 | **同品牌择优** (跨候选比较) |

**audit**: 每个 covers 不同信号 (mood / 健康折中 / spicy+距离 / 同品牌择优). **第 4 例**是 §99-102 比较条件化规则 "若候选输入有同品牌多变体" 的硬例证, 不能砍. **第 1 例 + 第 3 例** 都是"命中 + 比较", 信号略重叠但 evidence 不同 (mood vs spicy). **保留 4 例**.

#### `rerank_system.md` 3 explore 示例

| 示例 | 演示信号 |
|---|---|
| 本周第一次粤式早茶，explore 一次，油辣都低 | "近期未吃" + 健康双保 |
| 川菜你常吃但近 3 天没出现，重换口味，不踩 avoid | "常吃但近期没" + 不踩 avoid |
| 沙拉对上 mood=want_light，探索冷盘，蛋白 30g 保底 | mood-explore + 保底 |

**audit**: 每个不同 explore 触发原因. 信号几乎不重叠. **保留 3 例**.

#### `rerank_system.md` 3 ❌ 禁止示例

| 示例 | 演示反 pattern |
|---|---|
| 空泛形容词「营养均衡搭配合理」「好吃可口」「符合你的口味」 | 抽象空话 |
| 脱离用户「这个店评分高」「便宜好吃」 | 不点用户信号 |
| 仅描述菜本身「红烧肉香」「米饭软糯」（没点用户信号） | 仅描述本体 |

**audit**: 第 1 例和第 3 例信号高度重叠 (都是"不点用户信号"). 区别是 "形容词的空" vs "客观描述菜". 可以合并: "脱离用户信号 — 空形容词「均衡」「可口」/ 仅描述菜本身「软糯」「鲜香」". 但合并后失去"评分高/便宜好吃"这种**脱离个人**的反例, 跟"空泛形容"不同维度. **结论: 3 例都保留, 信息有微妙差异**.

#### `parse_refine_intent_v2.md` 10 例 audit

| # | 示例 | 演示 slot/规则 |
|---|---|---|
| 1 | 想吃点湖南菜, 然后肉多一点 | cuisine_want + ingredient_want |
| 2 | 今天想来点辣的, 不要日料, 30 块以内 | expanded + cuisine_avoid + price_max |
| 3 | 上一组都不要, 别再给我萨莉亚, 也别要油炸的 | reject_previous + brand_avoid + cooking_method_avoid |
| 4 | 不要烧烤, 也不要生冷的 | cooking_method_avoid 映射 (烤/生/凉拌) |
| 5 | 今天不要油腻的 (走 oil 不走 cooking_method) | 边界规则: "油腻"→ oil="low" 不进 cooking_method_avoid |
| 6 | 比昨天清淡点的 | reference.relation=lighter |
| 7 | 想吃辣但别太辣 (冲突表达) | 冲突 → slot 空 + raw_understanding |
| 8 | 不要面条 (schema 未覆盖) | 字段闭包: 不抽 food_form_avoid, narrative 兜底 |
| 9 | 随便, 你看着来 (用户放权) | 全空 + raw_understanding 标"放权" |
| 10 | 今天加班好累 (陈述场景, 无诉求) | **禁止脑补** "加班→外卖" |

**audit**:
- 1-6 是不同 slot 直接命中 (核心训练样本)
- 7-10 是边界 / 反 pattern (冲突 / 字段闭包 / 放权 / 禁止脑补), **都是 D-094 实施新加**, 防 LLM 走偏的关键护栏
- 任一 covers 独立场景, **真砍下来损失大**

### 1.3 推荐 (项 A)

**结论: 砍 0 例, 不动**. 现有 10+10 例都有明确护栏作用. 不做机械数量目标. 把 brief 附录 B 这条收入 BACKLOG, **下次 prompt 实际拍 token 价时再 revisit** (LLM 真实表现 > 拍脑袋砍).

**待 codex 拷问**: 是否有更细的信号重复审计漏掉的? exploit 4 例第 1+3 是否能合并成 1 例?

---

## 2. 项 B — 多 cache breakpoint

### 2.1 现状

| 调用 | breakpoint 数 | 内容 |
|---|---|---|
| rerank.py | 1 | system (~148 行) + tools schema 整段 ephemeral cache |
| refine_intent_v2.py (D-095 刚加) | 1 | system (template_head, ~170 行) ephemeral cache |

Anthropic 支持 **4 个 cache breakpoint** (`cache_control: {type: "ephemeral"}` 在 system 或 user content blocks 任意 4 个位置).

### 2.2 rerank user_msg 结构 audit

`chisha/rerank.py:517-540` `build_user_message`:

```
[CONFIG] n=5 n_explore=2        ← 几乎不变 (~30 字符)
[PROFILE]                        ← 跨次推荐一天内不变 (~1-2k tokens, l1_prefs / taste_description / avoid_dishes / l0_protections / mood baseline)
[CONTEXT]                        ← 每次变 (~200-500 tokens, mood snapshot / last_feedback chips)
[CANDIDATES]                    ← 每次完全变 (~3-5k tokens, top60 combo 紧凑文本)
```

**真有 ROI 的拆点**:
- 第 2 个 breakpoint 放 `[CONFIG] + [PROFILE]` 末尾 (假设 5 分钟 TTL 内连续推荐, profile 不变, 这段可命中)
- 第 3 个 breakpoint 放 `[CONTEXT]` 末尾? 但 context 每次推荐都变 (新 mood / 新 feedback chip), cache 命中率低
- 第 4 个 breakpoint 放 `[CANDIDATES]` 末尾? candidates 每次完全不同, 没意义

**结论**: 真有 ROI 的只有 1 个新 breakpoint — `[PROFILE]` 段尾.

### 2.3 ROI 估算 (rerank)

| 场景 | 现状 cache | 加 [PROFILE] breakpoint | 增量 |
|---|---|---|---|
| 用户 5 分钟内连续推荐 2-3 次 (典型 refine 链路) | system ~5k tokens cache_read | system + profile ~7k tokens cache_read | +2k tokens 每次 |
| 跨时段推荐 (>5 分钟) | system 命中 (TTL 5min) | system + profile 命中 | 同样 +2k |
| 单次推荐 | system 写入 | system + profile 写入 | 首次 +2k 写入成本 |

5 分钟 TTL 内连续 refine 链路 (用户连点 2-3 次 refine), profile 不变 → 命中率高. 单用户每天 refine 频率不高, 但 refine→refine→refine 这种连续场景刚好踩在 TTL 内.

### 2.4 实施所需

需要 anthropic_api / openrouter provider 支持 **user message content blocks** (现在 `messages=[{"role": "user", "content": <string>}]`, 要改成 `content=[{"type":"text", "text": ..., "cache_control": {...}}, ...]`).

`chisha/llm_providers/anthropic_api.py:39` 当前硬编码 string content. **需扩 call() 签名** — 加 `user_cache_breakpoints` 参数让调用方指定 user_msg 内拆点位置. 这是 low-level provider API 改动, **可能 scope bleed 到 llm_client.py + 两个 provider**.

### 2.5 风险红线 (项 B)

**high-risk 文件白名单触碰**:
- `chisha/rerank.py` — build_user_message 改返回值类型 (string → blocks) 或新加并行函数
- `chisha/llm_client.py` — call_text 签名扩
- `chisha/llm_providers/anthropic_api.py` + `openrouter.py` — provider call 签名扩

3 个 high-risk 文件 + 1 个 low-risk 调度层. **CLAUDE.md 强制流程**: 设计 codex 共商 (本步) + commit 前 codex diff review.

**baseline_l2_snapshot 守门**: rerank 输入构造改了, 但发到 LLM 的最终 prompt 内容应该 1:1 不变 (只是 cache_control 元数据加进去). baseline 应 0 diff.

**ROI 实测要求**: 改完后 5 分钟内连续 refine 2-3 次, 看 trace.cache_read_input_tokens 是否多 ~2k. 若实测不增, 说明 Anthropic 端没把 user content block 加入 cache prefix, 要 revert.

### 2.6 待 codex 拷问 (项 B)

- (Q1) Anthropic 多 cache breakpoint 是不是真支持 user content blocks 加 cache_control? 文档 cite 一下 OR 我有错觉?
- (Q2) [PROFILE] 段一天内真的不变吗? l1_prefs 是否会因为反馈而 invalidate (更新触发 5min TTL 内 cache miss)?
- (Q3) cache_control 元数据加在 user content block 上会不会破坏 prompt 解析? (LLM 收到的 logical content 应该不变, 只是 metadata 加 cache hint)
- (Q4) refine_intent_v2 是不是也能加第 2 个 breakpoint? 还是 1 个够 (用户文本太短没必要)?
- (Q5) openrouter 透传 Anthropic 模型时, user content blocks 的 cache_control 是否真生效? (Anthropic 直连应该没问题, OR 中转需确认)

---

## 3. 工程量粗估 + 子任务草拆 (待 /plan-brief)

| 任务 | 工作量 | high-risk | 内容 |
|---|---|---|---|
| **项 A 不做** (推荐) | 0h | — | 收入 BACKLOG, 下次拍 token 价时 revisit |
| T-PR3b-01 · provider 层支持 user content blocks + cache_breakpoints (anthropic_api + openrouter) | ~3h | high | call() 签名扩, 加 user blocks 模式 |
| T-PR3b-02 · llm_client.call_text 透传 user_cache_breakpoints kwarg | ~1h | high | 单层透传, 不动业务逻辑 |
| T-PR3b-03 · rerank.build_user_message 加 [PROFILE] 段尾 cache breakpoint | ~2h | high | 改返回 (string vs blocks) 或加并行 API |
| T-PR3b-04 · 单测加固 (assert 调用时 user_cache_breakpoints 正确传入) | ~2h | low | mock provider 看入参 |
| T-PR3b-05 · 实测 5 分钟连续 refine 链路 trace.cache_read 增长验证 | ~1h | low | 拿到验证数据再决定是否 commit |
| **项 B 总** | **~9h** | **3 high-risk** + 验证 | |

---

## 4. 落地流程

1. **本文件 v1 草稿** = 本提交 (志丹同意推进 + 起 brief, 等 codex 共商)
2. 志丹 review brief 内容
3. 调 `codex:rescue` 共商方案 — 重点拷问 §2.6 Q1-Q5
4. codex 共识达成 → 决定:
   - 项 A 是否真砍 0 例还是有更细审计
   - 项 B 是否真有 ROI (Q1/Q5 任一答 NO 就砍)
5. 若项 B ROI 确认 → `/plan-brief docs/proposals/2026-05-21-prompt-step3-cache-and-examples.md` → 拆 specs/T-PR3b-*.md + 追加 tasks.json
6. 实施 + Codex commit-前 diff review
7. 实测验证 (≥2k tokens cache_read 增长) → 落 D-XXX

---

## 附录 A: brief 附录 B Step 3 完整清单 (引用)

```
Step 3 (压缩 + 加速):
- 🔴 refine cache bug: refine_intent_v2.py:418-421 → 修 call_text 拆 system/user
   ✅ D-095 实施完成 (2026-05-21)
- L3 input top-K 60 → 40 (D-046 实测 31-60 仅 3 新候选, 边际低)
   ❌ 砍, 跟 D-047 实测矩阵冲突 (本文件 §0)
- rerank/refine reason 示例从 8 例减到 4-5 例
   ⚠️ 项 A — 推荐砍 0, 现状 10+10 例都有护栏作用 (§1)
- 多 cache breakpoint (Anthropic 支持 4 个,目前只用 1 个)
   🟡 项 B — 真 ROI 拆点 1 个 (rerank [PROFILE] 段尾), 待 codex 共商 (§2)
```
