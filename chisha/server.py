"""单一 uvicorn 入口 + SPA 托管 (D-085 重构后改名 server.py).

启动:
    uv run python -m chisha.server                    # 新入口
    uv run python -m chisha.debug_server              # 老入口 (back-compat shim)
    → 浏览器开 http://127.0.0.1:8765        (apps/web SPA, Living)
    → http://127.0.0.1:8765/debug             (老调试台 HTML, /api/lab/* 后端)
    → http://127.0.0.1:8765/logic             (逻辑说明页)

路由布局 (D-085):
    /api/*               Living API → chisha.api_living
    /api/lab/*           Lab API    → chisha.api_lab
    /swagger             FastAPI OpenAPI UI
    /                    apps/web/dist SPA (404 fallback → index.html)
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from chisha.api_lab import router as lab_router
from chisha.api_living import router as living_router


ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
WEB_DIST = ROOT / "apps" / "web" / "dist"


app = FastAPI(
    title="chisha 推荐调试台 (D-085 Living + Lab)",
    version="0.2.0",
    docs_url="/swagger",
    redoc_url=None,
)

# D-085: Living + Lab 两个独立 router
app.include_router(living_router)
app.include_router(lab_router)


# ---------- 静态页 ----------

@app.get("/debug")
def debug_page() -> FileResponse:
    """老调试台 (D-039) — / 让给 apps/web SPA."""
    return FileResponse(STATIC_DIR / "debug.html")


@app.get("/logic")
def logic_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "logic.html")


# 兼容旧路径 (老书签): /docs → /logic
@app.get("/docs")
def docs() -> FileResponse:
    return FileResponse(STATIC_DIR / "logic.html")


# ---------- SPA 托管 ----------

if WEB_DIST.exists() and (WEB_DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="web-assets")

    @app.get("/")
    def web_index() -> FileResponse:
        return FileResponse(WEB_DIST / "index.html")

    _WEB_DIST_RESOLVED = WEB_DIST.resolve()

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str) -> FileResponse:
        # /api/* 真没匹配上的视为 404, 不要 swallow 成 SPA
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail=f"unknown api {full_path!r}")
        # path traversal 守卫: 一律 resolve + 断言 startswith
        candidate = (WEB_DIST / full_path).resolve()
        try:
            candidate.relative_to(_WEB_DIST_RESOLVED)
        except ValueError:
            return FileResponse(WEB_DIST / "index.html")
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(WEB_DIST / "index.html")
else:
    @app.get("/")
    def web_index_missing() -> dict:
        return {
            "ok": False,
            "error": "apps/web/dist not built — run `cd apps/web && npm run build` first",
            "debug_url": "/debug",
        }


def main():
    import uvicorn
    uvicorn.run(
        "chisha.server:app",
        host="127.0.0.1",
        port=8765,
        reload=False,
    )


if __name__ == "__main__":
    main()
