# chisha web · 用户视图 V1 + V1.1

> 本机 localhost SPA。来源于 [`docs/design_briefs/v1_user_view.md`](../../docs/design_briefs/v1_user_view.md) + claude.ai/design 原型两轮迭代沉淀（[`docs/style-guide.md`](../../docs/style-guide.md)、D-052~D-055 入口架构、D-056~D-068 反馈系统）。

## 启动

```bash
cd apps/web
npm install
npm run dev          # http://localhost:5173 (Mock API)
# 或者: VITE_USE_MOCK=0 npm run dev   # 真接口模式，/api 反代到 8765
```

后端走 `chisha/debug_server.py` 的 8765 端口；`/api/*` 已在 `vite.config.ts` 配反代。

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

- `src/lib/api.ts` — 真接口骨架，HTTP/JSON
- `src/lib/mockApi.ts` — mock 数据，端口 §5 契约（[docs/api.md](../../docs/api.md)）
- `VITE_USE_MOCK=1`（默认）走 mock；`VITE_USE_MOCK=0` 走真接口

V1.1 反馈链路 7 个端点在 mockApi 全量实现, 后端 FastAPI 待装 — 详见 [docs/api.md §5](../../docs/api.md) + [IMPL_LOG D-056~D-068](../../docs/archive/IMPLEMENTATION_LOG_phase0.md#d-056d-068-执行记录--v11-反馈系统落地-appsweb)。

## 设计原则

详见 [`docs/style-guide.md`](../../docs/style-guide.md) §文案规范 + §视觉系统 + §反模式。锁定的交互（pick / refine 面包屑 / skip / 同 session 抑制 banner / YAML 只读默认 / banner ✕ = snooze / 反馈提交即 readonly / append-only timeline）已写入 D-052~D-055 + D-056~D-068，**不要重新设计**。
