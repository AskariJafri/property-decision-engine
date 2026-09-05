# Deploying it for free

The analyze path touches no database. Nothing on it imports SQLAlchemy, Alembic or
a driver — only FastAPI, Pydantic and httpx, with pypdf loaded lazily for uploads.
That is why this deploys on free tiers that would otherwise be ruled out by a
Postgres requirement: **21 runtime packages, no persistent storage, no state.**

Saved analyses, accounts and the rule registry in a database all arrive with
Phase F/C work that is not built yet. Until then the app is a pure function of its
request, which is inconvenient for a product and extremely convenient for hosting.

---

## What is deployed

| | |
|---|---|
| Frontend | <https://property-decision-engine-web.vercel.app> |
| API | <https://property-decision-engine-gules.vercel.app> |
| Health | <https://property-decision-engine-gules.vercel.app/api/v1/health> |

Both are Vercel Hobby projects built from this one repository, differing only in Root
Directory. Commute times are live against OpenRouteService; amenity counts report
themselves unavailable, as the table below says they will.

Explanations are wired in but switched off on both deployments: Vercel functions cannot
reach an Ollama on your machine, and no hosted model is configured. The figures never
depend on one — see "Turning explanations on" below.

---

## What you get, and what you give up

| | Free deployment | Local with everything running |
|---|---|---|
| Money, scoring, fair value, risk | identical | identical |
| Listing paste and PDF upload | works | works |
| Commute / Location | works with an ORS key | works, self-hosted |
| Amenity counts | unavailable, stated | needs Overpass |
| AI explanations | needs a reachable hosted model | works with Ollama |
| Saved analyses | not built yet | not built yet |

Every absent piece reports itself rather than failing, so a free deployment is a
smaller product, not a broken one.

---

## Recommended: Vercel for both halves

Two projects from one repository. Both free, cold starts of a second or two.

**Import the same repository twice**, as two projects with different Root
Directories. One repo, two deployments.

**Do the backend first.** `NEXT_PUBLIC_*` variables are inlined into the
JavaScript bundle at build time, not read at runtime, so the frontend has to know
the API's URL *before* it builds. Doing it the other way round means building
twice.

### 1. Backend

New Project → import `property-decision-engine` → **Root Directory: `backend`**.
Framework preset: **Other**. `backend/vercel.json` routes every path to
`api/index.py`, and `backend/requirements.txt` carries the runtime dependencies.

Environment variables before deploying:

```
PDE_ENVIRONMENT   = production
PDE_ORS_API_KEY   = <your key, for commute times>
```

Deploy, then note the URL — call it `https://<api>.vercel.app`. Check it:

```bash
curl https://<api>.vercel.app/api/v1/health
```

### 2. Frontend

New Project → import the **same repo again** → **Root Directory: `web`**. Next.js
is detected automatically. Set this *before* the first deploy:

```
NEXT_PUBLIC_API_BASE = https://<api>.vercel.app
```

**You create this variable; it is not one you pick from a list.** Vercel's
Environment Variables screen is two free-text boxes — type the name on the left
and the value on the right. Nothing is pre-populated, and nothing validates the
name, so a typo produces a build that succeeds and an app that cannot reach its
API. The name must be exactly `NEXT_PUBLIC_API_BASE`: the `NEXT_PUBLIC_` prefix is
what tells Next.js to expose it to the browser, and without it the value is
visible only on the server, where this app never reads it.

### The alternative that needs no variable at all

Uncomment the `rewrites` block in `web/next.config.mjs`, put your API's URL in it,
and the frontend proxies `/api/*` through its own origin. Then there is no
`NEXT_PUBLIC_API_BASE` to set and no `PDE_CORS_ORIGINS` to get wrong, because the
browser only ever talks to one host. The cost is that the URL lives in a committed
file rather than in project settings.

### 3. Close the loop

Go back to the backend project and add the frontend's origin, then redeploy it:

```
PDE_CORS_ORIGINS = https://<web>.vercel.app
```

**`PDE_CORS_ORIGINS` is the one people forget.** Miss it and every browser request
dies at the preflight while the API looks perfectly healthy to curl — the exact
failure the E2E suite was written for.

It is an exact list, not a pattern. That means **preview deployments will fail at the
preflight**, because each one gets its own hostname and none of them is the production
origin. This is deliberate: a wildcard wide enough to cover previews would be
`*.vercel.app`, which lets any site hosted on Vercel make credentialed calls to an
endpoint that receives a household's income and debts. If you need a preview to work,
add that specific preview origin.

### The build that succeeds and fails anyway

Vercel refuses to publish a Next.js build whose framework version carries a known
critical advisory. The build log is not obviously a failure — it compiles, it
prerenders every page, it prints the route table, and then the last line reads:

```
Vulnerable version of Next.js detected, please update immediately.
```

The deployment is marked *Build Failed* with the generic "project or build error"
and an Upgrade button, none of which points at the version. The fix is to move to
a patched release and push; nothing about the project configuration is wrong.

This happened here on `next@15.1.3`, which sits inside the range of
CVE-2025-29927 (middleware authorization bypass, patched in 15.2.3). The pin is
now `15.5.25`, the current 15.x backport line.

Worth knowing because the same block will fire again the next time an advisory
lands and the pin has drifted behind it. A build that compiles is not evidence
that the version is deployable.

### Turning explanations on

Three variables, and the flag is the one that matters:

```
PDE_LLM_EXPLANATIONS_ENABLED = true
PDE_LLM_BASE_URL             = https://<an OpenAI-compatible endpoint>/v1
PDE_LLM_MODEL                = <the exact tag, never an alias>
PDE_LLM_API_KEY              = <the key, if the endpoint wants one>
```

**Do not turn the flag on without a reachable model.** The default base URL is
`http://localhost:11434/v1`, and on a serverless host localhost is the function's
own container: the call does not fail fast, it waits. A short connect timeout
(`PDE_LLM_CONNECT_TIMEOUT_SECONDS`, 3s) bounds the damage, but paying it on every
request for prose that can never arrive is waste.

**Blanking `PDE_LLM_BASE_URL` does not turn the model off.** Blank environment
variables are treated as unset so the default applies — the fix for a crash where
an empty `PDE_LLM_SEED` took the whole app down at import. The consequence here is
that emptying the URL restores the localhost default rather than clearing it. The
flag is the switch; there is no other one.

The model is handed a finished analysis and can move nothing in it. If it is down,
slow, malformed or inventing figures, the analysis renders in full and says why the
prose is missing. That is asserted in `tests/test_explanation_wiring.py`, which
checks a complete set of figures alongside every failure mode.

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
