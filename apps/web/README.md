# chisha web · 用户视图 V1 + V1.1

> 本机 localhost SPA。来源于 [`docs/design_briefs/archive/v1_user_view.md`](../../docs/design_briefs/archive/v1_user_view.md) + claude.ai/design 原型两轮迭代沉淀（[`docs/style-guide.md`](../../docs/style-guide.md)、D-052~D-055 入口架构、D-056~D-068 反馈系统）。

## 启动

```bash
cd apps/web
npm install
npm run dev                      # http://localhost:5173 (默认: 真接口, /api 反代到 8765)
# 或者: VITE_USE_MOCK=1 npm run dev   # mock 模式 (离线 UI 调试, NavBar 显示红色 MOCK 角标)
```

**默认走真接口** (D-073 后, backend stable). 后端 `chisha/debug_server.py` 监听 8765, `/api/*` 已在 `vite.config.ts` 配反代.

历史: 早期 mock-first 默认导致 D-073 调试时对着 mock 看不到 backend 实测差异 — 改 real-first + NavBar `MOCK` 角标双保险.

## Claude Code 自测约定

改本目录任何 `.tsx` / `.css` / `vite.config.ts` 后, Claude Code 必须用 `mcp__chrome-devtools__*` 工具自驱浏览器验证 (导航到改动路由 + 走 golden path + 看 console / network), 不许只跑 vitest/tsc 就宣告完成. 详见根目录 [`CLAUDE.md`](../../CLAUDE.md) "前端自测" 章节.

## 路由

| 路由 | 用途 | 状态 |
|---|---|---|
| `/` | 推荐主页（5 卡片 + refine + pick + skip + stack banner） | ✅ |
| `/profile` | 偏好页（YAML 只读 / 7 区表单编辑） | ✅ |
| `/history` | 最近 7 天历史（行可点进反馈, D-059） | ✅ |
| `/feedback` | 反馈中心三段（待反馈 / 暂缓 / 已反馈, D-058） | ✅ V1.1 |
| `/feedback/last` | 解析到第一条 active unfed | ✅ V1.1 |
| `/feedback/:id` | 反馈页双态: 未反馈→progressive form / 已反馈→readonly snapshot + append timeline (D-066 + D-067) | ✅ V1.1 |

## 数据层

- `src/lib/api.ts` — 真接口客户端，HTTP/JSON
- `src/lib/mockApi.ts` — mock 数据，端口 §5 契约（[docs/api.md](../../docs/api.md)）
- `VITE_USE_MOCK=0`（默认, 真接口）；`VITE_USE_MOCK=1` 切 mock (UI 上 NavBar 显示红色 `MOCK` 角标)

V1.1 反馈链路 7 个端点已在后端 FastAPI 装上 (D-069) 并在 mockApi 全量实现 — 详见 [docs/api.md §5](../../docs/api.md)。

## 设计原则

详见 [`docs/style-guide.md`](../../docs/style-guide.md) §文案规范 + §视觉系统 + §反模式。锁定的交互（pick / refine 面包屑 / skip / 同 session 抑制 banner / YAML 只读默认 / banner ✕ = snooze / 反馈提交即 readonly / append-only timeline）已写入 D-052~D-055 + D-056~D-068，**不要重新设计**。
