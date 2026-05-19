# chisha · sandbox lab (apps/sandbox-lab)

D-093 「白盒时光机」内部 debug SPA。7~14 天可回放、可分支、可改规则的推荐沙箱。

设计源: `chidiansha-sandbox/project/sandbox-lab/` (HTML 原型,Phase 1/2 字句搬过来不重设计)
落地 brief: `docs/design_briefs/2026-05-19-sandbox-lab.md`

## 本地拉起

两个 server 一起跑:

```bash
# Terminal 1 — 后端 FastAPI (debug + sandbox 端点)
uv run python -m chisha.debug_server   # http://127.0.0.1:8765

# Terminal 2 — 前端 Vite (SPA)
cd apps/sandbox-lab
npm install                            # 第一次
npm run dev                            # http://127.0.0.1:5175
```

Vite proxy `/api → :8765` 已配。

**多 worktree 端口冲突**: 5175 被占时用 `VITE_PORT=5180 npm run dev`,后端用 `VITE_API_TARGET=http://127.0.0.1:8767`。

## 当前状态

D-093 落地完成 (2026-05-20): S-01 ~ S-09 全部 commit. 主区 + Timeline + 4 panels + Banners + Modals + TweaksPanel 接入真后端 (`/api/sandbox/*` 11 端点), backend offline 时 fallback 内置 mock, 顶栏 pill 显示 backend/mock 状态.

dev / demo query 参数 (visual verification 用):
- `?dev=1` — 显示 TweaksPanel 浮层
- `?mock_recommend=1` — 后端 in-memory mock 兜底, 不烧 LLM
- `?demo-review=1` — 左列渲 ReviewCard (eat 形态, mock D1 午)
- `?demo-review=skip` — ReviewCard skip 极简形态
- `?demo-modal=summary|confirm-rollback|confirm-branch|refine` — 强开对应 modal

## Claude Code 自测约定

改本目录任何 `.tsx` / `.css` / `vite.config.ts` 后,必须用 `mcp__chrome-devtools__*` 工具自驱浏览器验证 (golden path + edge case + console + network),不许只跑 lint/tsc 就宣告完成。详见根目录 [`CLAUDE.md`](../../CLAUDE.md) §前端自测。

## 数据流

```
Backend chisha.web_api sandbox/* (chisha/web_api.py)
  └── GET  /api/sandbox/sessions                              → 桶列表
  └── POST /api/sandbox/sessions                              → 创建桶
  └── GET  /api/sandbox/sessions/{sid}                        → FullSnapshot (meta/clock/history/recs/decision/...)
  └── POST /api/sandbox/sessions/{sid}/recs                   → 拉本顿 5 推荐
  └── POST /api/sandbox/sessions/{sid}/eat                    → job_id (async BG decision)
  └── POST /api/sandbox/sessions/{sid}/skip                   → 推时钟不学习
  └── POST /api/sandbox/sessions/{sid}/swap                   → 换一组
  └── POST /api/sandbox/sessions/{sid}/refine                 → 单 round refine
  └── GET  /api/sandbox/sessions/{sid}/jobs/{jid}             → 轮询 eat 完成
  └── POST /api/sandbox/sessions/{sid}/rollback               → 裁剪 history
  └── POST /api/sandbox/sessions/{sid}/branch                 → 派生新 sid

Frontend useSandbox hook (apps/sandbox-lab/src/hooks/useSandbox.ts)
  ├── pingBackend() 决定 backendOnline
  ├── online: fetch + polling, 状态从 GET /sessions/{sid} 拉真 FullSnapshot
  └── offline: fallback sbxMocks (S-03 时期的 mock 数据)
```

后端 snake_case → 前端 camelCase 全走 `src/api/adapter.ts` 边界, 后端 schema 改只动 adapter.
