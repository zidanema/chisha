"""推荐调试 Web 服务 + apps/web SPA 托管.

启动:
    uv run python -m chisha.debug_server
    → 浏览器开 http://127.0.0.1:8765        (apps/web SPA, D-051 用户视图)
    → http://127.0.0.1:8765/debug             (老调试台 HTML)
    → http://127.0.0.1:8765/logic             (逻辑说明页)

Endpoints:
    /                          apps/web/dist SPA (404 fallback → index.html)
    /api/recommend etc.        见 chisha.web_api (V1 + V1.1)
    /api/debug_recommend       老调试台用 (V2 instrumented)
    /api/compare_moods         同上, 横向对比
    /swagger                   FastAPI OpenAPI UI
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from chisha.debug_recommend import compare_moods, debug_recommend
from chisha.web_api import router as web_router


from chisha.install_root import install_root as _install_root  # T-DIST-01 B.1
ROOT = _install_root()
STATIC_DIR = Path(__file__).resolve().parent / "static"
WEB_DIST = ROOT / "apps" / "web" / "dist"  # dev only — wheel 不含 apps/
PROFILE_PATH = ROOT / "profile.yaml"


app = FastAPI(
    title="chisha 推荐调试台",
    version="0.1.0",
    docs_url="/swagger",   # 让出 /docs 给逻辑说明页
    redoc_url=None,
)

# 用户视图 API (apps/web 用)
app.include_router(web_router)


# ---------- Pydantic models ----------

class DebugRecommendReq(BaseModel):
    meal_type: str = "lunch"
    daily_mood: str | None = None
    use_llm_rerank: bool | None = None
    profile_overrides: dict[str, Any] | None = None
    today: str | None = None              # YYYY-MM-DD
    trace_target: dict[str, Any] | None = None
    # 边界 (Codex review LOW): 防止误传巨大值放大 LLM 调用成本
    n_return: int = Field(default=5, ge=1, le=20)
    n_explore: int = Field(default=2, ge=0, le=10)


class CompareMoodsReq(BaseModel):
    # D-073 后 neutral 是 V1.2 唯一对 L2 产生加分的 mood; 历史枚举入参仍接受
    # (向后兼容), 但 compare 结果横向差异趋零. 默认只比 neutral 自身, 调用方
    # 想横向对历史 mood 仍可显式传 moods=[...]. 上限 8 防误传跑死服务器.
    moods: list[str] = Field(
        default_factory=lambda: ["neutral"],
        min_length=1, max_length=8,
    )
    meal_type: str = "lunch"
    profile_overrides: dict[str, Any] | None = None
    use_llm_rerank: bool | None = None
    today: str | None = None


def _parse_today(today: str | None) -> dt.date | None:
    """非法 YYYY-MM-DD → 400 而不是 500 (Codex review LOW)."""
    if not today:
        return None
    try:
        return dt.date.fromisoformat(today)
    except ValueError:
        raise HTTPException(400, f"today must be YYYY-MM-DD, got {today!r}")


# ---------- API ----------
# NOTE: GET /api/profile 已挪到 chisha.web_api (V1 用户视图也要用), 这里不再重复挂.

@app.post("/api/debug_recommend")
def api_debug_recommend(req: DebugRecommendReq) -> dict:
    return debug_recommend(
        meal_type=req.meal_type,
        daily_mood=req.daily_mood,
        use_llm_rerank=req.use_llm_rerank,
        profile_overrides=req.profile_overrides,
        today=_parse_today(req.today),
        trace_target=req.trace_target,
        n_return=req.n_return,
        n_explore=req.n_explore,
    )


@app.post("/api/compare_moods")
def api_compare_moods(req: CompareMoodsReq) -> dict:
    return compare_moods(
        moods=req.moods,
        meal_type=req.meal_type,
        profile_overrides=req.profile_overrides,
        use_llm_rerank=req.use_llm_rerank,
        today=_parse_today(req.today),
    )


# ---------- Static ----------

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
# apps/web/dist 挂在 /; 不存在 (未 build) 时仅老调试台可用。
if WEB_DIST.exists() and (WEB_DIST / "index.html").exists():
    # /assets/* 走 StaticFiles
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="web-assets")

    @app.get("/")
    def web_index() -> FileResponse:
        return FileResponse(WEB_DIST / "index.html")

    _WEB_DIST_RESOLVED = WEB_DIST.resolve()

    # SPA fallback: 任何非 /api 非 /assets 非已注册路由的 GET 都回 index.html
    # React Router 用 (/feedback /history /profile etc.)
    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str) -> FileResponse:
        # /api/* 真没匹配上的视为 404, 不要 swallow 成 SPA
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail=f"unknown api {full_path!r}")
        # path traversal 守卫 (Codex review MED-2):
        # full_path 由 URL 解码后传入, '../' 可能逃逸 WEB_DIST.
        # 一律 resolve + 断言 startswith, 不安全就退回 SPA shell.
        candidate = (WEB_DIST / full_path).resolve()
        try:
            candidate.relative_to(_WEB_DIST_RESOLVED)
        except ValueError:
            return FileResponse(WEB_DIST / "index.html")
        if candidate.is_file():
            return FileResponse(candidate)
        # 其它一律回 SPA shell, React Router 接管
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
        "chisha.debug_server:app",
        host="127.0.0.1",
        port=8765,
        reload=False,
    )


if __name__ == "__main__":
    main()
