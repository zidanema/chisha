# chisha · sandbox lab (apps/sandbox-lab)

D-088 「白盒时光机」内部 debug SPA。7~14 天可回放、可分支、可改规则的推荐沙箱。

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

S-01 scaffold 阶段:demo 区块验证 token / 字体 / 主题切换 / accent 4 套切换。
完整视觉 (TopBar / Timeline / 5 推荐卡 / 4 panels) 见 S-02。

## Claude Code 自测约定

改本目录任何 `.tsx` / `.css` / `vite.config.ts` 后,必须用 `mcp__chrome-devtools__*` 工具自驱浏览器验证 (golden path + edge case + console + network),不许只跑 lint/tsc 就宣告完成。详见根目录 [`CLAUDE.md`](../../CLAUDE.md) §前端自测。
