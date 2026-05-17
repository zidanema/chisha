"""Back-compat shim — 真正入口已迁到 chisha.server (D-085).

老命令仍可用:
    uv run python -m chisha.debug_server
    from chisha.debug_server import app

会自动转发到 chisha.server. 该 shim 不再演进, 新功能改 chisha/server.py 或两个 router.
"""
from __future__ import annotations

from chisha.server import app, main  # noqa: F401  re-export

__all__ = ["app", "main"]


if __name__ == "__main__":
    main()
