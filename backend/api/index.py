"""Serverless entrypoint.

The analyze path touches no database — only fastapi, pydantic and httpx — so the
whole backend fits in a serverless function with a cold start measured in
seconds rather than the minute a sleeping container takes.

Vercel looks for a module-level ASGI app in ``api/``; this is that, and nothing
else. Keeping it to one import means a deployment problem is never confused with
an application problem.
"""

from app.main import app

__all__ = ["app"]
