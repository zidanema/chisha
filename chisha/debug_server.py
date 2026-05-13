"""推荐调试 Web 服务.

启动:
    uv run python -m chisha.debug_server
    → 浏览器开 http://127.0.0.1:8765

Endpoints:
    GET  /                      调试台 HTML
    POST /api/debug_recommend   跑一次 V2 instrumented 推荐
    POST /api/trace_combo       同上 + 追溯指定 combo
    POST /api/compare_moods     同一输入跑多个 daily_mood 横向对比
    GET  /api/profile           读当前 profile.yaml (供前端展示默认值)
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from chisha.debug_recommend import compare_moods, debug_recommend


ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
PROFILE_PATH = ROOT / "profile.yaml"


app = FastAPI(
    title="chisha 推荐调试台",
    version="0.1.0",
    docs_url="/swagger",   # 让出 /docs 给逻辑说明页
    redoc_url=None,
)


# ---------- Pydantic models ----------

class DebugRecommendReq(BaseModel):
    meal_type: str = "lunch"
    daily_mood: str | None = None
    use_llm_rerank: bool | None = None
    profile_overrides: dict[str, Any] | None = None
    today: str | None = None              # YYYY-MM-DD
    trace_target: dict[str, Any] | None = None
    n_return: int = 5
    n_explore: int = 2


class CompareMoodsReq(BaseModel):
    moods: list[str] = ["want_light", "want_soup", "want_indulgent"]
    meal_type: str = "lunch"
    profile_overrides: dict[str, Any] | None = None
    use_llm_rerank: bool | None = None
    today: str | None = None


def _parse_today(today: str | None) -> dt.date | None:
    if not today:
        return None
    return dt.date.fromisoformat(today)


# ---------- API ----------

@app.get("/api/profile")
def get_profile() -> dict:
    """供前端显示当前 profile 默认值."""
    return yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))


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

@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "debug.html")


@app.get("/docs")
def docs() -> FileResponse:
    return FileResponse(STATIC_DIR / "logic.html")


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
