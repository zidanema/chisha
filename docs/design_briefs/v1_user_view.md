# chisha「今天吃点啥」V1 用户视图 · claude.ai/design Brief

> 用法：把这整份文件粘进 [claude.ai/design](https://claude.ai/design)，让它出 React + TypeScript + Tailwind 组件源码。**两份 brief 不要合并**：本 brief 仅覆盖**用户视图**（路由 `/`），调试台（路由 `/debug`）见 [v1_debug_view.md](v1_debug_view.md)（待写）。
>
> 本 brief 锁定决策见 [DECISIONS D-051](../archive/DECISIONS_phase0.md#d-051)（2026-05-15）。
>
> ---
>
> ## 2026-05-15 更新 · 原型迭代后落地决策
>
> claude.ai/design 协同迭代后追加了 4 条用户视图决策（**改 home 主页前必读**）：
>
> - **D-052** Accept 信号去 deeplink，改持久 inline 锁定 + 复制店名
> - **D-053** Refine 历史从底部列表升级为顶部面包屑 + smooth-scroll；输入框置顶、chip-fallback
> - **D-054** Skip-meal escape hatch（6 reason chip + "不说原因" 兜底，新增 `POST /api/skip`）
> - **D-055** 同 session 抑制 unfed banner（`unfed.session_id === current.session_id` 时不渲染）
>
> 文案规范 + 视觉系统抽到 [`docs/style-guide.md`](../style-guide.md)；前后端契约见 [`docs/api.md`](../api.md)；落地代码在 [`apps/web/`](../../apps/web/)。
>
> 本 brief 下面 §5/§6 的旧版本"3 卡片 + 备选折叠 + 底部 refine 历史"已被 D-052~D-053 推翻，**以 DECISIONS 为准**。
>
> ---

---

## 1. 项目背景（自包含，请仔细读）

**chisha**（中文项目名「今天吃点啥」）是一个**个人 AI 餐饮推荐系统**，跑在本机 localhost，单用户无认证。它的核心承诺：

> 每天中午晚上 30 秒内决定吃啥，吃得「控油 + 有蔬菜 + 有蛋白」。

**它不是什么**：不是大众点评、不是美团、不是营养追踪 APP、不是社交分享平台、不是 SaaS。

**用户唯一**：本项目作者，工程师，在做减脂增肌（标准体重 → 目标体重），同时在做臀部康复。**全程他自己一个人用**——不要做注册、登录、协作、分享、公开榜单。

---

## 2. 用户画像（决定 UI 风格）

| 维度 | 值 |
|---|---|
| 年龄/职业 | ，某大厂技术中台负责人 |
| 技术水平 | 后端高级 + AI/ML 中高级 + GIS 行业专家 |
| 审美偏好 | 工程师审美，喜欢 Linear / Vercel / Notion 风格 |
| 反感 | 小红书风、过度营销、emoji 堆砌、儿童化插画、卡路里数字焦虑 |
| 信息密度 | 偏好高密度。能在一屏内看完 3 推荐 + 三件套达标徽章 + 价格 + ETA + 一句话理由 |
| 决策风格 | ENTP，快速决策，不喜欢被引导填一堆问卷 |
| 设备 | 主用 MacBook Pro 13"（M3）+ 偶尔手机查看 |

**别学这些 UI**：薄荷健康（太重图表）/ Keep（健身风太重）/ 美团（信息太杂）/ Cron Calendar（太空）

**学这些 UI**：Linear Dashboard / Vercel Deploy 页 / Raycast 设置页 / Notion AI 块 / GitHub Copilot UI

---

## 3. 使用场景（决定信息层级）

### 场景 A · 工作日 11:25（最高频）

> 11:25 macOS 自动拉起 localhost 服务并打开浏览器 → 用户瞥一眼 3 卡片 → 选一个 → 点击「就这个」按钮 → 跳转大众点评/美团 APP 完成下单 → 关浏览器回工作。
>
> **总时长目标：30 秒以内**。

### 场景 B · 想换个口味时

> 11:30 看完 3 个推荐都不满意 → 在页面输入框写「今天想吃辣的」/「不想吃汤水」/「换日料」→ 提交 → 页面刷新出新的 3 张卡片。
>
> 自然语言追加约束 = **refine**。不是另起一轮，是在当前 session 内迭代。

### 场景 C · 饭后反馈（14:00）— **独立动线**

> 吃完饭回工位 → 重新打开 chisha 主页 `/` → 看到顶部 banner 「中午吃的"粤牛"怎么样？5 秒反馈一下 →」→ 点击 banner → 跳到独立反馈页 `/feedback/<id>` → 看到当时推荐的 5 张卡片，默认选中你点的那个 → 评分 + chip + 备注（可选）→ 提交 → 跳回主页。
>
> **总时长目标：5 秒以内**。
>
> **关键：饭后反馈与饭前推荐是两个独立 task**。用户的 mental state 完全不同（决策态 vs 回顾态），不能塞在同一页面。

### 场景 D · profile 查看 / 调整（低频）

> 推荐了几天后觉得"老推那几家"或者"忽略了我说的想吃辣"→ 点击主页顶栏右上角 ⚙️ profile → 进入 `/profile` 页面，**默认是只读 YAML 视图**（用户可以快速看一眼当前的 taste_description / avoid_dishes 等关键字段是什么）→ 如果要改，点「编辑」切到表单 → 改完保存 → 自动切回只读视图查看新结果。
>
> **频率**：调推荐质量阶段每周 1-2 次，稳定后每月 1-2 次。
> **入口位置**：顶栏右上角（明显但不抢镜），不是 footer 链接（看不见）。

---

## 4. 页面结构（路由）

| 路由 | 用途 | 必做 |
|---|---|---|
| `/` | 推荐主页：3-5 张卡片 + refine 输入框 + 待反馈 banner（条件渲染） | ✅ |
| `/feedback/last` | 跳转：找到最近一个 accepted 但未 feedback 的 session，重定向到 `/feedback/<id>`；若无则空状态页 | ✅ |
| `/feedback/<session_id>` | 反馈页：还原当时的推荐卡片 + 选哪个 + 评分 + chip + 备注 | ✅ |
| `/profile` | profile 查看页（默认 YAML 只读 + "编辑" 按钮切表单） | ✅ |
| `/history` | 历史推荐列表（按日浏览） | 🟡 V1 可不做 |
| `/debug` | **不要做**，由另一份 brief 负责 | ❌ |

### 动线设计原则（必读，决定整体架构）

**推荐动线 ≠ 反馈动线**。这是两个独立 task，间隔 2-3 小时，**用户的认知模式完全不同**：

- **推荐动线**（11:25/18:00 饭前）：决策疲劳态 → 30 秒选一个 → 跳外卖 APP。用户来这是"我现在要吃啥"。
- **反馈动线**（13:30/20:00 饭后）：回顾态 → 5 秒打分 → 关闭。用户来这是"评价中午那顿"。

**两条动线不混合**。原版 brief 把反馈塞在主页底部是产品错误（用户饭后不会主动打开主页，即使打开，主页第一眼是推荐模式，反馈区在底部 = 等于不存在）。

**反馈触达靠两点**：
1. **顶部 banner**（V1 必做）：用户重新打开主页 `/` 时，若存在 accepted 但未 feedback 的 session，**主区上方显示一行 banner**：「中午吃的怎么样？给个反馈 →」。点击进 `/feedback/<id>`。
2. **agent cron 主动推**（V1.5+，**不在本 brief 范围**）：通过 Lark/系统通知触发用户重新打开 chisha 走到反馈页。技术实现后期再做。

> **手动调试时**：用户先在 `/` 选推荐 → 跳点评 APP → 吃完后**手动重开** `/` → 看到 banner → 点击进 `/feedback/<id>` 填完 → 跳回 `/`。两个页面之间用户手动衔接即可，不要把反馈塞回主页。

---

## 5. 主页 `/` 详细规格

### 5.1 顶部导航栏（fixed top）

横向一行，左到右 + 右上角图标：

**左到右**：
- **餐次徽章**（UI 显示「午餐 / 晚餐」）：自动判断当前是 lunch / dinner（11:00-15:00 → lunch；其它 → dinner）。允许手动切换。视觉上轻量，不抢镜。**前端必须用中文 label 显示，不能直接 print 后端字段名 `lunch`/`dinner`**。
- **心情切换**（UI 显示，label 是 "今天想吃啥" 或不放 label 直接铺胶囊组）：可选值（**后端字段值不能改，UI 标签必须中文映射**）：
  | 后端枚举 (传给 API) | UI 显示文案 |
  |---|---|
  | `neutral`（默认，可不传） | 「随便」（或不选中状态） |
  | `want_clean` | 「清淡」 |
  | `want_indulgent` | 「解馋」 |
  | `want_light` | 「轻食」 |
  | `want_soup` | 「想喝汤」 |
  | `low_carb` | 「低碳水」 |
- **「换一组」按钮**（不要叫"重新生成"，太机器感）：极轻量。点击后主区进 loading 态，重出 5 张卡片。loading 时长 15-60s（LLM 慢），需要 skeleton 或骨架屏，**不要用旋转 spinner**。loading 文案用「正在为你挑选...」，**不要默认的 "Loading..."**。

**右上角图标**（轻量但稳定可见）：
- **⚙️ 偏好**（UI 文字必须是中文「偏好」，**不要写 "profile"**）→ 点击进 `/profile`
- **🕐 历史**（同上，**不要写 "history"**）→ 点击进 `/history`

> 偏好入口必须明显但不抢镜。理由：偏好是用户调推荐质量的核心杠杆（口味描述 / 不喜欢的菜 等字段直接影响推荐排序）。藏起来等于把核心调优工具藏起来。但默认页面是只读模式（见 §7），所以不会形成"用户随手就改坏偏好"的风险。

### 5.2 待反馈 Banner（条件渲染，未反馈时显示）

当存在 accepted 但未 feedback 的 session 时，**导航栏正下方** + **3 卡片区上方** 显示一行 banner：

```
┌──────────────────────────────────────────────────────────────┐
│ 🍽 中午吃的"粤牛·化州剪牛腩"怎么样？ 5 秒反馈一下 →           │
│                                                          [×] │
└──────────────────────────────────────────────────────────────┘
```

- 数据源：`GET /api/session/last_unfed` 返回 `{ session_id, meal_type, restaurant_name, accepted_at }` 或 `null`
- 点击整行 → `/feedback/<session_id>`
- 右侧 [×] 关闭按钮 → 调 `POST /api/session/dismiss_feedback_banner { session_id }`（不删 session 数据，只标记 banner 不再显示）
- 视觉权重：明显但不抢推荐主区（不要做大色块横幅，配色用浅暖色背景 + 深色文字，类似 GitHub 提示条样式）
- **绝不阻断推荐流程**：banner 旁边可以正常重新生成推荐、选卡、refine

### 5.3 3 推荐卡片（**核心区块，60% 视觉权重**）

返回的是 **5 张卡片**（3 exploit + 2 explore）。主区显示前 3 张，下方一行小字「2 个备选 ▽」可展开看 4-5 张。

#### 单张卡片的信息层级（从大到小）

```
┌────────────────────────────────────────────────────────────────┐
│ [chip: ⓘ 探索]  [chip: ✓ 控油][✓ 蔬菜][✓ 蛋白]                │
│                                                                │
│ 粤牛·化州剪牛腩（牛杂煲·科技园店）                  ¥50.4    │
│                                                                │
│ 双拼鲜牛腩牛杂单人煲 + 招牌鲜牛杂单人煲 + 萝卜                 │
│                                                                │
│ 💬 牛腩牛杂炖汤，牛肉是你首选蛋白，5 种配菜补蔬菜，2.1km 最快到 │
│                                                                │
│ 15min · 2.1km · 蛋白 50g · 油 2.3/5                            │
│                                                                │
│        [ 就这个 → ]            [ 查看详情 ⌄ ]                  │
└────────────────────────────────────────────────────────────────┘
```

**字段映射到后端 schema**（见 §9 真实样本）：
- 商家名：`candidate.restaurant.name`
- 菜组合：`candidate.summary`（已经是 " + " 拼接好的字符串）
- 一句话理由：`candidate.reason_one_line`
- 价格：`candidate.total_price`（数字，前面拼 ¥）
- ETA / 距离：`candidate.restaurant.eta_min` / `candidate.restaurant.distance_m`
- 蛋白：`candidate.estimated_total_protein_g`（**单位 g**，不是 kcal）
- 油（1-5）：`candidate.estimated_total_oil`（5 是最油）
- 三件套徽章：`candidate.health_flags.{veg_ok, protein_ok, oil_ok}`
- 探索徽章：`candidate.is_explore === true` 时显示
- 风险 chip：`candidate.risk_flags` 是 string 数组（如 `["价格偏高¥129", "距离较远"]`），有就显示，红色

**「就这个 →」按钮的行为**：
- 调 `POST /api/accept { session_id, candidate_rank }`
- 后端返回 `{ deeplink_url: "..." }`
- 前端 `window.location.href = deeplink_url`（跳点评/美团 APP 的 URL Scheme）
- 后端标记 session 为 accepted (尚未 feedback)，下次用户重开 `/` 时 §5.2 banner 会显示

**「查看详情 ⌄」展开的内容**：
- 单菜列表：每道菜显示 `canonical_name` / `price` / `main_ingredient_type`（红肉/白肉/海鲜/蛋/豆制品/纯素/主食）/ `oil_level`
- score breakdown：暂不显示（开发者数据，放在 `/debug`）
- `fit_score`（0-1）和 `taste_match`（0-1）可显示为两个迷你 progress bar

#### 排序与显示规则

- 后端返回的 `candidates` 已按 `rank` 排好，**前端不要重排**
- `is_explore: true` 的卡片视觉上不应被弱化，但徽章要明显（"探索" / "本周新店"），让用户知道"这个是系统鼓励你试试看的"
- 蛋白量显示规则：`< 30g` 红色 / `30-45g` 默认 / `> 45g` 绿色（这是用户的健康目标，强信号）
- 油量显示规则：1-2 绿 / 3 默认 / 4-5 红（5 在召回阶段已被硬过滤，但 UI 仍要兜底）

### 5.4 换口味（refine）

紧跟 3 卡片下方。**UI 上不要叫 "refine"**，标题用「不喜欢？换个口味试试」。

```
┌─────────────────────────────────────────────────────────────┐
│ 不喜欢？换个口味试试                                         │
│                                                              │
│ [ 想吃辣的 ] [ 换日料 ] [ 来份烧烤 ] [ 想吃牛肉 ]            │
│ [ 来盖饭 ]  [ 换粤菜 ]                                       │
│                                                              │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 或者，告诉我你今天想要什么...                              │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                  [ 换一组 ] │
└─────────────────────────────────────────────────────────────┘
```

#### 5.4.1 快捷标签 chip 行（V1 静态固定 6 个）

固定 6 个 chip，**用户点击 chip 直接触发换口味**（等同于把 chip 文本作为 refine_text 提交），不需要再点「换一组」按钮：

| chip 文案 | 提交给 `/api/refine` 的 refine_text |
|---|---|
| 想吃辣的 | "想吃辣的" |
| 换日料 | "换日料" |
| 来份烧烤 | "来份烧烤" |
| 想吃牛肉 | "想吃牛肉" |
| 来盖饭 | "来盖饭" |
| 换粤菜 | "换粤菜" |

设计原则：
- chip 维度避开 mood selector 已覆盖的"清淡/解馋/轻食/想喝汤/低碳水"，聚焦在 **菜系 / 食材 / 形态**
- 视觉上是中性色 chip（不要做主色调），hover 微动，**点击直接发起请求**，不需要选中态
- chip 顺序固定（不要随机化，用户形成肌肉记忆）

> **TODO (V2.1 个性化)**：未来根据"最近 3 天没吃过的菜系/食材"动态生成 4-6 个标签，让快捷标签真的"知道你"。当前 V1 先用上面 6 个静态值。

#### 5.4.2 自定义输入

- 占位符示例（可轮播 3-5 秒切换）：
  - "或者，告诉我你今天想要什么..."
  - "想吃辣的，或者今天就想要带汤水的..."
  - "换日式定食"
  - "不想吃面，给我个有锅气的"
- 提交后：调 `POST /api/refine { session_id, refine_text }`，主区进 skeleton 态，新 5 张卡片返回后替换。
- 「换一组」按钮：用户输入文本后点击触发；如果文本为空就置灰禁用。

#### 5.4.3 换口味历史

- 在输入框下方显示一个小灰区："刚才你试过这几次：" → 「1. 想吃辣的 · 2. 换日料」（**不要叫 "refine 历史" 或 "session 历史"**，全中文）
- 允许点击某一条回到那一轮的卡片（前端从 session state 取，不重新调后端）

### 5.5 主页底部

**极简 footer，几乎看不见**：
- 仅在屏幕底部留一个 4-5px 的小灰色文字 `v0.1` （**不要写完整版本号、不要写决策号 D-051、不要写 "chisha" 项目代码名、不要写 "localhost"**——这些是工程内部信息，不应给 C 端用户看到）
- hover 后再展开 tooltip 显示完整调试信息（可选）
- 偏好 / 历史 入口已经在 §5.1 顶栏右上角，**不要重复**

> **§5 不要做反馈区**。反馈是独立动线，见 §6 反馈页。

---

## 6. 反馈页 `/feedback/<session_id>` 规格

### 6.1 入口与跳转规则

**入口 1**：用户点击主页 §5.2 banner → 直接进 `/feedback/<session_id>`
**入口 2**：访问 `/feedback/last` → 后端调 `GET /api/session/last_unfed` → 若有 → `redirect /feedback/<id>` → 若无 → 空状态页 "没有待反馈的推荐 · 回主页 →"

### 6.2 页面结构（顶到底）

```
┌────────────────────────────────────────────────────────────────┐
│  ← 回主页                          2026-05-15 中午 lunch       │
│                                                                │
│  ─────  那顿你点了哪个？  ─────                                │
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ ● 粤牛·化州剪牛腩（牛杂煲·科技园店）           ¥50.4   │   │
│  │   双拼鲜牛腩牛杂单人煲 + 招牌鲜牛杂单人煲 + 萝卜         │   │
│  │   💬 牛腩牛杂炖汤，牛肉是你首选蛋白...                   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                │
│  ○ 醉湘楼·家宴（南山店）                                       │
│    酸菜黑鱼片营养套餐 + 丝瓜闷土鸡蛋 + 黑米饭                  │
│                                                                │
│  ○ Super Model 超模厨房                                        │
│    S 级招牌烤鸡+牛肉套餐 + 清炒油菜芯 + 黑米饭                 │
│                                                                │
│  ○ 都没吃这几个                                                │
│                                                                │
│  ─────  怎么样？  ─────                                        │
│                                                                │
│  好吃度    ☆☆☆☆☆                                              │
│  整体满意  ☆☆☆☆☆                                              │
│                                                                │
│  [ 偏油 ]  [ 分量小 ]  [ 配送慢 ]  [ 想再来 ]                  │
│                                                                │
│  备注（可选）                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                                                          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
│                          [ 提交反馈 ]                          │
└────────────────────────────────────────────────────────────────┘
```

### 6.3 关键设计点

**还原推荐卡片（回顾视图）**：
- 数据源：`GET /api/feedback/<session_id>` 返回 `{ session_id, meal_type, accepted_at, candidates: [...] }`
- `candidates` 字段格式同 §9 真实样本，**前端复用 §5.3 的 RecommendCard 组件，但传 mode="review" 参数**：
  - 隐藏「就这个 →」「查看详情」按钮
  - 卡片左侧加 radio 单选圆点
  - 后端返回的 `accepted_rank` 对应那张卡片默认选中（高亮 + radio 选中态）
  - 用户可改选另一张（如果实际吃的不是点的那个，比如吃了同事的）
  - 末尾加一个无卡片的"都没吃这几个" radio

**评分区**：
- 两个 5 星（好吃度 / 整体满意），独立 state
- 4 个 toggle chip（多选）："偏油" "分量小" "配送慢" "想再来"
- textarea 占位符："比如：辣度刚好、米饭硬了点..."（不强制填）

**提交流**：
- 调 `POST /api/feedback { session_id, accepted_rank: number|null, rating_taste: number, rating_satisfaction: number, chips: string[], note: string }`
- 成功后：①显示一行 toast "已记录，明天见 →" ②2 秒后跳回 `/`
- 主页 §5.2 banner 自动消失（因为该 session 已 feedback）

**返回主页**：
- 顶栏左上角「← 回主页」始终可见
- 用户中途想取消反馈 → 点回主页 → banner 仍在，下次还可重新进

### 6.4 不要做

- ❌ 不要做"评价历史"（每次都是单个 session_id 上下文，历史走 `/history`）
- ❌ 不要做"分享反馈到社交"
- ❌ 不要把这一页塞回主页 `/`
- ❌ 不要做"必须填完所有字段才能提交"。**评分 + chip + note 全部可选**，唯一必填是"那顿你点了哪个"（含"都没吃"）

---

## 7. 偏好页 `/profile` 规格

> **UI 上叫「偏好」，不叫 "profile"**。但路由路径仍保留 `/profile`（URL 是技术词，用户不直接看到）。本文档内部用"偏好页"或"profile 页"都行。

偏好页**默认是只读视图**（YAML 源文件预览），点击「编辑」切表单。这是为了：
- 默认状态低噪音（用户主要诉求是"看一眼当前偏好长啥样"）
- 同时保留编辑能力（用户需要时进入表单模式调整）
- 避免主页被表单区污染（主页保持极简）

### 7.1 默认视图（只读 · 源文件预览）

```
┌────────────────────────────────────────────────────────────────┐
│  ← 回主页              偏好 · 当前区域: 深圳湾科技园           │
│                                                                │
│                                       [ 编辑 ✏️ ]               │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  basics:                                                 │  │
│  │    name: 志丹                                            │  │
│  │    goal: 体重控制+力量训练期（保饱腹感，参考哈佛餐盘法）│  │
│  │    zones:                                                │  │
│  │      lunch: shenzhen-bay                                 │  │
│  │      dinner: shenzhen-bay                                │  │
│  │                                                          │  │
│  │  plate_rule:                                             │  │
│  │    min_protein_g: 40                                     │  │
│  │    prefer_oil_level_at_most: 3                           │  │
│  │  ...                                                     │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
│  最后修改: 2026-05-13                                          │
└────────────────────────────────────────────────────────────────┘
```

**注意**：顶栏「当前区域」必须显示中文 label，不能直接 print 后端字段值 `shenzhen-bay`。前端需要维护一个 zone 中文 mapping：

| zone 后端字段 | UI 显示文案 |
|---|---|
| `shenzhen-bay` | 深圳湾科技园 |
| `home` | 家附近 |
| `beijing-zgc` | 北京中关村（V2 才有数据） |
| `shanghai-xhh` | 上海徐汇湾（V2 才有数据） |

- YAML 高亮组件用 `prism-react-renderer` 或 `react-syntax-highlighter`（轻量），**不要引入 Monaco editor**（太重）
- 只读，等宽字体，浅色背景 + 语法高亮
- 顶部一行 meta：当前 zone / 文件最后修改时间

### 7.2 编辑视图（点击「编辑」后切换）

按以下分区组织表单：

#### 7.2.1 基本信息
- name (string)
- city (string, 默认深圳)
- goal (textarea, 多行长描述, 见真实样本)

#### 7.2.2 餐次区域映射
- zones.lunch (枚举: shenzhen-bay / home / ...)
- zones.dinner (同上)

#### 7.2.3 弱约束三件套
- plate_rule.min_vegetable_dishes (number, 默认 1)
- plate_rule.min_protein_g (number, 默认 40)
- plate_rule.prefer_oil_level_at_most (number 1-5, 默认 3)
- plate_rule.hard_max_oil_level (number 1-5, 默认 4)

#### 7.2.4 口味偏好（**最重要的区**）
- taste_description (大 textarea, 至少 10 行高, 字符 500+)
- preferences.liked_cuisines (chip list, 可加可删)
- preferences.disliked_cuisines (chip list)
- preferences.banned_cuisines (chip list, 标红)
- preferences.avoid_dishes (chip list, 标红, 显示真实条目)
- preferences.avoid_main_ingredients (chip list)
- preferences.avoid_cooking_methods (chip list)
- preferences.avoid_restaurants (chip list)
- spicy_tolerance (slider 0-3 整数)

#### 7.2.5 履约约束
- delivery_constraints.hard_max_eta_min (number)
- delivery_constraints.prefer_max_eta_min (number)

#### 7.2.6 价格约束
- price_range.hard_max_lunch / hard_max_dinner / prefer_max_lunch / prefer_max_dinner (4 个 number)

#### 7.2.7 触发时间
- meal_trigger_time.lunch (time picker)
- meal_trigger_time.dinner (time picker)
- meal_trigger_time.weekend (boolean)

#### 7.2.8 LLM / 高级（折叠默认关）
- llm.provider (枚举 auto / claude_code_cli / anthropic / openrouter)
- llm.model.* (3 个 string 字段)

### 7.3 编辑视图的通用交互

- 顶部固定一栏：「← 取消」「保存修改」按钮，未保存修改时显示红点
- 字段旁有 tooltip 解释（重要字段）
- 保存调 `PUT /api/profile { ...profile_dict }`，返回后端回写 profile.yaml 的结果
- 保存成功后**自动切回 §7.1 只读 YAML 视图**（让用户看到新结果）
- 「重置为默认值」按钮（恢复 git HEAD 版本）

> profile 表单的字段命名严格照抄 §10 真实 profile.yaml。不要改名、不要做"用户友好别名"。这是因为 profile.yaml 是工程产物，字段名改了下游召回/打分都炸。

---

## 8. API 契约（前端调这些，后端我会接）

所有 API 在 `http://127.0.0.1:8765/api/*`，单用户无认证。

```
# ─── 推荐动线 ───
GET  /api/recommend?meal=lunch&mood=neutral
     → 返回完整 recommend response（见 §9 真实样本）

POST /api/refine
     body: { session_id: string, refine_text: string }
     → 返回完整 recommend response（新一轮）

POST /api/accept
     body: { session_id: string, candidate_rank: number }
     → { deeplink_url: string }
     # 后端同时标记 session 为 accepted, last_unfed 候选

# ─── 反馈动线（独立）───
GET  /api/session/last_unfed
     → { session_id, meal_type, restaurant_name, accepted_at } | null
     # 主页 §5.2 banner 用. 找到最近一个 accepted 但未 feedback 的 session.

POST /api/session/dismiss_feedback_banner
     body: { session_id: string }
     → { ok: true }
     # banner 右上 [×] 关闭按钮调. 不删 session 数据, 只关 banner.

GET  /api/feedback/<session_id>
     → {
         session_id: string,
         meal_type: "lunch"|"dinner",
         accepted_at: string,        // ISO datetime
         accepted_rank: number|null, // 用户当时点的那个
         candidates: [/* 同 §9 candidate schema */]
       }
     # 反馈页 §6 加载时调, 还原当时推荐的卡片.

POST /api/feedback
     body: {
       session_id: string,
       accepted_rank: number | null,  // null = "都没吃"
       rating_taste: number,          // 1-5; 0 = 未填
       rating_satisfaction: number,   // 1-5; 0 = 未填
       chips: string[],               // 子集 ["偏油","分量小","配送慢","想再来"]
       note: string,
     }
     → { ok: true }

# ─── profile ───
GET  /api/profile
     → {
         profile: {...},                   // 完整 profile dict (见 §10)
         yaml_raw: string,                 // 原 yaml 文本, §7.1 YAML viewer 用
         last_modified: string,            // ISO datetime
       }

PUT  /api/profile
     body: { ...profile_dict }
     → { ok: true, saved_path: "profile.yaml", yaml_raw: string }

# ─── 历史（V1 可选）───
GET  /api/history?days=7
     → { items: [{ session_id, meal_type, generated_at, accepted_rank, candidates_summary }, ...] }
```

**Loading 状态**：`/api/recommend` 和 `/api/refine` 会跑 15-60s（LLM 慢），前端必须有 skeleton。其它 API 都是 <500ms。

---

## 9. 真实推荐输出样本（必读，照这个 schema 设计）

### 9.1 lunch / mood=null 默认场景

```json
{
  "session_id": "20260515_lunch_112d",
  "meal_type": "lunch",
  "zone": "shenzhen-bay",
  "round": 1,
  "version": "v2",
  "generated_at": "2026-05-14T17:25:45.495607+00:00",
  "context": {
    "meal_type": "lunch",
    "zone": "shenzhen-bay",
    "now": "2026-05-15T01:24:52.678558",
    "weekday": 4,
    "last_meal": null,
    "recent_3d_cuisines": {},
    "recent_3d_ingredients": {},
    "last_feedback": null,
    "daily_mood": null,
    "refine_input": null
  },
  "stats": {
    "n_dishes_total": 11123,
    "n_combos_recalled": 2467,
    "n_combos_after_score": 2467,
    "n_returned": 5
  },
  "candidates": [
    {
      "rank": 1,
      "is_explore": false,
      "summary": "S 级招牌烤鸡+牛肉套餐 + 清炒油菜芯 每份/90g + 低 GI 主食：黑米饭一份",
      "restaurant": {
        "id": "r_222",
        "name": "Super Model 超模厨房（深圳科技园店）",
        "distance_m": 3500,
        "eta_min": 30
      },
      "dishes": [
        { "dish_id": "d_222_005", "canonical_name": "S 级招牌烤鸡+牛肉套餐", "price": 32.8, "main_ingredient_type": "白肉", "oil_level": 3 },
        { "dish_id": "d_222_026", "canonical_name": "清炒油菜芯 每份/90g", "price": 6.0, "main_ingredient_type": "纯素", "oil_level": 2 },
        { "dish_id": "d_222_028", "canonical_name": "低 GI 主食：黑米饭一份", "price": 3.0, "main_ingredient_type": "主食", "oil_level": 1 }
      ],
      "total_price": 41.8,
      "vegetable_dish_count": 1,
      "estimated_total_oil": 2.0,
      "estimated_total_protein_g": 45,
      "score": 2.879,
      "reason_one_line": "Super Model 多变体中蔬菜最实（清炒油菜芯），烤鸡+牛肉蛋白足，结构最符合哈佛餐盘",
      "fit_score": 0.82,
      "health_flags": { "veg_ok": true, "protein_ok": true, "oil_ok": true, "processed_meat": false, "sweet_sauce": false, "wetness": false },
      "taste_match": 0.6,
      "risk_flags": []
    },
    {
      "rank": 2,
      "is_explore": false,
      "summary": "酸菜黑鱼片营养套餐 + 丝瓜闷土鸡蛋 + 黑米饭",
      "restaurant": { "id": "r_018", "name": "醉湘楼·家宴（南山店）", "distance_m": 4100, "eta_min": 35 },
      "dishes": [
        { "dish_id": "d_018_003", "canonical_name": "酸菜黑鱼片营养套餐", "price": 24.8, "main_ingredient_type": "海鲜", "oil_level": 3 },
        { "dish_id": "d_018_032", "canonical_name": "丝瓜闷土鸡蛋", "price": 29.9, "main_ingredient_type": "蛋", "oil_level": 3 },
        { "dish_id": "d_018_075", "canonical_name": "黑米饭", "price": 3.5, "main_ingredient_type": "主食", "oil_level": 1 }
      ],
      "total_price": 58.2,
      "vegetable_dish_count": 1,
      "estimated_total_oil": 2.3,
      "estimated_total_protein_g": 45,
      "score": 2.887,
      "reason_one_line": "酸菜黑鱼+丝瓜蛋+黑米饭，湘菜风格命中你口味，比 Super Model 多汤水和蔬菜层次",
      "fit_score": 0.79,
      "health_flags": { "veg_ok": true, "protein_ok": true, "oil_ok": true, "processed_meat": false, "sweet_sauce": false, "wetness": true },
      "taste_match": 0.75,
      "risk_flags": []
    },
    {
      "rank": 4,
      "is_explore": true,
      "summary": "杭椒煎牛肉 1 人份 + 鸡汤石磨老豆腐 1 人份 + 腐皮鸡毛菜 1 人份",
      "restaurant": { "id": "r_182", "name": "钱塘潮·精致江浙菜（高新店）", "distance_m": 1100, "eta_min": 15 },
      "dishes": [
        { "dish_id": "d_182_009", "canonical_name": "杭椒煎牛肉 1 人份", "price": 39.0, "main_ingredient_type": "红肉", "oil_level": 3 },
        { "dish_id": "d_182_010", "canonical_name": "鸡汤石磨老豆腐 1 人份", "price": 19.0, "main_ingredient_type": "豆制品", "oil_level": 2 },
        { "dish_id": "d_182_013", "canonical_name": "腐皮鸡毛菜 1 人份", "price": 23.0, "main_ingredient_type": "纯素", "oil_level": 2 }
      ],
      "total_price": 81.0,
      "vegetable_dish_count": 1,
      "estimated_total_oil": 2.3,
      "estimated_total_protein_g": 50,
      "score": 2.146,
      "reason_one_line": "江浙菜本周首次，杭椒煎牛肉辣1+锅气，鸡汤豆腐补汤水，1.1km 最近",
      "fit_score": 0.64,
      "health_flags": { "veg_ok": true, "protein_ok": true, "oil_ok": true, "processed_meat": false, "sweet_sauce": false, "wetness": true },
      "taste_match": 0.78,
      "risk_flags": []
    },
    {
      "rank": 5,
      "is_explore": true,
      "summary": "酸辣椒炒土猪肉 + 基地蔬菜-应季特惠 + 自制酸腌菜炒小笋+米饭 + 自制篙子粑粑",
      "restaurant": { "id": "r_191", "name": "湖南老灶台（科兴店）", "distance_m": 2400, "eta_min": 27 },
      "dishes": [
        { "dish_id": "d_191_014", "canonical_name": "酸辣椒炒土猪肉", "price": 58.0, "main_ingredient_type": "红肉", "oil_level": 3 },
        { "dish_id": "d_191_003", "canonical_name": "基地蔬菜-应季特惠 一人份", "price": 6.0, "main_ingredient_type": "纯素", "oil_level": 2 },
        { "dish_id": "d_191_008", "canonical_name": "自制酸腌菜炒小笋+米饭 单人份", "price": 43.25, "main_ingredient_type": "纯素", "oil_level": 3 },
        { "dish_id": "d_191_049", "canonical_name": "自制篙子粑粑", "price": 22.0, "main_ingredient_type": "主食", "oil_level": 1 }
      ],
      "total_price": 129.2,
      "vegetable_dish_count": 2,
      "estimated_total_oil": 2.2,
      "estimated_total_protein_g": 40,
      "score": 1.962,
      "reason_one_line": "酸辣椒炒土猪肉是你口味描述最直接命中；过去妥协清淡太久，explore 一次重口",
      "fit_score": 0.58,
      "health_flags": { "veg_ok": true, "protein_ok": true, "oil_ok": true, "processed_meat": false, "sweet_sauce": false, "wetness": false },
      "taste_match": 0.88,
      "risk_flags": ["价格偏高¥129", "距离较远"]
    }
  ]
}
```

### 9.2 dinner / mood=want_indulgent 解馋场景

```json
{
  "session_id": "20260515_dinner_8f38",
  "meal_type": "dinner",
  "version": "v2",
  "context": {
    "daily_mood": "want_indulgent",
    "refine_input": null,
    "recent_3d_cuisines": {},
    "last_feedback": null
  },
  "candidates": [
    {
      "rank": 1,
      "is_explore": false,
      "summary": "双拼鲜牛腩牛杂单人煲 + 招牌鲜牛杂单人煲 + 萝卜",
      "restaurant": { "name": "粤牛·化州剪牛腩（牛杂煲·科技园店）", "eta_min": 15 },
      "total_price": 50.4,
      "estimated_total_oil": 2.3,
      "estimated_total_protein_g": 50,
      "reason_one_line": "牛腩牛杂炖煲带汤，want_indulgent首选，比清粥类满足感高两档",
      "fit_score": 0.88,
      "taste_match": 0.82,
      "health_flags": { "veg_ok": true, "protein_ok": true, "oil_ok": true, "processed_meat": false, "sweet_sauce": false, "wetness": true },
      "risk_flags": []
    }
  ]
}
```

---

## 10. 真实 profile.yaml（必读，照这个 schema 设计编辑面板）

```yaml
basics:
  name: 志丹
  city: 深圳
  goal: 体重控制+力量训练期（保饱腹感，参考哈佛餐盘法）
  zones:
    lunch: shenzhen-bay
    dinner: shenzhen-bay

plate_rule:
  must_have_vegetable: true
  min_vegetable_dishes: 1
  min_protein_g: 40
  prefer_oil_level_at_most: 3
  hard_max_oil_level: 4

taste_description: |
  === 健康目标 ===
  体重控制 + 力量训练期。哈佛餐盘法（1/2 蔬菜 + 1/4 蛋白 + 1/4 复合碳水）。
  关键失败模式（朋友A教训）：极致清淡 + 极致低油 → 当顿满足感弱 →
  半夜反弹宵夜，总热量反而更高。
  所以不是"这一顿热量最低"，而是"这一顿能撑到下一顿"。

  === 真实口味偏好（不考虑健康约束）===
  - 喜欢有锅气的炒菜、味道重的下饭菜——这是核心口味
  - 喜欢辣椒炒、酸菜煮、卤味、糖醋、蜜汁、照烧、红烧——口味上都喜欢
  - 喜欢汤水/带汁的也行（潮汕牛肉、酸菜鱼、翘脚牛肉、卤粉）
  - 能吃重辣（spicy_tolerance=3）
  ...（长 textarea，~30 行）

preferences:
  liked_cuisines: [湘菜, 川菜, 潮汕, 粤菜, 日式, 轻食健康]
  disliked_cuisines: [饮品甜品, 烧烤]
  banned_cuisines: []
  banned_processed_meat: false
  banned_sweet_sauce_level_3: false
  avoid_dishes: []
  avoid_main_ingredients: []
  avoid_cooking_methods: []
  avoid_restaurants: []
  spicy_tolerance: 3   # 0=不辣 1=微辣 2=中辣 3=重辣

delivery_constraints:
  hard_max_eta_min: 45
  prefer_max_eta_min: 30

price_range:
  hard_max_lunch: 150
  hard_max_dinner: 150
  prefer_max_lunch: 120
  prefer_max_dinner: 120

meal_trigger_time:
  lunch: "11:25"
  dinner: "18:00"
  weekend: false

llm:
  provider: auto
  model:
    claude_code_cli: sonnet
    anthropic: claude-sonnet-4-6
    openrouter: anthropic/claude-sonnet-4.6
```

---

## 11. 技术栈约束

| 项 | 要求 |
|---|---|
| 框架 | React 18 + TypeScript |
| 样式 | Tailwind CSS（不要 styled-components / emotion） |
| 路由 | React Router v6（用户视图 + profile 编辑双路由） |
| 状态 | useState / useReducer 即可，**不要引入 Redux / Zustand**，单用户场景不值得 |
| 数据请求 | fetch + 简单 useEffect / SWR 也行（喜欢轻量的话） |
| 图标 | lucide-react（轻量） |
| 字体 | system-ui / Inter |
| 构建 | Vite |
| YAML 高亮 | `prism-react-renderer` 或 `react-syntax-highlighter`（任选轻量的）。**不要 Monaco editor**（太重） |
| 表单 | `react-hook-form` 可用（profile 表单需要） |
| **不要的依赖** | shadcn 可以用，但不要拉 ant / mui / chakra；不要 Redux / Zustand / Recoil |

---

## 12. 视觉细节

- **配色**：浅色优先（白底 + 浅灰 + 1 个主色调，建议偏冷色调 indigo / sky / slate）。深色模式 V2 再做，先不做。
- **圆角**：rounded-lg / rounded-xl 居多
- **阴影**：极轻 shadow-sm，不要 shadow-2xl 那种
- **字号**：base 14-15px，标题 18-24px，**不要做超大字号**（不是 landing page）
- **间距**：紧凑而非奢侈。卡片间距 16-20px，区块间距 32-40px
- **动画**：极轻，hover 微动 + skeleton 转场即可。**不要做花哨的 page transition**

---

## 13. 明确不要做的事

### 13.1 范围层面

| ❌ 不做 | 原因 |
|---|---|
| 用户注册 / 登录 / 头像 / 个人资料页 | 单用户，无认证 |
| 卡路里数字 | 用户反感数字焦虑，只显示蛋白 g + 油 1-5 |
| 推荐结果的"分享/收藏到小红书" | 偏离工具属性 |
| 教学引导 / onboarding wizard | 用户是开发者，自己读 README |
| 把所有功能塞主页 | 偏好页 / 历史独立路由 |
| 移动端 hamburger menu | 桌面优先，移动端做响应式自适应即可 |
| 中文字体加载 webfont | 用 system-ui，加载快 |
| emoji 装饰（除了 reason_one_line 里的 💬）| 工程师审美 |
| 加载时旋转 spinner | 用 skeleton 骨架屏 |

### 13.2 UI 文案：纯中文，禁止中英夹杂（关键规则）

**用户看到的所有界面文案必须是纯中文**。"用户看到的" = 标签、按钮文字、导航文字、提示、loading 文案、错误信息、状态描述。

#### 必须中文化的术语对照（前端必须 mapping，不能直接 print 后端字段名）

| 后端 / 内部术语 | UI 必须显示的中文 |
|---|---|
| `lunch` / `dinner` | 午餐 / 晚餐 |
| `profile` | 偏好 |
| `mood` / mood selector | 心情 / 「今天想吃啥」 |
| `neutral` | 随便（或不选中态） |
| `want_clean` | 清淡 |
| `want_indulgent` | 解馋 |
| `want_light` | 轻食 |
| `want_soup` | 想喝汤 |
| `low_carb` | 低碳水 |
| `refine` | 换口味 / 「不喜欢？换个口味试试」 |
| `session` | 本次推荐 / 这一轮 |
| `explore` (徽章) | 探索 / 本周新店 |
| `history` | 历史 |
| `zone` 字段 (`shenzhen-bay` 等) | 必须 mapping 中文区域名（见 §7.1 表） |
| `YAML` (技术词) | 源文件预览 / 完整配置 |
| Loading / Loading... | 正在为你挑选... |
| Error / Failed | 出问题了，再试一次 → |
| `accept` / 「accept this」 | 「就这个」 |
| `feedback` | 反馈 / 「中午吃的怎么样」 |

#### 文案禁用词清单（**绝对不要在任何 UI 元素出现**）

`profile` · `mood` · `refine` · `session` · `lunch` · `dinner` · `explore` · `accept` · `feedback` · `YAML` · `localhost` · `D-051` · `chisha` · `v1` · 任何后端 enum 字面值（如 `want_clean`、`shenzhen-bay`）

#### 保留英文不动的（允许）

- 数据本身（商家名"Super Model 超模厨房"、菜名"S 级招牌烤鸡"、品牌名）
- 路由 URL 路径（`/feedback/last` — 不显示给用户）
- 技术 README 文档（给开发者看，不在 UI 中）

#### 实施建议

前端必须维护一个 `lib/labels.ts` 中文 mapping 文件，集中管理所有后端枚举 → 中文文案的映射。所有 UI 组件只使用 mapping 后的字符串，**不能直接 render 后端字段值**。

---

## 14. 期望产出

按这个顺序产出文件：

### 14.1 路由 & 主结构
1. **路由结构**：`App.tsx` + `router.tsx`（4 个路由：`/` `/feedback/:id` `/feedback/last` `/profile`）
2. **顶部导航栏**：`components/TopBar.tsx`（含餐次徽章 + mood selector + 重新生成 + ⚙️ profile + 🕐 history 入口）

### 14.2 推荐主页 `/`
3. **主页**：`pages/Home.tsx`（顶栏 + 待反馈 banner + 3 卡片 + refine 输入）
4. **待反馈 banner**：`components/PendingFeedbackBanner.tsx`（条件渲染，调 `/api/session/last_unfed`）
5. **推荐卡片**：`components/RecommendCard.tsx`（**支持 `mode="decision" | "review"` 两态**：decision 显示「就这个」按钮，review 显示 radio 单选圆点 + 默认选中态）
6. **refine 输入**：`components/RefineInput.tsx`（含 session 内 refine 历史展示）

### 14.3 反馈页 `/feedback/<id>`
7. **反馈页**：`pages/Feedback.tsx`（顶部还原推荐卡片 review 模式 + 评分 + chip + textarea + 提交）
8. **反馈空状态**：`pages/FeedbackEmpty.tsx`（`/feedback/last` 路由无未反馈 session 时显示）

### 14.4 profile 页 `/profile`
9. **profile 页**：`pages/Profile.tsx`（**两态切换容器**：默认只读 / 编辑表单）
10. **YAML 只读组件**：`components/ProfileYamlViewer.tsx`（用 `prism-react-renderer` 或 `react-syntax-highlighter`，YAML 高亮 + 等宽字体）
11. **profile 编辑表单**：`components/ProfileEditForm.tsx`（按 §7.2 八个分区）

### 14.5 工具层
12. **API client**：`lib/api.ts`（按 §8 契约封装）
13. **Mock data hook**：`lib/mockData.ts`（用 §9 真实样本 + 一份反馈页 mock + 一份 profile mock，让前端不依赖后端就能跑起来）
14. **类型定义**：`lib/types.ts`（Candidate / RecommendResponse / FeedbackPayload / Profile 等）
15. **中文文案映射**：`lib/labels.ts`（**关键文件，见 §13.2**）—— 集中管理所有后端枚举/字段值 → UI 中文文案的映射。比如：
    ```ts
    export const MEAL_LABELS = { lunch: '午餐', dinner: '晚餐' };
    export const MOOD_LABELS = {
      neutral: '随便', want_clean: '清淡', want_indulgent: '解馋',
      want_light: '轻食', want_soup: '想喝汤', low_carb: '低碳水',
    };
    export const ZONE_LABELS = {
      'shenzhen-bay': '深圳湾科技园', 'home': '家附近',
    };
    // ...
    ```
    所有组件**禁止 hardcode** 后端字段值的字符串显示，必须经过这个 mapping 层。

### 14.6 文档
15. **README**：怎么本地起 dev server，怎么切 mock / real backend，4 个路由各自怎么测

---

## 15. 验收标准（设计完成后我会自检的清单）

### 推荐动线
- [ ] 我能在 30 秒内从打开 `/` 到点击「就这个」跳转完成
- [ ] 3 卡片在 13" MacBook 上一屏能看完（不需要滚）
- [ ] mood selector 改变后我能直观知道当前选了哪个
- [ ] explore 卡片有视觉差异但不被边缘化
- [ ] risk_flags 数组有内容时红色 chip 醒目
- [ ] 重新生成 / refine 时主区进 skeleton 态，**不是**旋转 spinner

### 反馈动线
- [ ] 选中"就这个"后，重开 `/` 顶部能看到 banner 提示未反馈
- [ ] 点击 banner / 访问 `/feedback/last` 能进反馈页
- [ ] 反馈页能看到当时被推荐的所有 5 张卡片（review 模式）
- [ ] 默认选中的就是当时 accepted 的那张卡片，但允许改选
- [ ] 评分 / chip / note 全部留空也能提交（唯一必填是"哪张卡片"）
- [ ] 提交后 banner 消失，跳回 `/`

### profile
- [ ] 进 `/profile` 默认看到的是 YAML 只读视图，不是表单
- [ ] YAML 视图有语法高亮，等宽字体
- [ ] 点「编辑」切到表单，顶部能看到「← 取消」「保存」
- [ ] taste_description 是大 textarea（10+ 行），不是 input
- [ ] avoid_dishes 是 chip 列表可加可删，不是逗号分隔字符串
- [ ] 保存后自动切回只读 YAML 视图，能看到新内容

### 整体
- [ ] 主页、反馈页、偏好页有统一的导航/返回交互
- [ ] 整体感觉像 Linear / Vercel / Raycast，不像薄荷健康 / 美团 / 小红书
- [ ] 没有"分享到朋友圈" / "营养图表" / "排行榜" 这类范围外功能

### 文案纯中文（§13.2 必读）
- [ ] **全屏扫一遍**：任何 UI 标签 / 按钮 / 提示文案中**找不到** profile / mood / refine / session / lunch / dinner / explore / accept / feedback / YAML / localhost / D-051 / chisha / v1 / want_clean / shenzhen-bay 等英文/枚举字面值
- [ ] 餐次徽章显示"午餐 / 晚餐"，不是 "lunch / dinner"
- [ ] 心情选项显示"清淡 / 解馋 / 轻食 / 想喝汤 / 低碳水 / 随便"，不是 `want_clean` 等
- [ ] 顶栏右上角是「⚙️ 偏好」「🕐 历史」，不是 "profile" "history"
- [ ] 区域名显示"深圳湾科技园"，不是 "shenzhen-bay"
- [ ] Loading 状态是「正在为你挑选...」，不是 "Loading..."
- [ ] 错误兜底是「出问题了，再试一次 →」，不是 "Error" / "Failed"
- [ ] 主页 footer 不出现 "chisha v1 · localhost · D-051"
- [ ] 所有这些通过 `lib/labels.ts` 一处管理，组件层只用 mapping 后的字符串

### 换口味标签（§5.4.1）
- [ ] Refine 输入框上方有 6 个快捷标签 chip（想吃辣的 / 换日料 / 来份烧烤 / 想吃牛肉 / 来盖饭 / 换粤菜）
- [ ] 点击 chip 直接触发换口味请求（不需要再点「换一组」按钮）
- [ ] 「换口味历史」区显示"刚才你试过这几次："（中文，不是 "refine 历史"）

---

## 附录 · 给设计 AI 的元指令

如果你（claude.ai/design）有任何不清楚的地方：
1. **不要瞎猜**。可以用注释 `// TODO(brief): 这里我假设了 X，是否合理？` 留下标记
2. **不要扩展范围**。不要主动加"分享给朋友" / "营养图表" / "排行榜" 等
3. **schema 字段名严格照抄**（在 API 请求 body / 内部代码中）。`main_ingredient_type` 不是 `category`，`canonical_name` 不是 `name`，等等
4. **mood 枚举严格照抄**（在 API 请求中）。是 `want_indulgent` 不是 `indulgent`，是 `want_clean` 不是 `clean`
5. **但 UI 上必须全部中文化**（§13.2）。所有这些后端字段名 / 枚举值 / `lunch` / `profile` 等英文术语**绝对不能在 UI 上出现**。前端通过 `lib/labels.ts` 集中 mapping 后再 render
6. **不要加 i18n** 库（i18next 等）。中文 hardcode 即可，简单 mapping 不需要国际化框架
