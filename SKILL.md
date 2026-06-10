---
name: chisha
description: "今天吃点啥 — 个人原则派点餐执行外包. 中午/晚上点外卖纠结时用. 基于哈佛餐盘弱约束 (控油+有蔬菜+有蛋白) 从办公区/家附近商家推一组 (稳妥 exploit + 探索 explore), 选 1; 可多轮 refine. 触发词: 吃啥, 吃什么, 午餐, 晚餐, 中午吃啥, 晚上吃啥, 点外卖, 外卖纠结."
---

# chisha 点餐 (零 LLM, 借你的 LLM · 自包含 bundle · 跨宿主)

chisha **不调 LLM** — 它发 `do_llm` 信封, **你 (宿主 agent) 用自己的 LLM 执行**后喂回. 确定性 (召回/打分/校验/兜底) 全在 chisha; 你只做两处智能判断: 抽 intent / 排候选. 命令任意目录跑, 输出 JSON 到 stdout, state 落 `~/.chisha/`.

本 skill **自包含、跨宿主**: 代码 + 数据 + vendored 依赖都在本文件夹, clone 进宿主的 skills 目录即用, **零全局安装、运行期零联网**. 协议层 (CLI verbs + `do_llm` 信封) 通用; **唯一按宿主分支的, 是「怎么把候选/问卷摆给用户」这层呈现** (下面标 ⎇ 的步骤). chisha **不碰任何通道** (不发飞书卡、不渲染 UI、不处理回调) —— 呈现一律用**你手上现成的工具**, 三选一:

- **有 `AskUserQuestion`** (Claude Code) → 用它. 选项 + 自带 Other 自由输入.
- **有 `feishu_ask_user_question`** (OpenClaw 的 openclaw-lark 扩展自带工具) → 用它. **候选卡 schema** 与 AskUserQuestion **同构**: `questions[].{question, header, options[].{label,description}, multiSelect}` (但**无** AskUserQuestion 那种自带可选 Other; refine 入口见 §用-3); **某题 `options` 留空 `[]` = 一道强制必答的纯文本题** (满意的用户也被逼填, 别拿它做"可选 refine 框"); 工具立即返回 `{status:pending}`, 用户提交后宿主把答案当作**下一轮 inbound 消息**推回给你 (形如 `用户回答了你的问题:\n- 问题: 答案`) —— 你**别重复调**, 等那条消息即可.
- **两个都没有** (Codex / 纯 CLI / 其它) → 编号列表纯文本, 用户回数字选、打字提诉求.

**按宿主对号入座** (唯一按宿主分支的是「怎么把候选/问卷摆给用户」; 其余协议 + do_llm 执行完全一致):

| 宿主 | 呈现工具 (摆候选/问卷) |
|---|---|
| Claude Code | `AskUserQuestion` (卡片) |
| OpenClaw (含 openclaw-lark) | `feishu_ask_user_question` (契约同构) |
| Codex / 纯 CLI / 其它 | 编号列表纯文本 |

> `do_llm` 三宿主**一律 inline 直跑** (别起 subagent —— 多一跳编排 + 子代理过度推演反而更慢)。判别只看「你手上有没有这个工具」: 有 `AskUserQuestion` 就 Claude Code 路; 有 `feishu_ask_user_question` 就 OpenClaw 路; 都没有就纯文本。下面标 ⎇ 的步骤按本表分支, 没标 ⎇ 的对所有宿主一字不差。

命令统一走 bundle 内 wrapper (下面记作 `CHISHA`) — 即**本 skill 文件夹**内的 `scripts/chisha`:

```
# Claude Code 宿主:  CHISHA = python3 ~/.claude/skills/chisha/scripts/chisha
# Codex 宿主:        CHISHA = python3 ~/.codex/skills/chisha/scripts/chisha
# OpenClaw 宿主:     CHISHA = python3 ~/.openclaw/skills/chisha/scripts/chisha
# 其它宿主: 替成你 clone 本 skill 的实际目录 + /scripts/chisha
```

## 环境要求

- **python3 ≥ 3.11** 在 PATH (macOS 自带 python3 是 3.9, 不够; 装 3.11+: homebrew / pyenv / uv 均可). wrapper 会硬 guard 低版本并给明确报错.
- **POSIX only** (macOS / Linux). Windows 不支持 (除非 WSL) — core 用 fcntl 文件锁.

## 装 (一次)

skill 文件夹已在宿主 skills 目录 (你正在读它 = 已就位).

**先定 region** (高 stakes: 选错 = 推 50km 外的店). 跑 `CHISHA zones` 拿支持清单, 按用户位置匹配 `slug`, 向用户**轻确认**友好名 ("我看你在深圳, 给你配深圳湾创新科技中心, 对吧?"), 再 onboard:

```
CHISHA zones                      # 支持的 region (zone_id/friendly_name/slug/status)
CHISHA onboard --zone <zone_id>
```

- 用户位置**不在清单** → 仍照常 onboard (--zone 传用户所在地名), 装好待数据上线; eat 会返回"敬请期待"不瞎推.
- **配画像与一次性 onboard 解耦 (D-119)**: onboard 回包带 `profile_configured` —— **`false`(画像还没配, 不管 profile 是新建还是「已存在」) → 主动跑一次下面「配画像」问卷**; `true`(之前配过) 就不打扰. ⚠️ 跨宿主共享 `~/.chisha/`: 别的宿主先 onboard 过, 这次会 status=exists, 但**只要 `profile_configured=false` 仍要主动提**, 别因「已存在」就跳过配画像 (这正是「Claude Code 装了几次都不进 onboard」的根). 问卷很轻: 每道选择题都有「都行/都能吃」选项, 没偏好的一路选「都行」几秒提交; memory 有显式饮食信号就预选默认值.

## 配画像 (画像捕获 · onboard 后 profile_configured=false 时主动提 / eat 回包 profile_status.taste=empty 时也可提 / 用户随时说"配画像")

口味/忌口/爱吃菜系**没有可靠获取路径**时, 推荐永远是 blank-start. 用 `CHISHA profile` 问卷把画像配起来 —— **schema 由 chisha 出 (确定性), 映射 + 校验 + 写盘也由 chisha 拥有, 你只负责: 按 schema 渲染问卷 + (可选)用 memory 预填默认值 + 让用户确认**.

```
CHISHA profile                                     # 出问卷 schema (host 按字段渲染)
CHISHA profile apply --answers '<json>'            # 回传答案 → 映射预览 (不写盘)
CHISHA profile apply --answers '<json>' --confirm  # 用户确认后才落盘
```

流程:

1. **⎇ 按 schema 渲染问卷收答案** —— `CHISHA profile` 回 `questions[]`, 每题自带 `id` / `prompt` / `kind` (`multi_select`·`single_select`·`free_text`) / `options[{value,label}]` / `allow_free_text` / `free_text_hint` / `skippable`. **照这些字段机械渲染即可, 别在这里硬记每题问什么** —— schema 是单一可信源, 问卷会演进。用你手上的 ask-user-question 工具 (见顶部三选一):
   - 答案以题的 `id` 为键回传 (`multi_select`→数组, `single_select`→选中的 `value`, `free_text`→字符串)。
   - **照 `options` 直接渲染成下拉/卡片, 别降级自由文本框** —— chisha 已把每道选择题的选项收到宿主单题上限内 (菜系 9 项 + 「都行」= 10, 贴 feishu `feishu_ask_user_question` 上限; Claude Code AskUserQuestion 上限 4 就取前几项)。**降级成自由文本框正是「菜系列表很少、被迫打字」的病根, 别再这么做。** 飞书 form **每题强制必答**: 用户没有要选的 → 引导他选「都行/都能吃」那个 option (合法的空答案, chisha 映射认作静默不写)。`allow_free_text` 只是给**无下拉能力的纯文本宿主**兜底, 有下拉就别用; 用户报多个值仍**拆成数组**回传 (chisha 逐个按枚举校验, 非法进 `rejected` 不静默放行)。**无工具宿主** (Codex 等) 编号列表 + 回数字/打字。
   - **辣度是「能吃的最高辣度」(上限语义, 非精确档)**: 用户选「中辣」= 微辣/不辣也都接受 (召回按 ≤上限 过滤), label 已写明含义, 照念即可, **别让用户以为要逐档多选**。
   - `mapping_note` 是 chisha 的映射说明 (host 参考, 不必念给用户)。
2. **memory 预填默认值 (可选, 守三道闸)** —— 渲染前扫你自己的 memory, 命中的显式信号**预选成默认值**, 并在确认时 **source-anchor** ("依据你之前说过『不吃牛肉』, 我先勾上"):
   - ① **只取 allow-list 显式信号**: 过敏 / 宗教饮食 (素食·清真) / 明确忌口 / 明说过的爱憎菜系或食材 / **明确的辣度耐受** (如"不吃辣" → 预选 spicy 题里对应的 option). **demographics (职业/地域/年龄) 一律不抽**, 不从人设推口味.
   - ② **只采长期稳定偏好**, 不采 contextual ("今天不想吃辣"不算长期).
   - ③ 拿不准 → **不预选、留空**, 不臆测. 没信号就提交空问卷.
   - **过敏**预填写成 `"过敏:花生"` (chisha 据此分流到医学级永不可破); 随口提到的不加 `过敏:` 前缀, 不会被误升级.
   - **辣度**明确时走专门的 spicy 题 (进召回硬过滤), **别塞进口味自由文本** —— 自由文本只进 L3 软提示, 挡不住辣菜召回.
3. `CHISHA profile apply --answers '<json>'` (**先不带 --confirm**) 拿映射预览: `writes` (将写哪些字段) + `rejected` (没采纳的 + 原因). 把 `summary` 念给用户确认 ("我会记: 素食→身份饮食永不可破 · 不吃海鲜 · 爱吃川菜/日式 · 辣度=不吃辣 · 口味=少油, 对吗?").
4. 用户确认 → 同一份 `--answers` 加 `--confirm` 落盘; 要改 → 调整答案重走第 3 步. **用户想跳过整张问卷就跳过** (空问卷无害, 守 onboard 零强制).

**写权限边界 (硬规则)**: 结构化字段 (忌口/菜系/身份饮食/过敏/口味) **一律走 `CHISHA profile apply`, 你不徒手编辑 `~/.chisha/profile.yaml` 的结构化字段** —— 映射跨 L0 与偏好层 (素食≠食材黑名单), chisha 确定性拥有, host 脑补易错档. 非法值 (不在枚举) chisha 会**拒写并报原因**, 不静默放行.

## 用 (一个循环, 下面 `CHISHA` = 上面那条 wrapper 命令)

1. 判 meal (11:00–15:00 → `lunch`, 其余 `dinner`; 拿不准问用户). **判吃饭地点**: 用户提到具体
   地点 (出差/换区, 如"明天去景湖/北京吃") → 先 `CHISHA zones` 拿清单, 把地点按 `slug` 匹配到
   `zone_id`, eat 带 `--zone <匹配到的 zone_id>` (临时覆盖, **不改 profile 默认**); 没提地点就
   不带 (走 profile 默认区). 有诉求原话另带 `--context`:
   `CHISHA eat <lunch|dinner> [--zone <zone_id>] [--context "用户原话"]`
   - 地点**匹配不到清单** (如北京) → 仍把用户说的地名原样当 `--zone` 传 (chisha 会回 coming_soon,
     下一步念"敬请期待"); 可顺带说一句清单里**已支持**的区。**绝不**因未覆盖就拿 profile 默认区的店
     硬推成异地推荐 —— 那是幻觉, 是这条协议要堵的根。
2. **循环**: 回包带 `do_llm` 就执行它 → 喂回 → 直到 `status=ready`.
   - 若回包 `status=coming_soon` (region 未覆盖 / 待上线): 把 `message` 念给用户 (敬请期待), **到此结束** — 没有 cards、不要 continue.
   - **⎇ 执行 `do_llm` (三宿主统一: inline 直跑, 不起 subagent)**: 直接用你自己的 LLM **inline** 执行 do_llm, **别起 subagent** —— 起 subagent 比 inline 多一整跳编排 + 把信封重载进子上下文 + 子代理易过度推演, 反而更慢; 一次性出卡也不在乎主上下文那点候选 JSON. 严格按 `do_llm.system` + `messages` 忠实执行 (读里面的 `[PROFILE]`/`[CONTEXT]`/硬约束如辣度耐受; 拿不准就保守选、在 narrative 如实说明, 别脑补"已避开"). **别**用 Bash/python 拆候选、别自己摘 profile. 产出符合 schema 的**裸 JSON** (第一个字符就是 `{`), 不要 markdown/解释, 不要手包 `{correlation_id, payload}` 信封:
     - `operation_kind=extract` → intent 对象 (没把握映射进 slot 的诉求写 `raw_understanding`, 别回传 raw_text).
     - `operation_kind=rerank` → `{candidates, narrative}`, 挑 5 条 (R1: 3 稳妥 + 2 探索; refine 轮全稳妥).
   - **rerank 别空转 (省时关键)**: `[CANDIDATES]` 已按 fit_score 由高到低排好序, 你只需挑前几条、把末 n_explore 条标 explore、各写一句 `one_line_reason`、同 brand 至多 1 条 —— **不要逐条复算分数 / 写长篇分析 / 列推理过程**, 直接吐 JSON. 这步无需 extended thinking (开 thinking 会把 10 秒的活拖到上百秒).
   - 喂回 (`--step` 回显上一步回包**顶层**的不透明 token):
     `CHISHA continue --id <rid> --result '<裸 JSON>' --step <step_token>`
   - 若回包带 `intent_disclosure`, 记下 `raw_understanding` 里值得告诉用户的点 (稍后呈现带一句).
3. `status=ready` → 先按 `profile_status` 报一句画像状态 (区域 {region.friendly_name} · 哈佛餐盘 · 口味{taste.state: set→已设 / empty→未设}; 字段缺失/null 就跳过, 别硬读)。**`profile_notice` 硬规则 (once_per_session, 别凭感觉跳)**: 回包带 `profile_notice` 且**本 session 你还没念过它的 `once_key`** → 摆 cards **前**必须先把 `message` 念给用户 (软性邀请补口味/配画像); 这个 `once_key` 本 session 已念过 → 跳过不复念。同一餐多轮 refine 共用一个 `once_key` (只念一次); 新开一餐换 `once_key` (再念一次)。若回包带 `staleness_notice` → 摆完 cards 后在末尾附一行 `💡 {staleness_notice.message}` (数据陈旧软提示, notify-don't-force; **别因此不出推荐**, 用户想刷新可自行跑 `CHISHA update` —— 需 VPN/HTTP 代理, 纯 SOCKS 不支持)。再 **⎇ 摆 `cards` 给用户选** (点餐硬性交互, **必带 refine 入口**; 用你手上的 ask-user-question 工具, 见顶部三选一):
   - **Claude Code `AskUserQuestion`** / **openclaw-lark `feishu_ask_user_question`** (候选卡写法一致): 一道单选题, 每个候选一个 option —— **`label` 必须以 rank 前缀保证唯一** (如 `1. 餐厅+主菜`; 两家店主菜重名时纯名字会撞, 工具回传只给 label 字符串, 撞了你映射不回 card.id), `description`=¥总价 · 一句理由 · 健康点 (`is_explore=true` 的在 label/description 标"探索"). **出题前先在心里建好 `label(或 rank) → cards[].id` 映射**, 收到答案按它定位 card.id。**严禁**在有工具时改用纯文本复述替代候选卡 (那样用户没法点选)。
     - **refine 入口 (两端不同, 别搞混)**:
       - **Claude Code**: 用每题自带的 **Other/自由输入**, 用户在 Other 里打诉求即可。
       - **openclaw-lark feishu**: feishu **没有**自带可选 Other; 且**别**为 refine 再弹一张输入卡 (那要多一次宿主大模型往返, 慢、体验差)。正解 = **摆候选卡的同时(同一轮内, 别为此单独再起一轮)配一条 refine 引导文案**, 让用户知道"想换直接回我一句"; 用户在会话回一句 (如「想吃川菜」「换牛肉」) 就是 refine, 你按 §用-5 续轮。引导文案 (照抄, 示例方向可微调, 别框死自由表达):
         > 不合胃口?直接回我一句就行：
         > 换菜系（川菜/湘菜）· 换口味（重口/清淡/辣）· 想吃啥肉（牛肉/鸡肉/海鲜）· 便宜点 · 换一批
   - **Codex / 其它无工具的宿主**: 把 cards 摆成**编号列表** (每行 `N. 餐厅 + 主菜 — ¥总价 · 一句理由 · 健康点; explore 的标"探索"`), 让用户**回数字**选某条; 用户**直接打字提新诉求** (如"想吃辣"/"换一家") = refine 入口. 别假装有卡片 UI、别替用户选.
4. 用户选某卡 / 回某号 → `CHISHA choose --id <rid> --card <cards[].id> --action accept` (工具回传的是 label/数字, 按上一步建好的映射换回那条 card 的 `id`, **别把 label 当 card_id 传**); 明确不吃 → `--action skip`.
   - **用顺手后才提主动提醒 (先尝后订)**: 用户**首次 accept 成功**后 (真用了一回、尝到价值), 若你 (宿主) 有定时能力 (Claude Code routines / openclaw cron) → 可顺势问一句"要不要我每天这个点主动给你配好", 要 → 按下面「cron 宿主对号入座」节配。**别在 onboard 当场问** (那会儿没体验, 转化低又显冒昧), 也**别每轮都问** (问过没要就别再烦); 无定时能力跳过。
5. refine: 用户给新诉求 (如"再辣点"/"换一家") → `CHISHA eat <meal> --context "新诉求" --from <rid>` (回到步骤 2). 出差/异地那轮起的 refine **带上同一 `--zone`** (漏了 chisha 也会从上轮继承, 但显式更稳).

## 一轮完整示例 (信封 → 你回传的裸 JSON → cards)

真实链路, 帮你对齐"到底回传什么形状"。`…` = 截断的长字段 (实际更长)。

**① `CHISHA eat lunch --context "想吃辣别太贵"`** →
```json
{ "ok": true, "recommendation_id": "20260602_lunch_xxxx",
  "status": "pending",                                   // pending待extract / resolved待rerank / ready出cards / coming_soon未覆盖
  "operation": "extract",
  "step_token": "20260602_lunch_xxxx::R1::extract",      // ← 顶层, 与 do_llm 同级; continue 要原样回显
  "do_llm": { "operation_kind": "extract", "output_mode": "text_json",
    "system": "# refine 意图解析员 prompt …(内含 schema 与 [PROFILE]/[CONTEXT], 忠实执行)…",
    "messages": [ { "role": "user", "content": "想吃辣别太贵\n…" } ],
    "required_validation": [ "schema_version == '2.1'", "…" ],
    "json_schema": { "…": "intent 对象的 schema" } } }
```

**② 你的 LLM 跑完 do_llm, 回传裸 intent JSON** (无 markdown / 无外包信封):
```json
{"redirect":{"cuisine_want":[],"cuisine_avoid":[],"cuisine_candidates_expanded":["川菜","湘菜","贵州菜","重庆菜"],"ingredient_want":[],"ingredient_avoid":[],"brand_avoid":[],"cooking_method_avoid":[],"staple_want":[],"staple_avoid":[]},"constrain":{"oil":null,"price_max":40,"price_band":null,"wants_soup":false},"reference":null,"reject_previous":false,"raw_understanding":"想吃辣预算40","schema_version":"2.1"}
```
喂回 (`--step` = 上一步顶层的 step_token):
`CHISHA continue --id 20260602_lunch_xxxx --result '<上面整段裸 JSON>' --step 20260602_lunch_xxxx::R1::extract`

**③ 回包 `status=resolved` + rerank do_llm** (这次 `output_mode=tool_use`, `tools[0].name=select_top_candidates`; `messages` 里有 `[CANDIDATES]` 列表 + `[CONFIG] n=5 n_explore=2`; `step_token` 变 `…::R1::rerank`)。回传裸 JSON (= tool 入参形状):
```json
{"candidates":[
  {"rank":1,"is_explore":false,"combo_index":7,"fit_score":0.82,"taste_match":0.7,"risk_flags":[],"one_line_reason":"川辣牛肉, 控油尚可"},
  {"rank":2,"is_explore":false,"combo_index":3,"fit_score":0.78,"taste_match":0.7,"risk_flags":[],"one_line_reason":"…"},
  {"rank":3,"is_explore":false,"combo_index":12,"fit_score":0.74,"taste_match":0.6,"risk_flags":[],"one_line_reason":"…"},
  {"rank":4,"is_explore":true,"combo_index":21,"fit_score":0.66,"taste_match":0.5,"risk_flags":[],"one_line_reason":"探索·贵州酸辣"},
  {"rank":5,"is_explore":true,"combo_index":30,"fit_score":0.61,"taste_match":0.5,"risk_flags":[],"one_line_reason":"探索·重庆小面"}
],"narrative":"按想吃辣+预算40, 排了3稳妥2探索"}
```
约束: 前 `n-n_explore` 条 `is_explore=false` 在前、后 `n_explore` 条 `true` 在后、**不穿插** (refine 轮 `n_explore=0` 全 false); `combo_index` 取自 `[CANDIDATES]`, 不重复不越界; 同 brand 至多 1 条。喂回同样带 `--step …::R1::rerank`。

**④ 回包 `status=ready` + `cards`** (字段已齐, 直接渲染, 不再调 LLM):
```json
{ "status": "ready", "fallback": false,
  "profile_status": { "region": {"friendly_name":"深圳湾创新科技中心"}, "taste": {"state":"empty"}, "methodology": {"friendly_name":"哈佛餐盘"} },
  "cards": [ {
    "id": "c_0_r_4857923226",                            // ← choose 用这个 id
    "rank": 1, "is_explore": false,
    "restaurant": { "name": "Super Model 超模厨房", "distance_m": 3500, "eta_min": 30 },
    "dishes": [ {"canonical_name":"炙烤银鲷鱼套餐","price":31.8}, "…" ],
    "total_price": 37.6, "estimated_total_oil": 1.3, "estimated_total_protein_g": 40,
    "reason_one_line": "低油1.3, 蛋白40g" }, "…" ] }
```
摆给用户选 (Claude Code `AskUserQuestion` / openclaw-lark `feishu_ask_user_question` / 无工具时编号列表) → 用户选定 →
`CHISHA choose --id 20260602_lunch_xxxx --card c_0_r_4857923226 --action accept`

## cron 宿主对号入座 (主动饭点提醒 · 借你的 cron, chisha 不拥有)

**先定时机 (先尝后订)**: 别在 onboard 当场推这个 —— 用户还没尝到一次推荐的价值, 这会儿要他承诺"每天后台提醒"转化低又显冒昧。等他**用顺手了** (至少 accept 过一回, 见「用」第 4 步触点) 再顺势提; 用户随时主动说"每天提醒我"也算。下面是"确定要提"之后的数据契约 (谁注册、措辞、节奏仍全是你宿主的事)。

跟上面「按宿主对号入座」同精神: chisha 探测不了你有没有 cron, 所以这一节只是**引导文本** —— 你读到后按"我有没有定时能力"自己决定提不提。**chisha 自己不带任何 cron / 调度 / push**, 这节只说**数据契约** (哪个时点跑哪个 meal、环境 context 塞哪个 flag、提醒怎么带标识让用户回选)。**节奏 (何时发)、措辞、谁注册 cron、用不用 cron, 全是你 (宿主) 的事** —— 别把它当编排脚本照搬, 也别把"主动推送"那套渲染卡/调通道的逻辑换个壳搬回来。

| 宿主 | cron / 定时能力 |
|---|---|
| Claude Code | routines / scheduled agents |
| OpenClaw | `openclaw cron add` |
| Codex / 纯 CLI / 其它 | 多半无 → 整节跳过, 无害 |

**一个 cron job = 一个 agent turn = 跑上面「用」那段标准 eat 循环** (一字不差, 没有任何 chisha 侧新链路)。两条数据契约:

1. **meal 由时点定死** (注册 cron 时就定, 别在 turn 里现判): 午间 job → `CHISHA eat lunch`, 晚间 job → `CHISHA eat dinner`。
2. **触发时收集富 context** (有哪个能力用哪个, 没有就跳, 不阻塞 —— 同「对号入座」精神):

   | context | 来源 (你手上的能力) | 塞到哪 |
   |---|---|---|
   | 餐段/时间 | cron 注册时定死 | `eat <lunch\|dinner>` |
   | 出差/在外地 | 查日历 (如 lark-calendar) / 对话历史 | `--zone <匹配到的 zone_id>` (匹配不到→原样传地名→chisha 回 coming_soon) |
   | 天气 (降温/炎热/雨) | 你的天气工具 / MCP | `--context "天气冷想喝热汤"` (extract 映射 wants_soup) |
   | 健康/减脂/生病 | 你的 memory / 最近对话 | `--context "感冒了想清淡少油"` (映射 oil 约束) |
   | 近期口头偏好 | 对话上下文 | `--context "这周吃腻了快餐"` (进 raw_understanding 软提示) |

   chisha 只**列清单 + 给映射示例**; do_llm extract 能映射的进 intent slot, 不能的进 `raw_understanding` 给 L3 看。揉进一条 `--context` 即可: `CHISHA eat lunch --zone <z> --context "降温了 + 感冒想清淡"`。

**呈现 + 续轮 (cron 场景关键, 别漏)**:

- cron turn 多半**没有实时交互** (你不在用户面前摆卡) → 出 `status=ready` 后用**纯文本提醒**播报候选 ("中午好, 今天给你配了 3 家: 1.… 2.… 3.…, 想点哪个回我个号")。**绝不**重建飞书卡 push / 调任何通道。(若该 turn 恰好有交互工具且用户在场, 才摆 cards, 同「用」第 3 步。)
- **提醒文本必须带本轮 `recommendation_id`** —— 这个 cron turn 发完提醒就结束了; 用户晚点回"选 1 / 第一个"是**新 turn**, 手上**没有 cards 上下文** (card.id 已不在记忆里)。
- 用户回选 → 新 turn 跑: `CHISHA choose --id <提醒里的 recommendation_id> --rank <用户说的号> --action accept`。**`--rank N` 是 `--card <id>` 的别名**, 按候选 rank 号定位 (1 = 第一条), 专治这种"只剩号 + rid"的续轮。用户说"不要第 N 个" → 同样 `--rank N --action skip` (skip 也按号)。用户整体没回 / 说"都不想吃" → **就别 choose** (不记 = 自然忽略, 别硬塞一个 skip; rank 是当前呈现里的号, 越界会报错)。
- 用户提新诉求 (如"太贵了换便宜的") = 正常 refine: `CHISHA eat <meal> --context "新诉求" --from <recommendation_id>` (回「用」第 2 步)。

> 一句话守则: chisha 出推荐**数据**, 你的 cron 决定**节奏**, 你的工具决定**呈现**。三者不混。

## 注意

- 上面 `CHISHA` 是占位 —— 实跑替成**本 skill 文件夹**内的 `scripts/chisha` (Claude Code: `~/.claude/skills/chisha/scripts/chisha`; Codex: `~/.codex/skills/chisha/scripts/chisha`).
- `--result` 传 LLM 的**原始输出 JSON** (raw payload), **不要**手包 `{correlation_id, payload}` 信封; `--step` 直接回显上一步回包**顶层**的 `step_token` 字段 (与 `do_llm` 同级, 不在 do_llm 里面; 漏了/抄错 → chisha 报错, 重发即可).
- `fallback=true`: 你的产出没过 chisha 校验, 它按规则兜底排了 — 如实告诉用户"这次按规则排的", 别套你的 narrative.
- chisha 报 `ok=false` + `error` → 把 `error.message` 念给用户, 别硬编. 自检: `CHISHA doctor` (sandbox 全局启用时 CLI 拒绝跑, 先去 sandbox-lab disable).
- python3 报版本/依赖错 → 跑 `CHISHA doctor` 看自检详情 (python 版本 / vendored pyyaml / install_root / manifest).
- 通用 agent 端本轮只需要 `choose accept/skip`: accept 会写选择历史 + meal_log, 用于后续已吃历史 / 多样性; 好评 / 差评短链路目前只有 Web 反馈入口. agent/飞书宿主没有专门反馈 UI 时, 别臆造星级反馈, 如实只做选定 / 跳过.
- **OpenClaw / 飞书宿主**: 无需任何特殊命令 —— 你就是个普通 skill. 呈现用 openclaw-lark 自带的 `feishu_ask_user_question` (见顶部说明), refine 用户直接打字续轮 (§用-5). 没有 push / actions / card_state 这类通道命令, 也没有要装的飞书 plugin.
