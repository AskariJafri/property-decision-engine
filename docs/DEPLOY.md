# Deploying it for free

The analyze path touches no database. Nothing on it imports SQLAlchemy, Alembic or
a driver — only FastAPI, Pydantic and httpx, with pypdf loaded lazily for uploads.
That is why this deploys on free tiers that would otherwise be ruled out by a
Postgres requirement: **21 runtime packages, no persistent storage, no state.**

Saved analyses, accounts and the rule registry in a database all arrive with
Phase F/C work that is not built yet. Until then the app is a pure function of its
request, which is inconvenient for a product and extremely convenient for hosting.

---

## What you get, and what you give up

| | Free deployment | Local with everything running |
|---|---|---|
| Money, scoring, fair value, risk | identical | identical |
| Listing paste and PDF upload | works | works |
| Commute / Location | works with an ORS key | works, self-hosted |
| Amenity counts | unavailable, stated | needs Overpass |
| AI explanations | unavailable, stated | needs a local model |
| Saved analyses | not built yet | not built yet |

Every absent piece reports itself rather than failing, so a free deployment is a
smaller product, not a broken one.

---

## Recommended: Vercel for both halves

Two projects from one repository. Both free, cold starts of a second or two.

### 1. Push the repository

```bash
gh repo create property-decision-engine --private --source=. --push
```

### 2. Frontend

New Vercel project → import the repo → **Root Directory: `web`**. Next.js is
detected automatically. Add one environment variable once the API is deployed:

```
NEXT_PUBLIC_API_BASE = https://<your-api-project>.vercel.app
```

### 3. Backend

A second Vercel project from the same repo → **Root Directory: `backend`**.
`backend/vercel.json` routes everything to `api/index.py`, and
`backend/requirements.txt` holds the runtime dependencies only.

Environment variables:

```
PDE_ENVIRONMENT   = production
PDE_CORS_ORIGINS  = https://<your-web-project>.vercel.app
PDE_ORS_API_KEY   = <your key, if you want commute times>
```

**`PDE_CORS_ORIGINS` is the one people forget.** Miss it and every browser request
dies at the preflight while the API looks perfectly healthy to curl — the exact
failure the E2E suite was written for.

### The licence caveat

Vercel's Hobby plan is for **non-commercial** use. Fine for a personal project or
a portfolio piece; not fine the day you charge someone. Render's free tier permits
commercial use, which is the reason the alternative below exists.

---

## Alternative: Render for the backend

`render.yaml` at the repo root is a blueprint — point Render at the repo and it
builds `backend/Dockerfile`.

The trade-off is cold starts: Render's free web service sleeps after 15 minutes
idle and takes roughly a minute to wake, so the first visitor after a quiet spell
waits. Set the same environment variables as above.

Keep the frontend on Vercel either way; a Next.js app is what that platform is for.

---

## After deploying, check it took

```bash
curl https://<your-api>/api/v1/health
```

`providers_configured.openrouteservice` should be `true` if you set the key.
Remember that **configured is not reachable** — it means the value arrived, not
that the service answers.

Then load the frontend and run an analysis. If the button does nothing and the
browser console shows a CORS error, `PDE_CORS_ORIGINS` does not match your
frontend's origin exactly, scheme included.

---

## Secrets

`.env` is gitignored and stays local. Every deployed secret goes in the host's
environment variable settings — never in the repository, never in `.env.example`.

The only secret this app currently has is the OpenRouteService key. There are no
data-provider keys to leak, because every other source is open, self-hosted, or
supplied by the user (ADR 0002).

---

## What to do before this is a real product

Free hosting is fine for showing someone. Before it takes a stranger's financial
details:

1. **Authentication and persistence** — Phase F. Right now there are no accounts
   and nothing is saved.
2. **Rate limiting** — the analyze and upload endpoints are the expensive ones and
   are currently unthrottled in deployment.
3. **The legal review** in `COMPLIANCE.md` §7 — mortgage-adjacent language needs a
   FSRA-aware reader before it is in front of the public.
4. **A real database** — managed Postgres with PostGIS, at which point the free
   tier stops being sufficient and that is the right moment to start paying.
