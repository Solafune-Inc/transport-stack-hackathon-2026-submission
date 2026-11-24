# Delhi Bus Crowding: Phase 1 submission

Our entry for the **Transport Stack Hackathon 2026, Problem 2: a crowdedness-aware journey planner**.
It shows every Delhi bus route, stop and live bus, with the crowding you can expect on each route,
hour and day type. It also plans trips between any two stops, direct or with one change, ranked on
travel time **and** crowding. Crowding comes from October 2026 e-ticketing data (2.56 million tickets).

**[TECHNICAL_NOTE.md](TECHNICAL_NOTE.md)** has our proposal, the method and its assumptions, the checks
against known patterns, and where the estimates are least reliable.

This repository holds everything needed to run it: code, the crowding model, the team's EDA, and
Docker. It runs with one command.

## Run it

You need:
- Docker Desktop, or Docker Engine with Compose v2.24 or newer, with at least 4 GB of memory for Docker.
- The GTFS feed in `data/delhi_buses_static_gtfs/` (see [Data](#data)).

```bash
git clone https://github.com/Solafune-Inc/transport-stack-hackathon-2026-submission
cd transport-stack-hackathon-2026-submission
# add the GTFS first (see Data below)
docker compose up --build
```

| Open | What |
|---|---|
| http://localhost:8080 | The app (the web build of the mobile app) |
| http://localhost:8080/findings/ | **Team findings**: the EDA, validation and model reports, plus all figures |
| http://localhost:8787/api/health | The API (`"ok": true` once live buses are flowing) |

- **First build:** a few minutes, mostly `npm ci` and the Python wheels. After that, startup takes about 40 s. The API loads the whole
  network (2,554 routes) before the web container starts.
- **On a phone:** join the same Wi-Fi and open `http://<this-computer's-IP>:8080`.
- **To stop:** press `Ctrl+C`, or run `docker compose down`.

## Data

The data comes from the Delhi Transport Stack (Department of Transport, GNCTD) under its License
Agreement v1.0. Raw datasets must not be redistributed on their own, so this folder ships only
**derived, aggregated** data.

| Data | In this folder? | Where |
|---|---|---|
| Crowding model tables and the operator table (derived) | **Yes**, gzipped, 13 MB | `data/eticketing/*.csv.gz`, documented in [data/MODEL_CARD.md](data/MODEL_CARD.md) |
| Delhi Buses GTFS Static (raw) | **No**, you add it (gitignored) | `data/delhi_buses_static_gtfs/*.txt`, mounted read-only into the API |
| GTFS-RT live feed | Fetched live by the API | Needs an API key (optional) |
| E-ticketing, October 2026 (raw) | No | Only needed to rebuild the model or the EDA (see [Without Docker](#without-docker)) |

**Getting the GTFS:** sign in at https://delhi.transportstack.in, open Data & Services, then "Delhi
Buses GTFS Static", then Download (accept the licence). Unzip it so that `routes.txt`, `trips.txt`,
`stop_times.txt`, `stops.txt` and `shapes.txt` sit directly in `data/delhi_buses_static_gtfs/`.
If the files are missing, the API exits with a message saying so.

**Live buses (optional):**
- Run `cp .env.example .env` and set `TRANSPORTSTACK_API_KEY`.
- Without a key, everything works except live buses: `/api/live` returns 503.
- The key stays on the API container at runtime. It never goes into an image or the app.

## What's inside

```text
browser / phone ──► web  (nginx :8080) ── /           app: Expo web build (React Native Web, Leaflet + MapLibre)
       │                               └─ /findings/  team findings: reports, figures, notes
       └──────────► api  (FastAPI :8787) ── GTFS (mounted, read-only) + crowding tables (in the image)
                                         └─► Delhi Buses GTFS-RT feed (polled every 15 s; needs the key)
```

| Path | Contents |
|---|---|
| `TECHNICAL_NOTE.md` | Proposal, method, assumptions, checks and limits |
| `LICENSE` | Apache License 2.0, for the code (see [License](#license) for the data) |
| `docker-compose.yml`, `docker/` | The two services (`api`, `web`) and a `tests` profile |
| `src/api/` | API: network loading, crowding by day type, stop index, timetable, planner (`journeys.py` for one change) |
| `src/model/crowding.py`, `src/resolve_stops.py`, `src/ml/` | The crowding pipeline and the demand-model experiment |
| `src/eda_*.py`, `src/make_*.py` | The team's EDA and report generators |
| `mobile-implementation/` | The Expo / React Native app (Android, iOS and web from one codebase) |
| `data/` | Crowding model tables, model card, dataset notes, licence notes |
| `reports/`, `notebooks/` | EDA and validation reports, figures, EDA notes |
| `findings/index.html` | The team findings page served at `/findings/` |
| `docs/` | The product plan (`PLAN.md`) and the ML plan with the model decision (`ML_PLAN.md`) |
| `SNAPSHOT.txt` | The commit in the team's working repository that this copy was made from |
| `scripts/sync_from_repo.sh` | Maintainers only: refreshes this copy from the team's working repository |

**API endpoints:**

| Endpoint | Returns |
|---|---|
| `/api/health` | Status, with routes loaded and today's day type |
| `/api/live` | Live buses with expected crowding |
| `/api/stops`, `/api/stops/{id}` | All stops, or one stop with its routes, buses and busyness |
| `/api/routes?ids=…`, `/api/routes/{id}` | Routes, with crowding by hour for the day type of `?date=` |
| `/api/shapes?ids=…` | Route shapes |
| `/api/plan?from=&to=&t=&date=&transfers=1` | Trip options, direct or with one change, with crowding |

Interactive docs for every endpoint and parameter, where you can try each call: http://localhost:8787/docs
(OpenAPI schema at `/openapi.json`).

## What we found

The findings page (http://localhost:8080/findings/) walks through the analysis step by step, with
links to every report:

1. **The bus network (GTFS EDA).** 2,554 routes and 6,812 stops in a clean feed. The schedule is
   the same every day, so crowding has to come from ticket data.
2. **Who rides when (e-ticketing EDA).** 2.56 million October tickets, each with both its boarding
   and alighting stop. Demand peaks at 09:00 and 18:00.
3. **Linking tickets to stops.** Matching only against each route's own stops resolves 97.9% of
   tickets to GTFS stops.
4. **Crowding model.** For each route stretch, hour and day type, load is boardings minus alightings,
   with confidence flags. The weekday morning peak is about three times Sunday's.
5. **Demand model choice.** On a held-out week, B2 (hierarchical Poisson–Gamma smoothing) beats the
   monthly average by about 27% where the planner needs it. Gradient boosting added almost nothing.

## Team

SOLAFUNE.

## Demo video

The demo video (about 2½ minutes) is submitted with this entry. It was recorded from this app
running on live data, so the live buses, stops and planner results in it are real. The narration
voice is Kokoro-82M, a neural text-to-speech model run locally.

## Tests

```bash
docker compose --profile test run --rm tests     # Python tests (17)
cd mobile-implementation && npm ci && npm test && npm run typecheck   # app tests (Node >= 22.13)
```

## Without Docker

Use Python 3.12 and Node 22.13 or newer.

```bash
pip install -r requirements.txt
gunzip -k data/eticketing/*.csv.gz          # the server reads the uncompressed tables
python src/api/main.py                      # API on :8787
cd mobile-implementation && npm ci && npm start   # Expo Go on a phone, or: npx expo start --web
```

Rebuilding the model and EDA needs the raw October 2026 e-ticketing data, shared with Problem 2
teams through the Transport Stack platform (see [data/README.md](data/README.md)). Unzip it to
`data/eticketing/October-Delhi.csv`, next to the GTFS in `data/delhi_buses_static_gtfs/`. Then:
- `python src/resolve_stops.py && python src/model/crowding.py` rebuilds the model.
- `python src/eda_full.py`, `python src/eda_eticketing.py` and the `src/make_*_report.py` scripts rebuild the EDA.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `api` exits with "GTFS static feed not found" | Add the GTFS files (see [Data](#data)) |
| A port is already in use | Change `8080:80` or `8787:8787` in `docker-compose.yml`. If you move the API port, rebuild the app with the new address: `EXPO_PUBLIC_LIVE_API_URL=http://localhost:<port> docker compose up --build` |
| No live buses | Check that the key is set; `/api/health` shows the feed status |
| Grey map, no streets | The basemap tiles (OpenFreeMap) need internet. Stops, routes, crowding and the planner still work |
| `api` is killed while starting | Give Docker at least 4 GB of memory. The API peaks at about 1.7 GB while loading |
| You only want this computer to reach it | Use `127.0.0.1:8080:80` and `127.0.0.1:8787:8787` in `docker-compose.yml`. By default the ports are open on your network so phones can connect |

**Not run in Docker:**
- `src/live_server.py` is an earlier live-map server, superseded by the API.
- `src/demo_live_map.py` and `src/track_bus.py` write HTML maps that contain raw vehicle positions.
- `src/query_crowding.py` reads monthly tables that aren't shipped.

**For maintainers:** this repository is a copy of the team's working repository. There, run
`bash submission_1st_phase/scripts/sync_from_repo.sh` to refresh the copied code, reports, model tables
and `SNAPSHOT.txt`. It never touches the files written for this copy:
- this README and `TECHNICAL_NOTE.md`;
- `docker/` and `docker-compose.yml`;
- `findings/` and `data/MODEL_CARD.md`;
- `.env.example`, `.gitignore`, `LICENSE` and `requirements-api.txt`.

## License

- **Code:** Apache License 2.0, in [LICENSE](LICENSE).
- **Data:** the crowding tables in `data/eticketing/`, and the reports and figures in `reports/` and
  `notebooks/figures/`, are derived from Delhi Transport Stack data. The Apache licence doesn't cover
  them. They are shared under the Transport Stack data License Agreement v1.0: credit Delhi Transport
  Stack, and use them only for non-commercial purposes. Our changes are listed in
  [data/MODEL_CARD.md](data/MODEL_CARD.md). Figures with a map background also show map data
  © OpenStreetMap contributors.

## Credits

- **Data:** Delhi Transport Stack (Department of Transport, GNCTD), used under the Transport Stack data
  License Agreement v1.0, for non-commercial use. The tables are derived and aggregated by the team;
  the changes are listed in [data/MODEL_CARD.md](data/MODEL_CARD.md). Live positions come from the
  Delhi Buses GTFS-RT feed.
- **Basemap:** [OpenFreeMap](https://openfreemap.org), © [OpenMapTiles](https://openmaptiles.org),
  map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors.
- **Python:** FastAPI (MIT), uvicorn (BSD-3-Clause), pandas and NumPy (BSD-3-Clause), matplotlib (PSF-based),
  gtfs-realtime-bindings and protobuf (Apache-2.0 / BSD-3-Clause), scikit-learn (BSD-3-Clause, model
  comparison only), folium (MIT), contextily (BSD-3-Clause), Markdown (BSD-3-Clause), pytest (MIT).
- **App:**
  - Expo and React Native (MIT), React Native Web (MIT), react-native-webview (MIT),
    react-native-safe-area-context (MIT), @expo/vector-icons (MIT; Material Icons, Apache-2.0).
  - Leaflet (BSD-2-Clause), MapLibre GL JS (BSD-3-Clause), MapLibre GL Leaflet (ISC),
    Leaflet.PolylineOffset (MIT).
  - esbuild (MIT), Jest / jest-expo (MIT).
- **Serving:** Docker and Docker Compose; nginx (BSD-2-Clause); the official `python`, `node` and `nginx` images.
- **Demo video:** Kokoro-82M and misaki (Apache-2.0) for the narration voice, with PyTorch (BSD-3-Clause)
  and espeak-ng (GPL-3.0); Playwright (Apache-2.0); FFmpeg via imageio-ffmpeg (LGPL/GPL; BSD-2-Clause);
  Pillow (HPND).
- **AI tools:** developed with the help of GitHub Copilot and Claude Code (AI coding assistants).
