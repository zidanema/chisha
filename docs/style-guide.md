# chisha · UI 样式与文案规范 (V1)

> 本文档约束 `apps/web` 用户视图的所有 UI 输出（文案 + 视觉系统）。LLM 产出的字段（reason_one_line / summary）也必须遵守 §1 文案规则。
>
> 原型沉淀于 `chisha-user.zip / DESIGN_NOTES.md` §3 §4；正式约束写入本文档 + [DECISIONS.md](DECISIONS.md) D-050~D-053。

---

## 1. 文案规范

### 1.1 唯一原则: UI 上**零英文 / 零枚举字面值**

| ❌ 禁止出现在用户视图 | ✅ 应该是 |
|---|---|
| `lunch` / `dinner` | 午餐 / 晚餐 |
| `mood` / `refine` / `session` | 心情 / 换口味 / 本次推荐 |
| `neutral` / `want_clean` / `want_indulgent` / `want_light` / `want_soup` / `low_carb` | 随便 / 清淡 / 解馋 / 轻食 / 想喝汤 / 低碳水 |
| `profile` | 偏好 |
| `shenzhen-bay` | 深圳湾科技园 |
| `Loading...` | 正在为你挑选... |
| `chisha v1 · localhost · D-049` | footer 仅显示 `v0.1`（hover 出 build 信息） |
| `taste_match 偏低` / `want_indulgent 首选`（LLM CoT 漏出） | "口味契合偏低" / "'解馋'心情首选" |

例外（允许英文不动）:
- 商家名 / 菜名里的英文（`Super Model 超模厨房`、`Wagas`、`SaladPower`）
- 路由 URL 路径（用户不直接看到）
- 偏好页 YAML 源文件预览块（D-053 明确豁免 — 这是技术对象的字面预览）

### 1.2 实施约束

- 项目内 `apps/web/src/lib/labels.ts` 是**单一 i18n 源**，所有组件**禁止直接 hardcode** 后端字段值
- 即使 mock 数据里的 `reason_one_line` 也按这条规则改写（生产 LLM 输出走同一约束）
- 新增枚举值 → 必须同时在 `labels.ts` 加 mapping，否则 PR 不过

### 1.3 风格

- **写给开发者，工程师审美**：Linear / Vercel / Raycast 路线
- **直接，不绕弯**：不写"小贴士:"/"你知道吗:"
- **数据驱动**：具体数字（"3 道菜 ¥41.8 / 30min 送达"），少用"大概""可能"
- **关键操作必须有 inline 持久反馈**，不靠 toast（D-050）
- **emoji 只用功能性**: reason 行的 `💬`，banner 的 `🍽`，其它一律不加

---

## 2. 视觉系统

| 维度 | 决策 |
|---|---|
| 配色 | 浅色 + 单一主色（默认 indigo `#4f46e5`）。深色模式 V2 才做 |
| 字体 | Geist Sans + Geist Mono (Google Fonts)。**禁** Inter / 系统字体 / 中文 webfont |
| 圆角 | rounded-md / rounded-lg 居多，不用 rounded-full 装饰 |
| 阴影 | 极轻 shadow-sm；hover 浮一层带 accent 染色的软阴影 |
| 字号 | base 13-14px，标题 15-18px，卡片标题 16px |
| 间距 | 紧凑：卡片间距 12px，区块间距 28-32px |
| 加载态 | **必须 skeleton 骨架屏**（LLM 实际 15-60s）。**禁用旋转 spinner** |

### 2.1 健康标注的颜色规则（硬编码到组件，不要轻易改）

- 蛋白量：`< 30g` 红 / `30-45g` 默认色 / `> 45g` 绿
- 油量：`1-2` 绿 / `3` 默认色 / `4-5` 红
- `risk_flags` 数组任何条目 → 红色 chip

### 2.2 CSS 变量

主题通过 `:root` 上 CSS 变量驱动（见 `apps/web/src/App.tsx` 的 `themeVars()`）:

```
--bg / --surface / --surface-2 / --border / --fg / --muted
--accent / --accent-fg / --accent-bg
--good / --bad / --bad-bg / --info
```

组件内 `color: var(--fg)` / `background: var(--surface)` / `border-color: var(--border)` 引用，**不要写死十六进制颜色**。

---

## 3. 已显式砍掉的反模式（**别再加回来**）

- ❌ 用户注册 / 登录 / 头像 / 个人资料（单用户无认证）
- ❌ 卡路里数字（只显示蛋白 g + 油 1-5）
- ❌ "分享/收藏到小红书"
- ❌ 教学引导 / onboarding wizard
- ❌ 把所有功能塞主页（偏好/历史/反馈各自独立路由）
- ❌ 移动端 hamburger menu（桌面优先）
- ❌ 中文 webfont 加载
- ❌ Emoji 装饰（除了 §1.3 列的两个功能性 emoji）
- ❌ 旋转 spinner（必须 skeleton）
- ❌ 反馈区塞主页底部（独立路由，D-049）
- ❌ 备选折叠（5 张直接展开 — §6 信息密度卖点）
- ❌ 假装 deeplink 跳 APP（D-050: 改成"搜店名"+复制按钮）
- ❌ Toast 闪一下消失就完事（D-050: 关键操作必须 inline 持久状态）
- ❌ 反馈可修改（D-064: 提交即永久 readonly, 即使 1 分钟内也不能改; "事后回想"由 D-065 append-only timeline 承担）
- ❌ 反馈双维度评分（V1 原"好吃度 + 整体满意"双 5 星, D-062 砍 — 维度模糊, gut 一个就够）
- ❌ 反馈时让用户从 5 候选 review-radio 选一次（accept 已记 rank, D-066）
- ❌ 反馈 banner 关掉就永久消失（D-058: ✕ 默认 = snooze 24h, 永久 stop 需 ⋯ 菜单显式选）
- ❌ 反馈 4 个固定 chip 偏油/分量小/配送慢/想再来（V1 原版, D-061 砍 — 散乱无 calibration, 替换为 4 维 reason_match/fullness/oil_calibration/repurchase_intent）

---

## 4. 设计原则备忘（一行版）

1. 用户是开发者，工程师审美 → Linear / Vercel / Raycast 风格
2. 信息密度 > 留白
3. 一切 UI 文案纯中文
4. 关键操作必须 inline 持久反馈，不靠 toast
5. 给用户每条决策路径都留逃生口（pick / refine / skip / undo）
6. 因果链空间紧邻（动作和结果在视觉上挨着，D-051 面包屑）
7. 不假装做不到的事（deeplink、cron 通知）
8. 一千个 no 换一个 yes（不要给推荐页加任何 §3 列表里的功能）
