# Prototype Plan — Problem 2: Crowdedness-Aware Journey Planner

> Phase 1 deliverable for the Transport Stack Hackathon 2026.
> Target problem: **Problem 2**. See [HACKATHON.md](./HACKATHON.md) for the brief.
> Planning date: 2026-11-11 · Phase 1 deadline: **25 Nov 2026** (~2 weeks).

## 1. The product in one sentence

A journey planner that, for a trip from A to B, returns bus route options ranked
on **both estimated travel time and expected crowdedness** — where crowdedness is
estimated from Delhi's e-ticketing / ETM data by time of day.

## 2. Who it's for & why it matters

- **Commuter:** "Which bus should I take — and will I get a seat / be able to board?"
  Today's planners answer *when*, never *how packed*.
- **Operator (secondary):** sees where/when load concentrates → capacity planning.

The judged success criteria (from the brief) we must hit:
1. Planner **shows crowdedness estimates alongside route options**.
2. Estimates are **grounded in the ticketing data**.
3. Estimates **hold up vs known peak / off-peak patterns** (our validation story).

## 2b. Competitive landscape — existing Delhi journey planners

> Researched 2026-11-11 (web). Takeaway: **journey planning + live bus tracking for
> Delhi is a solved, crowded space; crowdedness grounded in the city's own
> ticketing data is an open white space.** That is exactly where Problem 2 sits.

| App | Journey planning | Live bus tracking | Ticketing | Crowdedness | Notes |
|---|---|---|---|---|---|
| **One Delhi** (official GNCTD) | ✅ universal planner | ✅ 7,300+ DTC + cluster buses, real-time ETA | ✅ QR, 10% e-ticket discount | ❌ | Built by **Chartr** with Transport Dept & IIIT-D — *the same operator running this hackathon* |
| **Chalo** | ✅ | ✅ GPS-based ETA | ✅ passes + tickets | ⚠️ "Live Passenger Indicator" **in select cities only** (Delhi unconfirmed) | Real-time device-based occupancy |
| **Tummoc** | ✅ patented multimodal (bus+metro+auto+cab) | ✅ DTC live tracking | ✅ all-in-one ticket | ❌ | Also shows cost + carbon saved |
| **Google Maps** | ✅ | ✅ live traffic delays for buses | ❌ | ⚠️ crowdedness **predictions** via opt-in crowdsourcing + AI/historical | 100 countries; not grounded in Delhi ticketing |
| **Moovit** | ✅ | ✅ updated DTC feed | — | ⚠️ global crowdedness (APC sensors + ticket data + crowdsourcing); Delhi unconfirmed | — |
| **DMRC Momentum** | metro-focused | — (metro) | ✅ metro | ❌ | Official Delhi Metro app |
| **Transport Stack Multimodal Journey Planner** | ✅ (API, approval-based) | — | — | ❌ | The hackathon's **own platform API** |

### How crowdedness is done elsewhere (and why ours differs)
- **Sensor-based (Moovit/Transit, Surat):** automatic passenger counters (APC) on
  vehicles → direct but needs hardware Delhi's fleet largely lacks.
- **Crowdsourced (Google Maps):** opt-in rider surveys + AI on historical trends →
  broad coverage but sparse, noisy, not tied to actual ridership.
- **Real-time device (Chalo):** proprietary on-bus signals in select cities.
- **Ours (ticketing/ETM-grounded):** estimate load from Delhi's **actual
  e-ticketing + ETM boarding records** — real ridership, open and reproducible,
  no extra hardware. This matches the brief's "grounded in the ticketing data"
  criterion and is **not offered by any incumbent for Delhi**.

### Implications for our prototype
1. **Don't compete on travel-time/ETA** — One Delhi, Google, Chalo, Tummoc, Moovit
   already do it well. (Reinforces choosing Problem 2 over Problem 1.)
2. **Crowdedness is the differentiator** — and specifically *ticketing-grounded*
   crowdedness, which no Delhi planner surfaces.
3. **Complement, don't duplicate, One Delhi** (same operator, Chartr) — frame our
   output as an open-source crowding component that could feed One Delhi / Transport
   Stack, aligning with the hackathon's "open-source component" goal.
4. **Benchmark opportunity:** we can sanity-check our estimates against the qualitative
   crowd signals these apps expose and against known peak/off-peak patterns.

Sources (links verified 2026-11-11):
[One Delhi — Google Play](https://play.google.com/store/apps/details?id=com.delhitransport.onedelhi),
[One Delhi — App Store](https://apps.apple.com/in/app/one-delhi/id1641749010),
[Chalo](https://chalo.com/),
[Tummoc — Google Play](https://play.google.com/store/apps/details?id=org.transhelp.bykerr),
[Moovit](https://moovit.com/),
[Transit — crowding (sensor/ticket/crowdsource method)](https://transitapp.com/banners/crowding),
[Google Maps crowdedness — Google Transit Partners](https://support.google.com/transitpartners/answer/9551309?hl=en),
[Surat real-time occupancy — Data for Public Good](https://dataforpublicgood.org.in/blog/rush-for-seats-no-more/).

## 3. The core idea — how we turn tickets into crowding

Tickets record **boardings** (route, direction, boarding stop, timestamp, pax).
On-vehicle load is a *cumulative* quantity along the route:

```
load(segment i→i+1) = Σ boardings at stops ≤ i  −  Σ alightings at stops ≤ i
crowding_index      = load / vehicle_capacity          # per bus type
crowding_level      = bucket(crowding_index)           # Low / Medium / High
```

- **Boardings** come straight from ticket aggregation per (route, direction, stop, time-band).
- **Alightings** — two cases:
  - *If the ticket carries a fare stage / destination* → alighting stop is known directly (best case).
  - *If only boarding is recorded* → estimate alightings with a simple model
    (e.g. distance-decay / proportional to downstream boarding demand), stated as an assumption.
- **Capacity** by bus type (standard ~ seated+standing); documented constant to start.
- **Time-bands:** 30- or 60-min buckets, by day-type (weekday / weekend).

This "boarding/alighting → load profile" method is the technical heart and the
thing we document in the technical note.

> Coverage note: e-ticketing alone captures only ~3–4% of bus tickets; **ETM data
> is the higher-coverage source** and should anchor the estimate. Scale/weight to
> known ridership where possible, and state uncertainty.

## 4. Scope

> **Note (2026-11-12):** the earlier crowding model, ticket schema, and synthetic
> e-ticketing generator were **removed** — they were built on *hypothetical* data.
> We'll rebuild the ingestion + crowding model on the **actual e-ticketing/ETM
> datasets** once access lands. The method (Section 3) still stands as the design.

### MVP (must-have for Phase 1)
- [x] Ingest GTFS static (routes, stops, schedules) — `src/data/gtfs.py` (`GTFSFeed`).
- [x] Ingest **real** e-ticketing data (Oct 2026, 2.56M tickets) — `src/eda_eticketing.py`;
      schema in `data/README.md`. Boardings **and** alightings both observed.
- [x] Resolve e-ticketing stop names → GTFS stops — `src/resolve_stops.py`
      (route-scoped fuzzy; **97.9%** of tickets, coords attached).
- [x] Crowding model on real data → `(route, segment, hour) → crowding level`
      — `src/model/crowding.py`. Boardings − alightings → per-vehicle load profile → level.
- [x] Validation: crowding peaks at rush hour (08–09, 18–19), dips off-peak; load returns
      to ~0 at terminus (alight/board = 1.0); 98.7% forward-consistent. Report:
      `reports/crowding_report.html`.
- [x] Crowding query ("will my bus be crowded?") per route/hour/leg — `src/query_crowding.py`.
- [x] Journey options for an O→D with **schedule travel time + crowding per option** — server
      planner for any two stops (`GET /api/plan` in `src/api/`, direct trips, same-named stops across
      the road count as one), ranked in the app (`mobile-implementation/src/logic/planner.ts`).
- [x] A ranking that trades off time vs crowding (Balanced / Fastest / Least crowded + "less
      crowded bus" suggestion).
- [x] Map UI with options + crowding badges — Expo / React Native app (`mobile-implementation/`)
      instead of the planned Next.js page.

### Stretch (if time allows)
- **Learned crowding model (ML)** — day types, Poisson demand model, ride-length model,
  coverage calibration, uncertainty, perceived-time ranking. Plan, evidence and gates:
  **[ML_PLAN.md](./ML_PLAN.md)** (2026-11-23).
- Multi-leg / transfer journeys. ✅ **One change done (2026-11-23):** `/api/plan?transfers=1`
  (`src/api/journeys.py`), shown in the app's planner and on the map.
- "Leave later for a less crowded bus" suggestion.
- Confidence / uncertainty shown per estimate.
- Real-time flavour by blending GTFS-RT positions (optional, P1 territory). ✅ **Done
  (2026-11-19):** the app shows every bus in the feed (~6,000) via `src/api/`, each
  snapped to its route with the expected crowding of its current stretch. **2026-11-22:** the
  two demo routes were dropped; the map covers the whole network (stops and buses when zoomed
  in; tap a stop for its routes in both directions and only their buses; tap a bus for its route).
- **Multimodal (bus + metro) crowding view** — *organizer-encouraged (2026-11-12)*;
  layer metro crowding from footfall (`datadetails/4`) + OD (`datadetails/9`) on top
  of the bus baseline. Strong differentiator / likely bonus; pursue after the bus MVP.
  **Moved to Phase 2 (2026-11-23):** no metro data yet (see "Next step" below).

### Next step: trips with a change + metro (plan 2026-11-23)

**Why trips with a change come first:** in 1,500 trips of 2–20 km (origins and destinations
weighted by real boardings), only **28%** have a direct bus, which is all the planner answers today.
**63%** need exactly one change, and 9% need more. This ignores timetables, so 63% is an upper bound.

**Phase 1 (by 25 Nov):**

- **Must:** finish the technical note, demo video, README and proposal. The proposal shows the
  finding above, the designs below, and readiness for Problem 5 (metro + bus crowding).
- **Data actions (no code):**
  - download the DMRC GTFS static and the metro gate locations (both Open)
  - chase the metro footfall/OD approvals (pending since 12 Nov) and ETM
  - ask whether shortlisted teams get the metro AFC data
- ✅ **Done 2026-11-23:** the one-change bus planner, `/api/plan?transfers=1`
  (`src/api/journeys.py`), used by the app. In 300 trips of 2–20 km at 09:00 on a weekday, it
  raised the share with an answer from 23% (direct only) to 94%. Queries take 18 ms median and
  103 ms at the 95th percentile.

**Phase 2 (25 Nov → 10 Dec), in order:**

| Dates | Work |
|---|---|
| 25–27 Nov | ~~Trips with one change (bus → bus)~~ **done 2026-11-23** (23% → 94% of sampled trips answered). Left for this slot: spot-check 10 well-known trips against a public planner; two changes if needed. |
| 27–29 Nov | **Crowding ranges** ("Medium, could be High"), see [ML_PLAN.md](./ML_PLAN.md) §7 |
| 30 Nov–2 Dec | **Bus + metro trips:** DMRC GTFS as a second mode, station ↔ bus stop walks ≤ 400 m, metro lines on the map. Metro crowding shown as "no data yet". |
| 3–6 Dec | **Metro crowding** if footfall + OD (or Problem 5 AFC) data has arrived: hourly OD by iterative proportional fitting → shortest-path assignment → load per segment ÷ (trains/hour × train capacity). Otherwise: live per-bus crowding (gap to the bus ahead). |
| 7–10 Dec | Freeze: technical note v2, demo video, rehearsal |

### Explicitly out of scope for Phase 1
- Full multimodal *routing* / transfers as a core deliverable (bus-only crowding is
  the committed MVP; a metro crowding **layer** is the stretch above).
- Production auth, scaling, polished design system.

## 5. Architecture

```
          ┌─────────────── Stage 2 (add later) ───────────────┐
          │  Frontend: React/Next + map (MapLibre/Leaflet)     │
          │  - search A→B, show ranked options + crowding badge │
          └───────────────────────┬────────────────────────────┘
                                   │ HTTP (JSON)
          ┌────────────────────────▼───────────────────────────┐
          │  Stage 1: Python backend — FastAPI                   │
          │  GET /crowding?route&time   GET /journey?from&to&time│
          └───────┬───────────────────────────────┬─────────────┘
                  │                                 │
      ┌───────────▼──────────┐          ┌──────────▼───────────┐
      │ Crowding model        │          │ Journey/routing       │
      │ (pandas + sklearn)    │          │ (GTFS schedule-based) │
      └───────────┬──────────┘          └──────────┬───────────┘
                  │                                  │
      ┌───────────▼──────────────────────────────────▼──────────┐
      │ Data layer: GTFS static (have) + e-ticketing/ETM (real,  │
      │ awaiting access — ingested when it lands)                  │
      └──────────────────────────────────────────────────────────┘
```

**Stack** (per team strengths): Stage 1 = Python/data-science (pandas,
scikit-learn, FastAPI, a Jupyter EDA/validation notebook). Stage 2 = React/Next.js
with a map library. Keep the frontend talking to the API only — the model stays in Python.

## 6. Repo layout (target)

```
src/
  data/        # gtfs.py (done); tickets.py (ingest REAL e-ticketing/ETM — add with data)
  model/       # crowding.py (boarding→load→level) — build on real data
  routing/     # journey.py (GTFS schedule-based candidate finder)
  api/         # main.py (FastAPI: /crowding, /journey)
  web/         # Stage 2 frontend
notebooks/     # EDA findings & figures
data/          # raw datasets (gitignored) + data/README on how to fetch
```

## 7. Data plan & the gap

- **Available now (build immediately):** GTFS static (bus routes/stops/schedules) —
  Open on the catalogue. Lets us build routing + the whole skeleton today.
- **Pending:** e-ticketing / ETM — **not in the public catalogue**. Request email sent
  2026-11-11; organizer replied 2026-11-12 that access is granted **on request ("by
  today")** — **awaiting actual access**. Still a critical-path risk until it lands.
- **Scope & datasets confirmed by organizer (2026-11-12):**
  - Minimum scope is **buses**; a **multimodal (bus + metro) view is encouraged** (bonus, not required).
  - **No other immediately relevant datasets** beyond: bus GTFS, e-ticketing/ETM,
    metro **hourly footfall** (`datadetails/4`), metro **yearly OD** (`datadetails/9`).
    Others may be explored later in the hackathon.
  - → **Committed MVP: bus-only crowding. Stretch: add a metro crowding layer for a
    multimodal view** (would need the two metro datasets, both approval-based).
- **Approach while waiting (decided 2026-11-12):** **no synthetic stand-in** — the
  crowding model will be built on the **actual** e-ticketing/ETM data to keep results
  credible. Meanwhile, make progress on the parts that need only GTFS: the
  **journey-planner routing + schedule travel time**. Crowding layers on once data lands.

## 8. Timeline (Nov 11 → 25)

| Days | Dates | Milestone |
|---|---|---|
| 1–2 | Nov 11–12 | Data requests sent; repo skeleton; GTFS loaded; comprehensive EDA ✅ |
| 3–5 | Nov 13–15 | **Journey-planner routing** on GTFS (`/journey`, schedule travel time); map UI skeleton |
| 6–8 | Nov 16–18 | **On real data:** ingest e-ticketing/ETM → **crowding model** (boarding→alighting→load→level) + validation |
| 9–11 | Nov 19–21 | Wire crowding into the planner (`/crowding`, time-vs-crowding ranking); map UI end-to-end |
| 12–13 | Nov 22–23 | Peak/off-peak validation on real data; write **technical note** |
| 14 | Nov 24–25 | **Demo video**, README, final checks, **submit** (proposal + prototype + repo URL) |

## 9. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| e-ticketing/ETM data arrives late | High | Build GTFS-only parts (routing/journey planner) first; crowding model is quick to add once data lands |
| Tickets lack alighting/destination | Med | Alighting-estimation model; document assumption; validate load shape |
| Low ticket coverage (3–4% e-ticket) | Med | Anchor on ETM; scale to ridership; report uncertainty |
| Scope creep (multimodal, transfers) | Med | Keep those in Stretch; protect the MVP demo |
| "Mock-only won't qualify" (rule) | High | Prototype must run end-to-end on the **real** datasets (no synthetic in the submission) |

## 10. Definition of done (Phase 1 submission checklist)
- [ ] Working prototype runs end-to-end (A→B query → ranked options with crowding).
- [ ] Source code + README (how to run, how to fetch data).
- [ ] Short technical note (the boarding→load method + validation + assumptions).
- [ ] Short demo video.
- [ ] Repo URL submitted on Where U Elevate before 25 Nov.
```
