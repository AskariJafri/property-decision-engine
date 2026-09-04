# Runbook

How to run, test and extend this locally.

---

## Run it (the short version)

You need **Python 3.12+** and **Node 22+**. You do not need Postgres, Docker, Ollama or the
OpenStreetMap services to see a full analysis — every absent provider degrades to
"Data unavailable" with a reason, which is the product working as designed.

**Terminal 1 — the API**

```bash
cd backend
python -m venv .venv                      # first time only
.venv/Scripts/pip install -e ".[dev]"     # first time only  (Linux/macOS: .venv/bin/pip)
.venv/Scripts/uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — the web app**

```bash
cd web
npm install                               # first time only
npm run dev
```

Open **http://localhost:3000** and click *Analyse this property*. The form is pre-filled with
an $850,000 Toronto example.

- API docs: http://localhost:8000/api/v1/docs
- Health: http://localhost:8000/api/v1/health

### Why several scores say "Data unavailable"

Location, Investment and Market conditions have no data source configured in a bare checkout.
They report that fact, their weight is redistributed across what *is* known, and the analysis
confidence drops accordingly (`SCORING_MODEL.md` §7). Nothing is broken — filling those gaps is
what the sections below are for.

---

## Run the tests

```bash
cd backend
.venv/Scripts/python -m pytest -q          # 265 tests, no database needed
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
.venv/Scripts/python -m mypy app
```

**Schema constraint tests** need a migrated Postgres with PostGIS:

```bash
docker run -d --name pde-pg -e POSTGRES_USER=pde -e POSTGRES_PASSWORD=pde \
  -e POSTGRES_DB=pde -p 5432:5432 postgis/postgis:16-3.4
cd backend
PDE_DATABASE_URL="postgresql+asyncpg://pde:pde@localhost:5432/pde" .venv/Scripts/alembic upgrade head
PDE_TEST_DATABASE_URL="postgresql://pde:pde@localhost:5432/pde" .venv/Scripts/python -m pytest tests/integration -q
```

**End-to-end** needs both servers running (see above), then:

```bash
cd web
npx playwright install chromium            # first time only
npx playwright test
```

---

## Getting a listing into the form

Three ways in, in order of how well they work:

1. **Print to PDF and upload.** Open the listing in your browser, `Ctrl+P` → *Save
   as PDF*, then use **Upload a saved PDF**. A browser's PDF carries a real text
   layer, so values are lifted exactly and shown back with the characters they came
   from. Two clicks and nothing is fetched on your behalf.
2. **Paste the text.** Select the listing details, paste, press *Read this listing*.
3. **Type it in.** Always available.

**There is no URL field, deliberately.** REALTOR.ca and the consumer portals
prohibit automated retrieval, and *Century 21 Canada v. Rogers*, 2011 BCSC 1196
held those terms enforceable, found the copying infringing and granted an
injunction. You may read a page you are entitled to read and save what you saw;
the product will not go and get it for you. See ADR 0002 §2.

**Screenshots are not supported** and say so when uploaded: a PNG has no text
layer, so reading it needs OCR or a vision model. Printing to PDF gives exact text
instead of a guess at pixels.

## Turn on the optional pieces

### The local model (AI explanations and listing extraction)

```bash
ollama serve
ollama pull llama3.1:8b-instruct-q4_K_M    # about 5 GB
```

The defaults in `.env.example` already point at `http://localhost:11434/v1`. Leave
`PDE_LLM_BASE_URL` blank to run with no model at all — judgements come back unavailable and the
analysis degrades honestly (ADR 0004).

Pin the **exact tag**, never an alias like `llama3`: judgements are stored with the model id
that produced them, and an alias that shifts under you breaks the replay that keeps scores
reproducible.

### A commute time in five minutes (OpenRouteService)

The quickest way to make the Location score real, before committing to the OSM box.

1. Sign up at **https://openrouteservice.org/dev/#/signup** (a HeiGIT account).
2. Go to **https://openrouteservice.org/dev/#/home**, open the **TOKENS** tab, and
   request a free token at the bottom of the page.
3. Put it in `.env` at the repo root: `PDE_ORS_API_KEY=your-token`.
4. Restart the API, then check it took:
   `curl http://localhost:8000/api/v1/health` — `providers_configured.openrouteservice`
   should be `true`.
5. Fill in the property address and your work address in the form.

`providers_configured` means a key or URL reached the process, **not** that the
service answers. Reachability is discovered at call time and degrades into the
analysis with a reason, which is why a configured-but-not-running OSM box falls
through to OpenRouteService rather than failing.

You get a geocoded commute and a real Location subscore. Amenity counts still wait
for Overpass, so the component scores at reduced confidence and says why - one
input out of two is a real answer with half the evidence behind it.

Note on transit: ORS has no public-transport profile, so a transit request is
answered with driving time, labelled an estimate and discounted in confidence. A
genuine transit figure needs GTFS, which arrives with the self-hosted stack.

### The OpenStreetMap stack (location, commute, amenities)

This is the one with real setup cost: an Ontario extract import takes hours and wants a modest
server, not a laptop tab.

```bash
docker compose --profile osm up nominatim overpass
```

OSRM needs its graph pre-processed before it will serve:

```bash
mkdir -p data/osrm && cd data/osrm
curl -O https://download.geofabrik.de/north-america/canada/ontario-latest.osm.pbf
docker run -t -v "$PWD:/data" osrm/osrm-backend osrm-extract -p /opt/car.lua /data/ontario-latest.osm.pbf
docker run -t -v "$PWD:/data" osrm/osrm-backend osrm-partition /data/ontario-latest.osrm
docker run -t -v "$PWD:/data" osrm/osrm-backend osrm-customize /data/ontario-latest.osrm
```

Then point the API at them:

```
PDE_NOMINATIM_URL=http://localhost:8081
PDE_ROUTING_URL=http://localhost:5000
PDE_OVERPASS_URL=http://localhost:8082
```

Refresh the extract monthly. Self-hosting is the path OSMF policy directs geocoding-dependent
applications to, and it is what lets us store the results permanently under ODbL (ADR 0002).

### Everything at once

```bash
docker compose up                 # db, api, web
docker compose --profile osm up   # ...plus the three OSM services
```

---

## Ports

| Port | Service |
|---|---|
| 3000 | Next.js web app |
| 8000 | FastAPI |
| 5432 | Postgres + PostGIS |
| 8081 | Nominatim |
| 5000 | OSRM |
| 8082 | Overpass |
| 11434 | Ollama |

---

## Troubleshooting

**"Failed to fetch" in the browser.** The API is not running, or its CORS list does not include
your origin. The API answers `http://localhost:3000` and `http://127.0.0.1:3000` by default; set
`PDE_CORS_ORIGINS` to change that. This exact failure is why the E2E suite exists — every
server-side test passed while the browser could not get past the preflight.

**Port already in use.** On Windows:

```powershell
foreach ($p in (Get-NetTCPConnection -LocalPort 8000 -State Listen).OwningProcess) {
  Stop-Process -Id $p -Force
}
```

**A 422 from `/analyze`.** That is usually the engines refusing an impossible file rather than a
bug — a down payment below the statutory minimum, for instance. The message is the engine's own
sentence and is meant to be shown to the user.

**Migrations fail with "type already exists".** A downgrade left its ENUMs behind. Drop and
recreate the database; the downgrade path drops them explicitly, and CI round-trips it on every
run to keep that true.
