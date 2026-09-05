"""Serverless entrypoint.

The analyze path touches no database — only fastapi, pydantic and httpx — so the
whole backend fits in a serverless function with a cold start measured in seconds
rather than the minute a sleeping container takes.

Vercel looks for a module-level ASGI app in ``api/``; this is that, and almost
nothing else. Keeping it thin means a deployment problem is never confused with an
application problem.

The one piece of work it does do is put the project root on ``sys.path``. Locally
the package is installed with ``pip install -e``, so ``app`` is importable from
anywhere; in a serverless build it is just a directory sitting next to this file's
parent, and whether that lands on the path is a property of the platform rather
than something to leave to chance.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.main import app  # noqa: E402  (import follows the sys.path fix, deliberately)

__all__ = ["app"]
