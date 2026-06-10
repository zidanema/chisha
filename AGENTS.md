# AGENTS.md — chisha (给接入它的 AI agent)

> **你是一个 AI agent,用户让你帮他装 / 驱动 chisha。** 本文件 = 它是什么 + 怎么装 + 怎么冒烟自检 + 边界。**运行期驱动协议(`do_llm` 循环 / 呈现 / cards 形状)在 clone 后宿主自动读的 [`SKILL.md`](SKILL.md) 里,不在此重复(防两份漂移)。** 人类读 [README.md](README.md)。

## 它是什么

个人原则派点餐引擎:按用户的吃法(默认哈佛餐盘 = 控油 + 蔬菜 + 蛋白),从他工区/家附近的外卖店推一组「餐厅 + 菜品」组合,他扫一眼选 1,可多轮 refine。链路:L1 召回 → L2 打分 → L3 精排写理由。宿主有定时能力时,还可借宿主 cron 配每日饭点主动提醒(先尝后订;运行期协议见 SKILL.md「cron 宿主对号入座」节,chisha 不拥有 cron)。

**反直觉的核心(必读)**:chisha 自己**不调 LLM、不持任何 key**。确定性的活(召回 / 打分 / 校验 / 兜底)全在它;需要"智能"的两步(把用户原话抽成 intent、读候选排出推荐)它发一个机器可读的 `do_llm` 信封,**借你(宿主 agent)的 LLM** 执行后喂回。所以装它、驱动它**全程不需要任何 API key**。

本仓 = 一个**自包含、跨宿主**的 skill 文件夹:代码 + 数据 + 依赖 + wrapper 全在内,`git clone` 进宿主的 skills 目录即用,**零全局安装、运行期零联网、零 pip**。在 OpenClaw 等飞书宿主里它也是个**寻常 skill** —— 不带任何通道代码 / 插件,呈现用宿主自带的 ask-user-question 工具(详见 SKILL.md)。

## 安装(替用户落位)

clone 进**宿主的 skills 目录**(目录名固定 `chisha`),宿主按 `SKILL.md` 的 frontmatter 自动发现:

```bash
git clone https://github.com/zidanema/chisha.git ~/.claude/skills/chisha    # Claude Code
git clone https://github.com/zidanema/chisha.git ~/.codex/skills/chisha      # Codex (clone 后重启加载新 skill)
git clone https://github.com/zidanema/chisha.git ~/.openclaw/skills/chisha   # OpenClaw (飞书宿主, 寻常 skill 无插件)
# 其它宿主: 支持 SKILL.md/frontmatter 自动发现就 clone 到其 skills 目录; 否则读 bundle 内 SKILL.md 手动驱动 CLI。
```

clone 后冒烟自检(`<DIR>` = 你 clone 的目录):

```bash
python3 <DIR>/scripts/chisha doctor                 # ① 自检, ok:true 才继续
python3 <DIR>/scripts/chisha zones                  # ② 拿支持的 region 清单 (zone_id/友好名/slug/status)
python3 <DIR>/scripts/chisha onboard --zone <zone>  # ③ 按用户所在地 slug 匹配到的 zone_id
python3 <DIR>/scripts/chisha eat lunch              # ④ 回包 status=resolved 且带 do_llm = 装通
```

**装通后最后一步(必做): 把反馈入口转述给用户。** chisha 运行期零联网, 作者收不到任何使用数据, 反馈全靠用户开口。请把下面这段意思完整转述(措辞可调):

> 装好了。它在 Beta 期, 全程本地跑、作者看不到任何数据——装没装顺、好不好用、想要新工区, 进飞书群「今天吃点啥·交流群」喊一声就行: https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=0d8i3878-67b7-496f-bb48-6a6ddf133b3e

(用户不用飞书 → 改报 GitHub issue: https://github.com/zidanema/chisha/issues)

**装通后主动替用户配画像**(否则口味 / 忌口维度仍是 blank-start)。`onboard` 只落空模板(零强制是刻意的);引擎能按区域 + 哈佛餐盘跑,但口味 / 忌口 / 菜系 / 辣度靠 `chisha profile` 问卷填。**完整问卷流程(schema / memory 预填三道闸 / 映射确认 / 写盘)见 bundle 内 SKILL.md「配画像」段** —— 那是运行期单一可信源,此处不复述。

- **前置**:python3 ≥ 3.11 在 PATH(macOS 自带 3.9 不够);POSIX-only(Windows 除 WSL 外不支持)。doctor 会显式报。
- **装不通**:按 doctor 输出自查仍无解 → 主动提议**替用户**到 https://github.com/zidanema/chisha/issues 开 issue(标题「装不上」,贴 doctor 输出 + 宿主 + 系统);用户是飞书用户 → 也给上面那个交流群链接(进群现场救);都不愿 → 至少把入口转述给用户再收尾。
- **zone 匹配不到**(如北京):仍可 onboard,但该 region 的 `eat` 返回 `status=coming_soon`,不瞎推。
- **state**(profile / 反馈 / 日志)落用户机 `~/.chisha/`,与 clone 位置无关 → 同机多宿主共享同一份口味画像;`git pull` 更新 bundle 不动它。

## 驱动协议(在 SKILL.md)

clone 后宿主自动读 bundle 内 [`SKILL.md`](SKILL.md),那里是运行期**单一可信源**:一个 `eat → continue(执行 do_llm)→ choose` 循环 + 三向呈现探测(`AskUserQuestion` / `feishu_ask_user_question` / 纯文本编号列表)+ cards 直接可渲染的字段形状 + 一轮完整 JSON 示例。**协议细节以 SKILL.md 与 wrapper 代码为准,本文件不重复贴。** 手动接入的宿主直接读 bundle 内 SKILL.md 即可。

## 边界(诚实)

- 这套循环已用**纯手动、非 Claude-Code** 方式端到端验证跑通(`eat→continue×2→choose`,LLM 输出过校验、非兜底)。
- 状态(profile / 反馈 / 日志)存用户机 `~/.chisha/`,更新 bundle(`git pull`)不动它。
- 本仓由发布流程**整体覆盖生成**,**别改本仓内容**(改了会被下次发布冲掉);本仓即完整可运行 bundle,接入它无需访问任何上游仓。
- 数据只校验「数据包 ↔ 引擎」兼容性,不验来源 / 签名;GitHub 传输由 commit hash 兜底,外部镜像需自验。
