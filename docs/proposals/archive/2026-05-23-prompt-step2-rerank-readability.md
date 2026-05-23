# Prompt Step 2 · rerank 可读性收口 (3 项)

**状态**: **closed** (2026-05-23 落地完成, 挪 archive). 3 commit: T-PR2-C `2e13ba8` · T-PR2-A `b2657f8` · T-PR2-B `d5fcf3d`. T2 codex commit-前 diff review SHIP 4/4.
**来源**: 2026-05-20 prompt review brief 附录 B Step 2 完整清单
**Scope 限定**: **仅 rerank**。refine v2 砍例 (brief 原项 B) 本轮**不做** — `v1-retire-brief` worktree 正在写 V1 refine 退役计划 (`specs/T-FR-V1-RETIRE.md`), 退役落地会改 `chisha/refine.py / recall.py / score.py / 删 V1 prompt`, 与 refine prompt 同步重写会撞包, 本 session 跳过, 留待退役后单开 brief。
**收口标志**: 本轮做完 → Step 2 (rerank 部分) 关闭; refine 部分留待 V1 退役后启动。Step 4 (model 切换) 仍 BACKLOG。

---

## 0. 不做的事 (scope guard)

- ❌ 不动 `prompts/parse_refine_intent_v2.md` (refine 在另一个 worktree 重构)
- ❌ 不动 `chisha/rerank.py` 的 `_RERANK_TOOL.description` (Step 1 T-PR-05 已收, 是 tool_use 路径的关键容错冗余)
- ❌ 不动 `_CLI_OUTPUT_SECTION` (CLI fallback 路径, 冗余是它的特性不是 bug)
- ❌ 不出 prompt 写作 style guide (单用户 2 prompt 项目, ROI 不足, 直接砍)
- ❌ 不改业务规则 / 不引入新约束 / 不破 D-079 trace 兼容

---

## 1. 项 A · 计数硬约束 6 处重复合并

### 1.1 现状

`prompts/rerank_system.md` 当前 6 处 (实际 grep 命中) 表述了同一条"数量 = n, 比例 = (n-n_explore) : n_explore, 顺序 = exploit 先 explore 后"规则:

| # | 行号 | 段 | 内容 | 是否真冗余 |
|---|---|---|---|---|
| 1 | L14 | §任务 #3 | "前 (n - n_explore) 条 = exploit, 后 n_explore 条 = explore" | 任务定义阶段, LLM 第一次见 exploit/explore 概念 — **保留** |
| 2 | L79-84 | §输出方式 顶部计数硬约束 4-bullet block | "必须正好 n / is_explore=true 正好 n_explore / exploit 在前 explore 在后 / 宁可挑次优中段填满 explore 槽" | **唯一权威源, 保留** |
| 3 | L89 | `is_explore` 字段语义 | "前 (n - n_explore) 条 false (exploit), 后 n_explore 条 true (explore). refine 模式 (n_explore=0) 时全部 false" | tool schema 已有同义 — **砍, 保 `is_explore: bool. 见 §输出方式 计数硬约束`** |
| 4 | L104 | §输出方式段尾 | "数量: 恰好 n 条. exploit 先 / explore 后. 不漏不多. 除非候选不足 n" | 整段在 §输出方式 内部, 重复同段顶部 — **砍** |
| 5 | L139 | §边界 #1 候选不足 n | "返回少于 n 条, 仍 exploit 先 / explore 后. 这是唯一允许少于 n 条的情形" + "不适用于'找不到漂亮的 explore'" | "唯一例外" 是新信息 — **保留**; "仍 exploit 先 / explore 后" 重复 — **砍** |
| 6 | L144 | §边界 explore 槽质量 | "explore 槽质量倾向... 不为新奇牺牲本轮指别选反 taste/avoid 的, 不是凑不齐就少给 — 计数永远先满足" | "不为新奇牺牲本轮" 是不同维度 (质量边界), 不是计数; "计数永远先满足" 是重复 — **砍尾巴**, 主体保留 |

**外部并存** (本轮不动):
- `chisha/rerank.py:55-62` tool `_RERANK_TOOL.description` (英文, tool_use 路径关键容错)
- `chisha/rerank.py:79` tool schema `is_explore.description` (英文, 同上)
- `chisha/rerank.py:121-150` `_CLI_OUTPUT_SECTION` (CLI fallback 路径)

### 1.2 改动方案 (草案)

净改 prompt md 4 行删除 / 改写, 不改语义:

- L89 `is_explore` 字段语义改为: `is_explore: bool. 见 §输出方式 计数硬约束`
- L104 "数量: 恰好 n 条..." 整行删
- L139 删 "仍 exploit 先 / explore 后" 7 字, 例外条款主体保留
- L144 删尾 "—— 计数永远先满足" 8 字, 主体"不为新奇牺牲本轮"保留
- §任务 #3 L14 **不动** (LLM 第一次读 exploit/explore 概念, 砍了会断裂)

### 1.3 风险 + 守门

- baseline_l2_snapshot 0 diff (改的是 system_prompt 字面, L2/L1 不受影响)
- pytest 全套 pass
- **5-10 case rerank L3 sanity check**: 拉真实 trace 跑 dry_run, 看 (1) candidates 长度 = n (2) 前 n-n_explore 是 exploit 后 n_explore 是 explore (3) is_explore 没穿插 — 这是核心容错验证, 必跑
- system 段字面改 → cache_write 失效一次, 第二次起 cache_read 命中恢复

---

## 2. 项 B · §输入格式速查 字段表 + 读法示例砍冗余

### 2.1 现状

`prompts/rerank_system.md:47-75` 共 29 行:
- L47-69 字段表 (8 字段 × 3 列, markdown table)
- L71-75 读法示例 (3 例)

### 2.2 brief 原议 "砍表保 example"

**重新评估**: 直接砍表风险偏大。表里有几个字段定义 example 没覆盖:
- `汤 N` 显示规则 (3-5 才显示, 1-2 省略)
- `processed` 的"未写即 false, 不要凭菜名臆测" — **这条是关键反幻觉指令**, example 里只覆盖正向 (line 75 腊肠), 没覆盖反向"未写就别脑补"
- `grain` 仅 role 含主食时出现 — example 没有主食带 grain 的样本

### 2.3 改动方案 (草案, 待 codex 共商)

方案 P-B-1 (推荐, 中度): 把字段表压成 5-6 行 inline bullet, 保留反幻觉 + 显示阈值 2 条关键约束, 读法示例 3 例不动

```
字段语义 (省略 = 默认值, **不要凭菜名臆测**):
- main: 8 类 (纯素/白肉/红肉/海鲜/蛋/豆制品/主食/汤水), 总显示
- 烹: 8+ 类 (蒸/炒/烤/炸/凉拌/卤/煮/炖), 总显示
- 油 N: 1-5, 总显示
- 辣/甜/汤 N: 1-5, 0/1-2 档省略 (汤 >=3 表示带汤)
- processed: 工业加工肉; **仅 true 时出现, 未写 = false**
- role: 主菜/主食/汤/小食/套餐; 配菜默认省略
- grain: 仅 role 含主食时出现 (糙米杂粮 / 白米 等)
```

整段从 29 行 → 约 12 行, 砍 ~50% token, 保留所有反幻觉关键信息。

方案 P-B-2 (激进, 砍表全保 example): 把上面 7 行也砍, 仅 3 例 + 1 行 fallback "未列字段默认值"。**不推荐** — 反幻觉的 `processed` 未写即 false 不重申 LLM 会脑补。

### 2.4 风险 + 守门

- baseline_l2_snapshot 0 diff
- pytest 全套
- 5-10 case rerank 输出检查: 看 `risk_flags` / `one_line_reason` 是否对 `processed` / `grain` / 汤的判读还正确 — 重点核 LLM 没把"没标 processed 的菜"误判为加工肉, 也没编造 grain 字段

---

## 3. 项 C · 顶部 HTML comment 挪 `prompts/_dev_notes.md`

### 3.1 现状

`prompts/rerank_system.md:1-6` 6 行 HTML comment, ~250 字节 / ~70 tokens:

```html
<!--
DEV NOTE (修改前请读 chisha/rerank.py 的 _patch_system_prompt_for_cli):
- 顶级 "# 输出方式" 标题 是 CLI no-tool 路径替换段的锚点
- 文末含 "select_top_candidates" + "现在等待" 的那行 是末尾指令替换的锚点
- 改这两处需同步 chisha/rerank.py 和 tests/test_rerank.py
-->
```

`SYSTEM_PROMPT_PATH.read_text()` 整文件喂 system_prompt, **HTML comment 进了 token bill** 并且 LLM 看的是原文不被渲染。

### 3.2 信息价值

这段 DEV NOTE 是给"改 prompt 的 agent"看的关键约束 (两个锚点不能动, 改了要同步 rerank.py + tests). brief 提到偶尔被 LLM 当指令 — 但 LLM 主要风险是看到 "DEV NOTE" 字样后不知道这是什么, 不影响输出格式但浪费 attention。

**信息不能砍, 只能挪。**

### 3.3 改动方案 (草案)

新建 `prompts/_dev_notes.md`, 把 DEV NOTE 内容挪过去, 加 file scope 头:

```markdown
# prompts/ DEV NOTES (给改 prompt 的 agent)

> 这个文件**不被加载**, 不进 token bill。改 prompt 前 grep 这里看锚点约束。

## rerank_system.md 锚点 (改后必跑 tests/test_rerank.py)

- 顶级 `# 输出方式` 标题 = CLI no-tool 路径替换段锚点 (chisha/rerank.py:_patch_system_prompt_for_cli)
- 文末含 `select_top_candidates` + `现在等待` 的那行 = 末尾指令替换锚点
- 改这两处需同步 chisha/rerank.py + tests/test_rerank.py

## parse_refine_intent_v2.md 锚点

(后续 V1 退役时再补)
```

同步:
- `prompts/README.md` 索引表加一行 `_dev_notes.md` (状态 = `dev notes (not loaded)`)
- `chisha/rerank.py:_patch_system_prompt_for_cli` 函数 docstring 顶部加一行 `# 参考: prompts/_dev_notes.md` 反向指针 (agent 改 prompt 后改 rerank.py 时也能看到)
- `prompts/rerank_system.md` 第 1 行直接是 "你是「今天吃点啥」的精排员..." (砍 HTML comment 6 行)

### 3.4 风险 + 守门

- baseline_l2_snapshot 0 diff
- pytest 全套 (尤其 `test_rerank.py` 里的 `_patch_system_prompt_for_cli` 锚点匹配测试)
- system 段开头字面变化, cache_write 失效一次

---

## 4. 项目 ROI / token 估算

| 项 | 删除 tokens | 改善 | 风险 |
|---|---|---|---|
| A 计数去重 | ~50 (4 处文字 + 整行) | LLM attention 更聚焦 / 维护成本下降 (改规则只改一处) | low |
| B 字段表压缩 | ~150 (29 行 → 12 行) | system 段小 ~5% / 反幻觉关键约束保留 | medium (检查 processed/grain 判读) |
| C HTML comment 挪走 | ~70 | system 段干净 / token bill 真省 | low |
| **总** | **~270 tokens / system 段 ~5-8% 减重** | | |

cache_write 失效成本: rerank system prompt ~5000 tokens × 1 次 cache_write = 一次性 ~$0.018 (sonnet)。之后所有 rerank 调用 cache_read 命中。**净 ROI**: 每次 rerank 调用省 ~270 cache_read tokens (10% 价格) = ~$0.0001/调用, 调用 ~180 次回本。志丹日常调用频率 ~5-10/天, 1 个月内回本; 主要价值是**可读性 + 维护性**, 不是 token 钱。

---

## 5. Closed Decisions (codex:rescue 2026-05-23 共商收口)

1. **§任务 #3 L14 保留** — exploit/explore 首次语义定义, §输出方式只管计数/顺序约束
2. **L139 压短**: `这是唯一允许少于 n 条的情形；找不到漂亮 explore 仍按计数硬约束填满.`
3. **L144 保留括号"(次于计数硬约束)"**, 删除尾部 "—— 计数永远先满足"
4. **项 B 采用 P-B-3 紧凑 key:value 列表** — 保留 processed 未写=false 不凭菜名臆测 / 汤>=3 / grain 仅主食 等默认规则, 3 条读法示例不动
5. **项 C 文件名 `prompts/_dev_notes.md`**, README 索引为 `dev notes (not loaded)`
6. **不改 chisha/rerank.py** 加反向指针 docstring (high-risk 文件不为 1 行注释碰)
7. **L3 sanity corpus**: logs/recommend_trace + logs/sandbox/recommend_trace 各抽 5 条; 不足用 dry_run 补
8. **3 个独立 commit** A/B/C 分开; B 单独 Codex diff review; 全部完成统一跑 baseline_l2_snapshot

## 6. Task Breakdown (实施清单)

| Task | What | 风险 | 守门 |
|---|---|---|---|
| T1 (A) | 计数硬约束 4 处去重: L89 改引用 / L104 删 / L139 压短 / L144 删尾 | medium | pytest + baseline_l2_snapshot 0 diff |
| T2 (B) | 字段表 P-B-3 key:value 重写, 保留 3 默认规则 + 3 读法示例 | medium | + 10-case L3 sanity + Codex diff review |
| T3 (C) | 删顶部 HTML comment, 新建 _dev_notes.md, README 加索引 | low | test_patch_system_prompt_for_cli + 全套 pytest |
| T4 | L3 sanity corpus runner (各 5 条 trace, 不足 dry_run 补) | low | 只读 |
| T5 | Final gate: pytest + baseline 0 diff + 10-case sanity + 检查未触 high-risk | low / high if 触 | 收口 |

## 7. 历史: Open Questions (codex 共商前的草稿)

1. **§任务 #3 L14 该不该砍?** 我的判断是保留 (LLM 第一次读 exploit/explore 概念的 onboarding), 但 codex 如果觉得 §输出方式段已经讲清楚, 砍也可以。
2. **L139 §边界 "唯一允许少于 n 的情形"** 这条主体保留, 但 "不适用于找不到漂亮的 explore" 的兜底句 (~25 字) 是否真有 LLM 会误判的风险? 砍了让 §输出方式 #4 bullet 兜底是否够?
3. **L144 §边界 explore 槽质量** "不为新奇牺牲本轮" 主体保留, 但 "(次于计数硬约束)" 这个括号说明是否真冗余 — codex 第二意见。
4. **项 B 方案选 P-B-1 vs P-B-2 vs 不动表**? P-B-1 砍约 50% token, 但保留所有反幻觉约束。P-B-2 激进砍, 风险偏高。Codex 也可能给方案 P-B-3 (例如改字段表为更紧凑的 key:value 列表而非 markdown table)。
5. **项 C `_dev_notes.md` 命名** 是否 underscore 前缀够好? Vite/build 工具不会扫?(本项目无 build 涉及 prompts/) 或者命名 `_meta.md` / `DEV_NOTES.md` 哪个更醒目?
6. **项 C 是否同时改 chisha/rerank.py 加反向指针 docstring**? 改 rerank.py 是 high-risk 文件白名单, 加 1 行 docstring 注释虽小但触发 commit-前 codex review。是否值?
7. **守门 5-10 case rerank sanity check** 用什么 corpus? 本地 trace 历史 (`tmp/baseline_traces_*`) 还是新跑 5 个 dry_run? 共识后定 case 集合。
8. **拆 task 粒度** 3 项 1 commit 还是 3 commits? A+C 风险 low 合一个, B 风险 medium 单独走?

---

## 6. 落地流程

1. **本文件 v1 草稿** = 本提交 (志丹 review + 起 brief, 等 codex 共商)
2. 调 `codex:rescue` 共商方案 — 重点拷问 §5 Q1-Q8
3. codex 共识达成 → 定终方案 (项 B 选哪个分支 / 拆几个 commit / sanity case 集)
4. `/plan-brief docs/proposals/2026-05-23-prompt-step2-rerank-readability.md` → 拆 `specs/T-PR2-*.md` + 追加 `specs/tasks.json`
5. 实施 (每 task 走 plan → diff review → Codex commit-前 review for B 项) + baseline_l2_snapshot + sanity case
6. 全部 done → 提交 + 落 D-XXX (或不立 D, brief 自带证据链)
7. Step 2 (rerank 部分) 收口标记: 更新 `docs/BACKLOG.md` 流转记录 + 把本文件挪 `docs/proposals/archive/`

---

## 附录 A: brief 原文 (引用)

```
Step 2 (可读性):
- rerank 计数硬约束在 §输出方式 / §边界 / tool description 6 处重复 → 合并到一处   ✅ 项 A
- refine v2 八例可减到 5 例                                                          ❌ 本轮跳 (worktree 撞)
- rerank 字段表 + 读法示例冗余 → 砍表保 example                                      ✅ 项 B (重新评估为压表保关键约束)
- rerank 顶部 HTML comment 浪费 token + 偶尔被当指令 → 挪到独立 _dev_notes.md         ✅ 项 C
- 双 prompt 风格不一致 → 出 prompt 写作 style guide                                  ❌ 砍 (单用户 2 prompt ROI 不足)
```
