# ML Plan — Problem 2: learned crowding model for the journey planner

> Planning date: **2026-11-23**. Companion to [PLAN.md](./PLAN.md) (product plan) and
> [HACKATHON.md](./HACKATHON.md) (brief). Phase 1 is due **25 Nov**; the Phase 2 build sprint
> runs **25 Nov → 10 Dec** (shortlisted teams refine Phase 1 work), finale **11 Dec**.
>
> **Defaults chosen (revisit if wrong):** small ML slice for Phase 1, full ML in Phase 2 ·
> **scikit-learn only** (no native deps; already the stated stack) · ETM data treated as
> **pending**: the plan works without it and gets better if it arrives.
>
> Revised the same day after an independent design review: consistent time cohort, leakage-safe
> splits, honest intervals, a full serving contract, and a smaller Phase 1 slice.
>
> **Experiment result (2026-11-23, §1b):** on the held-out week, the **statistical model B2**
> (hierarchical Poisson–Gamma smoothing) is ~27% better than today's average at the route-hour
> level the planner uses. Gradient boosting adds only ~3% at stop level, and nothing at
> route-hour level. Per the pre-registered gate, **B2 is the demand model (M1)**.
>
> **In the app (2026-11-23):** crowding is served by day type, with B2 setting each route-hour's
> day-type level (P1-2 via B2), plus volume-aware confidence (P1-1). See §5 "Implemented" and §7.

## 1. Why ML, and what's wrong with today's model

Today `src/model/crowding.py` is a **deterministic lookup**: for each `(route, hour)` it sums the
whole month's mobile tickets, walks boardings minus alightings along the GTFS stop sequence, and
divides by `COVERAGE (4.5%) × GTFS trips × 31 days × CAPACITY (60)`. It's validated on shape
(bimodal peaks, load back to ~0 at the terminus), but probing the real data (2026-11-23) shows
four structural weaknesses. "Pax" below means summed `passenger_count`.

| # | Finding (October e-ticketing, 2.56 M tickets) | Consequence today |
|---|---|---|
| 1 | **Signal is strong and stable**: weekday route-hour pax/day, 1–15 Oct vs 16–31 Oct, Pearson **0.981**, Spearman **0.891** (log-Pearson 0.958). | Demand is learnable, so a model can generalise instead of memorising one month. |
| 2 | **Cells are very sparse**: pax per route-hour per *month* median **21** (p25 = 5); per route-stop-hour median **2**; per route-hour-*day* median **3**. | Raw ratios are noisy wherever volume is low; nothing pools strength across hours, stops or similar routes. |
| 3 | **Day type matters a lot.** At 09:00, pax/day: weekday **14,327**, Saturday **11,698**, Sunday/holiday **4,866**. At 18:00: **9,902 / 6,650 / 3,933**. Holidays behave like Sundays: **2 Oct** Gandhi Jayanti 45.7 k, **20 Oct** Dussehra 56.1 k, vs ~98–110 k on most weekdays. | The monthly average **under-states weekday peaks by 16–17%** and **over-states Sunday/holiday peaks 2.1–2.5×** (09:00 and 18:00). |
| 4 | **"Low" often means "few mobile tickets"**, not "empty bus": all **9,186 / 20,739** route-hours with < 30 pax/month are labelled Low; **97.7%** of High/Very High labels come from route-hours with ≥ 100. Among routes with ≥ 10 GTFS trips/day, mobile pax per scheduled bus range **0.01 (p10) → ~3 (p90)**; **90** frequent GTFS routes have **zero** mobile tickets. | One global coverage constant can't be right for every route: either mobile-ticket share or actual service differs by route. Sparse routes are shown as confidently uncrowded. |

Also checked and **ruled out**: reconstructing individual bus runs from `vehicle_number`
(51.5% of tickets) gives a median of **1 ticket per run** (p90 = 3), far too sparse for
trip-level targets. ML therefore works at the aggregated demand level.

## 1b. Experiment: statistical models vs machine learning (run 2026-11-23)

[src/ml/compare_models.py](./src/ml/compare_models.py) →
[reports/ml_model_comparison.json](./reports/ml_model_comparison.json) (~50 min on a 16-core laptop).

**Setup**
- **Target:** boardings per day for every (route, stop position, hour, day type), about 3.07 M
  cells. That's M1's grain, with hour = ticket purchase hour as today.
- **Protocol (§4):** tickets split by date first. Tuning trained on 1–17 Oct and validated on
  18–24 Oct. The final test trained on 1–24 Oct and was **run once** on 25–31 Oct, with 621 k
  passengers.
- **Cells:** only 1.5% of test passengers fall outside the modelled cells (the timetable plus cells
  seen in training).

| ID | Model | Kind |
|---|---|---|
| B0 | Today's approach: average over all days, no day types | baseline |
| B1 | Plain average per day type | baseline |
| **B2** | **Hierarchical Poisson–Gamma (empirical Bayes)**: each cell is a weighted blend of its own count and a prior built from smoothed route × hour × day-type volume × the route's stop share in that time band. Route volume itself is smoothed toward scheduled trips × network passengers per trip. 6 smoothing strengths, tuned on validation (Clayton & Kaldor 1987). | statistical |
| GLM | Penalised Poisson log-linear model (ridge, ≈ random effects): route × day type, route × hour, hour × day type, route-stop, route-stop × time band, stop × time band, log scheduled buses. 452 k coefficients. | statistical |
| GBM | `HistGradientBoostingRegressor(loss="poisson")`: 15 schedule, route and stop features plus 8 historical rates (including B2's estimate), taken from the other half of the training days | ML |
| GBM+B2 | The same boosting, learning a multiplicative correction on top of B2 (B2 as offset) | hybrid |

**Final test (25–31 Oct).** Poisson deviance: lower is better. WAPE: weighted absolute error.
ρ: Spearman rank correlation over weekday route-hours with ≥ 10 passengers.

| Model | Stop deviance | vs B2 | Route-hour deviance | Route-hour WAPE | ρ | Predicted / actual | Fit time |
|---|---|---|---|---|---|---|---|
| B0 (today) | 0.364 | −10.8% | 1.880 | 0.385 | 0.902 | 1.02 | < 1 s |
| B1 | 0.412 | −25.7% | 1.723 | 0.342 | 0.901 | 1.07 | < 1 s |
| **B2** | **0.328** | — | **1.369** | **0.294** | 0.904 | 0.96 | **< 1 s** (tuning search 17 s) |
| GLM | 0.342 | −4.1% | 1.402 | 0.301 | 0.904 | 0.98 | 1.5 min |
| GBM | 0.318 | +3.0% | 1.385 | 0.301 | 0.906 | 0.98 | 6.5 min |
| GBM+B2 | 0.318 | +3.0% | 1.387 | 0.301 | 0.906 | 0.99 | 7 min |

The validation window (18–24 Oct) tells the same story: B2 0.336 · GBM 0.324 (+3.5%) ·
GBM+B2 0.325 · GLM 0.347 · B0 0.392 · B1 0.463.

**Findings**
1. **The statistical model is the right choice now.**
   - B2 cuts today's route-hour error by **27%** in deviance and **24%** in WAPE (0.385 → 0.294).
     On the busiest route-hours (≥ 100 pax in training) the deviance drops by **33%**
     (4.34 → 2.92).
   - It fits in under a second with NumPy alone, and every estimate is explainable as "own data
     blended with a prior".
2. **ML gives little on top, and only at stop level.**
   - GBM beats B2 by 3.0% at stop level. The gain is largest on cells with no training history
     (−5%) and on the busiest cells (−7.5%).
   - At route-hour level, which is what the planner and crowding levels use, GBM is 1.2% *worse*
     overall and 7% worse on the largest stratum (1–29 training pax, 51 k route-hours).
   - It fails gate G1 (≥ 5% and no stratum worse), so **B2 ships**. The hybrid adds nothing over
     plain GBM.
3. **Day types only help when smoothed.** Plain per-day-type averages (B1) are 26% *worse* than
   today at stop level, because splitting the month makes thin cells thinner. B2 gets the day-type
   gain without that cost.
4. **What the tuned smoothing says about the data:**
   - **Route-specific day-type effects are mostly noise at one month of data** (kB = 100 days, so
     a route's own Saturday pattern gets ~4% weight). Day-type differences are best taken from the
     **network's hour × day-type factor**.
   - Route-hour shapes, by contrast, are route-specific (kA = 3 days).
   - A cell's own count gets about 1/3 weight on weekdays (kC = 30 days vs 15 training weekdays).
5. **Counts are over-dispersed:** Pearson dispersion is ≈ 2.5 for every model. Poisson intervals
   would be ~1.6× too narrow, so use negative-binomial or quasi-Poisson intervals with φ ≈ 2.5.
6. **The test week's weekend was busier than October's average.** Weekdays matched (102.3 k vs
   102.4 k pax/day), but Saturday 31 Oct had 90.8 k vs a 78.9 k average, and Sunday 25 Oct had
   56.8 k vs 48.9 k. So B2 under-predicted the week by 4%. This is weekend variability, not a
   trend.
7. **Practical notes on ML:**
   - sklearn's Poisson boosting **diverged** (×50,000 predictions) with default-like L2. It needs
     strong L2 (`l2_regularization=1000`), because a Poisson Newton step overshoots on busy cells
     that start near zero, and sklearn has no step cap.
   - GBM was still improving at its 1,000-tree cap, and the GLM's solver hadn't converged at 1,000
     iterations. Neither is fully tuned. Both are unlikely to close the route-hour gap.
   - Revisit ML when ETM or a second month of tickets arrives, because ML gains usually grow with
     data.

## 2. Framing: keep the physics, learn the uncertain parts

Crowding is a ratio of **demand** to **supply**, scaled by **coverage**. The model keeps flow
conservation deterministic and learns only the parts that are noisy or unknown:

```
                 Σ_{i ≤ k}  B̂(r, i, h, d) · Ŝ(r, i → k, h, d)        ← M1 demand × M2 ride length
occ(r, k, h, d) = ─────────────────────────────────────────────
                     ĉ_r · N̂(r, h, d) · CAPACITY                    ← M3 coverage · M4 supply
```

**Units and cohort (one definition everywhere).** `h` is a **cohort hour bin**: the hour in which
a bus run's passengers are counted. `B̂` is sampled boarding pax **per service day** in that bin.
`N̂` is bus departures **per service day** in the same bin. The ratio is then passengers per bus,
with no extra 24 h or 31-day factor. The targets, supply features, denominator, day-type
assignment and every API lookup must use the same cohort definition:

- **Cohort A (default, = today):** ticket purchase hour; supply = the route's terminal departures
  in that hour. This is what `crowding.py` and the API use now.
- **Cohort B (experiment in M0):** a ticket is counted at the **terminal departure hour of its bus
  run** (see trip-hour alignment below). It only ships if it validates, and then it applies to
  every component at once.

| Symbol | Meaning | Source today | Planned |
|---|---|---|---|
| `B̂(r,i,h,d)` | expected sampled boardings per service day at stop position *i* | raw monthly sum | **M1**: Poisson gradient boosting |
| `Ŝ(r,i→k)` | P(a rider boarding at *i* is still on board past stop *k*) | implicit in observed alightings | **M2**: smoothed ride-length model |
| `ĉ_r` | mobile-ticket share of route *r*'s riders | 0.045 for every route | **M3**: calibration (needs ETM) / prior + flag |
| `N̂(r,h,d)` | departures per service day in the cohort bin | GTFS schedule | **M4**: GTFS-RT archive (conditional) |

Why this shape:
- **Conservation by construction:** load = boardings × survival, so it can't go negative and
  returns to 0 at the terminus. Separately predicted boardings and alightings wouldn't guarantee that.
- **Each factor is checked separately** (demand on held-out days, ride length on held-out tickets,
  coverage against ETM), so judges can trace every number back to tickets.
- **It degrades gracefully:** without ETM or GPS archives, M3 and M4 fall back to today's
  documented constants, and the improvement from M1 and M2 still applies.

**Not ML (on purpose):** routing and timetable (GTFS), stop-name resolution
([resolve_stops.py](./src/resolve_stops.py), already 97.9%), the load accumulation itself.

## 3. Model components

### Day types and calendar (shared by everything)
- Three day types, chosen from the daily totals: **weekday**, **Saturday**, **Sunday/holiday**
  (public holidays map to Sunday). October 2026 gives 20 / 5 / 6 days.
- [src/ml/daytypes.py](./src/ml/daytypes.py) holds the mapping and the holiday list (October holidays
  + Christmas so far; Diwali, 8 Nov 2026, is a Sunday anyway). Extend it from the Delhi Govt gazetted
  holidays before serving other months. (Not named `calendar.py`: that shadows Python's built-in
  module when scripts in `src/ml/` run.)
- The day type comes from the **service day of the trip's departure**, not the query time. GTFS
  times ≥ 24:00 belong to the previous service day, so a 23:50 query for a 00:20 departure uses
  the next day's type.

### Trip-hour alignment (cohort B), built in the dataset step
Today one bus that leaves the terminal at 08:40 and reaches mid-route at 09:20 has its tickets
split across two hours, which dilutes peaks. Cohort B re-keys each ticket to `purchase time −
scheduled offset(route, terminal → boarding stop)`, snapped to the nearest scheduled run, with an
explicit previous-service-day rule. Purchase time isn't exactly boarding time, and buses run late,
so before adopting it:
- **Validate** on tickets with `vehicle_number`: tickets from the same vehicle and route within one
  run should land in the **same cohort hour** much more often under B than under A.
- Keep cohort A as the fallback, and adopt B for every component or for none.

### M1 — Boarding demand model

**Decision (§1b): M1 = B2, the hierarchical Poisson–Gamma model.** It's implemented in
`b2_rates()` in [compare_models.py](./src/ml/compare_models.py), and the tuned strengths are in the
report. The gradient-boosting design below is kept as the experiment to re-run when more data
arrives (ETM, a second month of tickets).

- **Grain:** `(route, stop position, cohort hour, day type)`, only where GTFS schedules ≥ 1 run of
  that route in that cohort hour (about 3.1 M cells).
- **Target:** sampled boarding pax per service day = count / n_days(day type), with
  `sample_weight = n_days`. For Poisson loss this equals a log-exposure offset: the loss is
  `E·μ − C·log μ`, the Poisson log-likelihood of the count `C` with mean `E·μ`.
- **ML variant:** `sklearn.ensemble.HistGradientBoostingRegressor(loss="poisson")` with
  `l2_regularization=1000`, which is required: lighter L2 diverged (§1b).
- **Features**, all computed **inside each training fold** (see Section 4):
  - *Time:* hour, day type. No trend term: one row per day type has no date to fit a trend on,
    and trees don't extrapolate. Revisit only with daily rows and date-keyed outputs.
  - *Supply:* the route's runs in that cohort hour (same cohort as `N̂`); runs of **all** routes
    through the stop in that hour.
  - *Route:* number of stops, length (km), AC share, night-service flag (`(NS)`), direction,
    route-number family.
  - *Stop:* relative position i/n, first or last stop, number of routes serving it, name tokens
    (metro / terminal / border / depot), lat/lon, distance to Connaught Place, k-means zone (~50).
  - *Encodings:* route, stop and zone through `sklearn.preprocessing.TargetEncoder` (cross-fitted).
    Native categoricals cap at 255 levels, and there are 2,259 routes. Also **leave-route-out stop
    demand**: boardings at the same stop on *other* routes, so busy shared stops inform sparse
    routes.
- **Interpretability:** permutation importance and partial dependence (hour × day type), shown in
  the ML report and the technical note.

### M2 — Ride-length (alighting) model
- Trained on tickets with both ends resolved: 2.28 M usable, 98.7% forward-consistent.
- **M2a (baseline):** per route, the empirical OD split `P(alight j | board i)`, with Dirichlet
  smoothing toward a network-wide distance-decay prior; pooled by peak/off-peak × day type.
- **M2b (if M2a underfits sparse routes):** a discrete-time hazard classifier
  (`HistGradientBoostingClassifier`): "does the rider get off at stop j, given still on board?"
  Features: stops and km ridden so far, stops remaining, stop *j*'s alighting share across all
  routes (fold-local), terminal/metro flags, hour, day type.

### M3 — Coverage (expansion) calibration
- **If ETM arrives (preferred), first agree a population contract with the organizer:**
  - Does ETM include mobile sales? If they're disjoint, coverage = `M / (M + ETM)`, not `M / ETM`.
    Summing overlapping sets would double-count.
  - Are the units passengers or tickets? How are concessions and passes handled?
  - Do the time windows match?
  Then model the mobile share from route features (AC, zone, hour band, route volume) with
  shrinkage toward the network mean. Calibrate and apply it at the **same granularity**: either
  `ĉ_r` per route, or `ĉ_{r,band,d}` with route, hour band and day type. Check on held-out routes.
  This is the only true fix for finding #4.
- **Without ETM:**
  1. **Volume-aware `confidence`:** low when a route-hour has few tickets, not only when GTFS has
     few trips. The app already shows confidence.
  2. **Ranking guard:** an option with low confidence can't win "Least crowded" or "Balanced"
     because of its low point estimate; rank it on `occ_p90` or the prior instead. A poorly
     observed route must not look attractive just for lack of data.
  3. **Frequency-share prior, restricted to compatible lines:** for a given origin–destination pair,
     only routes that serve **both** stops in order are interchangeable (the common-lines
     assumption, Spiess & Florian 1989). Share the pooled demand on those lines by frequency, flag
     routes whose own tickets fall far below their share as likely under-covered, and shrink
     toward the prior with a wider interval.
  4. **Relative crowding,** labelled honestly as a ranking of **sampled demand** ("more mobile
     tickets than 80% of buses at this hour"). It's free of a *common* coverage constant, but not
     of route-specific coverage differences.

### M4 — Supply from GTFS-RT (conditional; collection should start now)
- **No archive exists yet.** The live server keeps only in-memory history and replaces vehicle ids
  with per-run salted hashes ([feed.py](./src/api/feed.py)), so nothing can be joined across
  restarts or to tickets.
- **Archiver:** a separate best-effort script, isolated from the live server. Store snapshots of
  `(vehicle_key, route, ts, dist_m)` every ~1–2 min to gitignored Parquet. `vehicle_key` is a
  **stable keyed hash** with a persistent secret in `.env`; apply the same hash to ticket
  `vehicle_number` when joining. Measure storage on day 1.
- **Departures, not vehicle counts:** distinct vehicles seen in an hour isn't trips departing in
  it, because long trips span hours and one bus runs several trips. Infer departures from
  **terminal crossings** along `dist_m`, deduplicated. Treat gaps in the feed as unknown, not as
  "not operated", and keep GTFS as the fallback where observation is incomplete.
- **Use:** operated departures for `N̂` (GTFS may overstate service on the 90 zero-ticket routes).
- **Ticket join (only if a November e-ticketing drop arrives):** `vehicle_number` matches GTFS-RT
  ids for **90%** of ticketed vehicles. A November archive plus November tickets would allow
  ticket-linked trips and a **headway effect** (a bus after a long gap is fuller), which unlocks a
  live crowding **nowcast**. November supply isn't paired with October demand.

### Uncertainty (two kinds, kept separate)
- **Confidence in the mean:** day-block bootstrap (resample whole days within each day type and
  refit, B ≈ 20, offline). Says how well we know the *average* crowding of a route-hour.
- **Predictive interval** (what a rider sees on a given day): add **day-to-day variation**, i.e.
  the empirical dispersion of daily cell totals (a negative-binomial / quasi-Poisson fit per volume
  stratum; §1b measured φ ≈ 2.5 at route-hour level), to the mean uncertainty. Output
  `occ_p10 / occ_p50 / occ_p90` from this, and derive `p_high = P(occ ≥ 0.8)` from it, labelled as
  model-based.
- **Measured 2026-11-23 (October tickets):**
  - Multi-passenger tickets explain little of φ ≈ 2.5: passengers per ticket average 1.08
    (E[n²]/E[n] = 1.16).
  - After removing mobile-ticket sampling noise (`(Var − 1.16·μ)/μ²` over daily route-hour counts),
    the **real day-to-day CV** of a route-hour's riders is 21–29% on weekdays (busiest → quietest
    stratum), 12–27% on Saturdays and 16–28% on Sundays/holidays.
  - So an 80% range is ≈ ×0.75 to ×1.35 of the typical value; a Medium bus at 65% "could be High".
  - The rider-facing range excludes sampling noise. G3 checks the interval for **sampled** daily
    counts (sampling noise added back), the quantity that can be observed.
- **Assumption ranges, reported separately rather than mixed into p10/p90:** coverage (e.g. 3–6%),
  capacity, and GTFS-vs-operated supply.
- Calibrate the predictive interval on the **validation** window, then check coverage on the test
  week (target 70–90% for the 80% interval).

## 4. Evaluation protocol (decided before training)

**Splits (validation and test are kept apart)**
- **Tune and calibrate:** rolling-origin inside 1–24 Oct. Example: train 1–17 → validate 18–24.
  Model choice, hyperparameters and interval calibration use only this.
- **Final test, run once:** train on 1–24 Oct, test on **25–31 Oct** (5 weekdays, 1 Saturday,
  1 Sunday). Report it as the forecasting result.
- **Robustness (interpolation, not forecasting):** leave-one-week-out.
- **Generalisation:** `GroupKFold` by route number.

**Leakage rules**
- Split **raw ticket records first**. Then regenerate **every** target-derived artefact inside the
  training fold: target encodings, leave-route-out stop demand, AC shares, alighting priors,
  baselines, and the confidence rules.
- Existing outputs (`crowding_*.csv`) cover the whole month, including the test week. Never use
  them as features.
- In route-group CV, held-out route groups are excluded from pooled stop demand, not just the
  route itself.
- A unit test asserts that no test-window ticket reaches any training artefact.

**Baselines** (all on identical support and exposure)

| ID | Model |
|---|---|
| B0 | Today's model: monthly route-hour average, global coverage |
| B1 | B0 split by day type (with a small positive floor so Poisson deviance stays finite) |
| B2 | Hierarchical Poisson–Gamma (empirical Bayes) smoothing, as specified in §1b; the **serious competitor**, and the winner in §1b |
| M  | M1 + M2 (+ M3/M4 when available) |

**Metrics**
- *Demand (M1), on all cells:* Poisson deviance D² and WAPE on held-out boardings; same for
  alightings implied by M2. Stratify by training volume.
- *Ride length (M2):* held-out log-loss of the alighting position.
- *Load:* WAPE and Spearman of route-hour load, **stratified by training volume**, plus the share of
  cells that are evaluable.
  - In the 25–31 Oct test week only **~22–26%** of route-hours reach ≥ 30 pax (4,522 counting
    forward-consistent tickets, 5,373 counting all, of 20,739), before splitting by day type. That
    filter excludes exactly the sparse cases ML should help with.
  - Test-week "load" is itself reconstructed from tickets, so call it a **proxy**, not observed
    occupancy.
  - Report mean segment load alongside route-hour peak, because a max over noisy segments is
    biased upward.
- *Intervals:* empirical coverage of the 80% predictive interval.

**Acceptance gates** (pre-registered; ship the simplest model that passes)
- **G1:** M beats **B2** on held-out Poisson deviance (all cells) by **≥ 5%**, and on every volume
  stratum not worse than B2. Otherwise ship **B2**, which still beats B0, and say so.
- **G2:** route-hour Spearman (volume-stratified) ≥ B2's.
- **G3:** 80% predictive interval coverage within 70–90% on the test week.
- **Diagnostics (reported, not hard gates)** for the brief's "matches known peak and off-peak
  patterns": bimodal peaks for each day type, holidays Sunday-like, terminus load ≈ 0, and known
  busy corridors (717A, 511A, 729, 623) near the top. Compare against the empirical October
  patterns, not fixed ratios.

## 5. Serving and journey-planner integration

**Implemented (2026-11-23), the day-type slice of this contract:**
- `src/model/crowding.py` multiplies each `(route, hour)` monthly load profile by a factor per day
  type, so loads stay ≥ 0 and return to 0 at the terminus. The factor comes from **B2**
  (`b2_daytype_factors` in [demand.py](./src/ml/demand.py)): B2's boardings per day on that day type
  over B0's, summed over the route's stops, fitted on all 31 days with the tuned strengths.
  `--daytype-model network` uses the network factor `rate(hour, d) / rate(hour, all days)` instead,
  as a fallback.
- Validation week (18–24 Oct, route-hour deviance): B0 2.315, network factor 1.817 (−22%), B2
  1.467 (−37%). On the busiest route-hours (≥ 100 training pax): 6.93 / 3.61 / 3.40.
- Outputs `data/eticketing/crowding_{segments,route_hour,stop_hour}_daytype.csv` +
  `crowding_model.json`. Stop busyness uses the network factor, because it covers all routes at a
  stop. [network.py](./src/api/network.py) keys crowding by `(route, day type, hour)` and falls
  back to the all-days files if the day-type files are missing.
- Day type = the Delhi date the bus departs (a bus after midnight gets the next day's).
  `/api/plan`, `/api/stops/{id}` and `/api/routes` take `date=YYYY-MM-DD` (default today);
  `/api/live` uses each GPS fix's date. Responses gain a `daytype` field.
- Still to do from this section: intervals (`occ_p10/p90`), M2 ride length, `perceived_min`,
  ranking guard, `model_version` checks.

**Batch inference, not live inference.** `src/ml/predict.py` writes
`data/eticketing/crowding_*_ml.parquet` (gitignored). scikit-learn never runs in the request path.

**Consumer contract.** Every table [network.py](./src/api/network.py) loads gains a `daytype` key,
and all of them come from the **same model run** so nothing goes stale:

| Artefact | Key | Columns |
|---|---|---|
| segments | `(route, daytype, hour, pos)` | `stop_id, per_vehicle_load, occupancy (= p50), occ_p10, occ_p90, p_high, level, confidence, n_obs` |
| route-hour summary | `(route, daytype, hour)` | as today, plus the interval columns |
| stop busyness | `(stop_id, daytype, hour)` | as today |
| `model_version` | — | in every table, checked at load |

Changes in the server and app:
- `occ`, `rh_by_route`, `confidence`, `busyness` and the `route_detail` cache become day-type
  aware. The `lru_cache` key includes the day type.
- `crowding_at` (live map) uses the service-day rule from Section 3.
- `/api/plan` gets an optional `date=` for planning ahead. The app doesn't need it today (it always
  plans from "now" and has no date picker). Each option gains `occ_lo`, `occ_hi` and
  `perceived_min`.
- **Ranking ("Balanced"):** today the app adds a flat penalty per level (`CROWD_PENALTY_MIN` in
  [planner.ts](./mobile-implementation/src/logic/planner.ts)), so a 5-min and a 50-min crowded ride
  cost the same. Replace it with **perceived time**: `wait + Σ_segments ride_min(seg) ×
  m(occ_seg)`.
  - `m` is a documented crowding multiplier curve: 1.0 when uncrowded, rising to about 2× for
    crowded standing, in the range reported by Wardman & Whelan (2011). Sensitivity-tested.
  - The **server** computes it, because it has per-segment times from the timetable. `planner.ts`
    **reads `perceived_min`** instead of computing its own score, with the ranking guard from M3.
- **"Leave later" suggestion:** already in the app (`findLeaveLater`, ≤ 45 min later within the
  2 h plan window). ML only improves the numbers it compares, plus the ranking guard.
- **App:** show the range ("Medium, could be High") and keep the existing confidence note.

### Impact on the mobile app (`mobile-implementation/`, checked 2026-11-23)

The app is a thin client: every crowding number comes from the server (`/api/plan`,
`/api/stops/{id}`, `/api/routes`, `/api/live`; see [api.ts](./mobile-implementation/src/live/api.ts)),
and it sends only `t` = seconds since midnight IST, never a date. So the ML stays entirely on the
server, and **as long as response fields keep their names and meaning, the app needs no code change
to pick up better estimates.** The table lists what does touch the app:

| Plan item | App change | Where |
|---|---|---|
| Day types (P1-2) — **done 2026-11-23** | **None required.** The server takes the day type from its own IST date. Update the copy: "October 2026 e-ticketing average" becomes "October weekday / Saturday / Sunday average". Optional: route crowding is cached for the whole session, so crossing midnight into another day type keeps old values until reload. Add a `daytype` field to the route response and refetch when it changes. | [details.tsx](./mobile-implementation/src/components/details.tsx) (stop note, About), `routes` cache in [App.tsx](./mobile-implementation/App.tsx) |
| Volume-aware confidence (P1-1) — **done 2026-11-23** | **Text only.** `confidenceText()` says low confidence means "few scheduled buses", and high means "≥ 2 scheduled buses". Reword both to cover ticket volume, and add the threshold to `meta.json`. Expect far more "low confidence" labels (route-hours < 30 pax/month: 9,186 of 20,739). Optional: dim low-confidence lines on the map, which currently greys only `none`. | [crowding.ts](./mobile-implementation/src/logic/crowding.ts), [export_mobile_data.py](./src/export_mobile_data.py), `Meta` in [types.ts](./mobile-implementation/src/types.ts), [main.ts](./mobile-implementation/map/main.ts) |
| Ranking guard (M3) | **Code.** `least_crowded` sorts by level alone, and `findLeaveLater` can recommend a low-confidence "Low" bus. Rank low confidence after high, or use `occ_hi`. | [planner.ts](./mobile-implementation/src/logic/planner.ts) + tests |
| `perceived_min` ranking | **Code.** `toOptions()` scores `totalMin + CROWD_PENALTY_MIN[level]`. Use the server's `perceived_min` when present and keep the old score as fallback. | [planner.ts](./mobile-implementation/src/logic/planner.ts), `PlanOptionRaw`, [planner.test.ts](./mobile-implementation/src/__tests__/planner.test.ts) |
| Ranges (`occ_lo`/`occ_hi`) | **Code (additive).** New optional fields; `describeLoad` shows "~25–40 on board". `/api/live` rows are **positional** (`R` in [live.ts](./mobile-implementation/src/logic/live.ts)), so new columns go at the **end** only. | [types.ts](./mobile-implementation/src/types.ts), [crowding.ts](./mobile-implementation/src/logic/crowding.ts), [JourneyPanel.tsx](./mobile-implementation/src/components/JourneyPanel.tsx) |
| Per-route coverage (M3) | **Text.** The app prints one global "~4.5% mobile-ticket share" from `meta.assumptions.coverage`. Describe the per-route calibration instead. | [details.tsx](./mobile-implementation/src/components/details.tsx), `Meta` |
| Trip-hour cohort B (if adopted) | **None, if the server translates.** The app reads `crowding[hour]` as "buses on this stretch in this hour" (map lines, live buses, stop sheet). The server should map cohort-B results back to that meaning when building responses. Then only the note "alightings count in the hour the ticket was bought" changes. | server `route_detail` / `crowding_at`; [details.tsx](./mobile-implementation/src/components/details.tsx) note |
| GTFS-RT archiver / nowcast (M4) | **None.** A nowcast only changes the `occ` values in `/api/live`. | — |

## 6. Code layout

```
src/ml/
  daytypes.py   # day types + Delhi holiday list (done; shared with the API)
  demand.py     # done: cells, B0, B2, b2_daytype_factors (shared by the experiment and crowding.py)
  compare_models.py  # done: B0/B1/B2/GLM/GBM demand comparison -> reports/ml_model_comparison.json
  dataset.py    # raw split first; cell table (route,pos,cohort hour,daytype) + exposure; cohort A/B
  features.py   # fold-local route/stop/time/supply features, leave-route-out stop demand, zones
  baselines.py  # B0, B1, B2
  train.py      # M1 = B2 (+ optional GBM re-check) + M2 (ride length); models/ gitignored
  evaluate.py   # splits, metrics, gates -> reports/ml_metrics.json, reports/ml_report.html
  predict.py    # batch inference + intervals -> crowding_*_ml.parquet
src/archive_gtfsrt.py  # M4 standalone best-effort archiver (stable keyed vehicle hash)
tests/ml/              # pytest: calendar + service-day rule, conservation (load ≥ 0, ≈ 0 at
                       #  terminus), no test-window leakage, output schema / model_version
```

- `scikit-learn` is now in [requirements.txt](./requirements.txt) (add `pyarrow` with the Parquet
  outputs).
- Credit **scikit-learn** in the README and technical note (required by the rules).
- `models/`, archives and all derived tables stay gitignored; only metrics JSON and HTML reports
  get committed.

## 7. Roadmap

### Phase 1 slice (by 25 Nov): **only after** the technical note, demo video and README are safe

In priority order; stop wherever time runs out.

| Step | Change | Payoff |
|---|---|---|
| P1-1 ✅ | **Volume-aware `confidence`** in `crowding.py` (low when the route-hour has few tickets), plus a test; reword the app's `confidenceText()` to match | Small change that stops sparse routes showing as confidently "Low" (finding #4) |
| P1-2 ✅ (with B2) | One **tested day-type vertical slice**: scale each route-hour's existing monthly load profile by the **network day-type factor** `rate(hour, day type) / rate(hour, all days)`. That's what B2 learned (§1b finding 4), and it keeps load conservation. Do **not** split counts by day type (B1 is worse than today). Add the service-day rule, and have `plan()` use it. | Fixes the −16% weekday / 2× Sunday distortion (finding #3) on the planner path |
| P1-3 | **Archiver** as an isolated, best-effort script | Starts M4 data collection; zero risk to the demo |

**Done 2026-11-23:** P1-1 (5,498 route-hours turned low-confidence for having < 30 tickets a month;
8,610 of 20,739 stay high), and P1-2 with **B2 per-route factors** in place of the network factor,
which stays as `--daytype-model network`. B2 now lives in `src/ml/demand.py` (part of M0), and the
moved code reproduces §1b's B2 scores exactly. Tests: `python -m pytest` (`tests/`).
The full evaluator happens in Phase 2. Section 1 and §1b go in the
technical note regardless: the comparison is already real validation evidence.

### Phase 2 (25 Nov → 10 Dec)

| Dates | Milestone | Exit criterion |
|---|---|---|
| 25–27 Nov | **M0**: move `daytypes.py` + B2 from the experiment into a shared module, leakage-safe dataset, cohort A vs B validation, tests | B2 reproducible from one command; cohort decided |
| 27–30 Nov | **M1 = B2** wired into `crowding.py` (boardings by day type); optional GBM re-check only if new data arrived. *Day-type factor already done 2026-11-23 (§5).* | B2's §1b test numbers reproduced; diagnostics pass |
| 27–29 Nov | **Crowding ranges ("could be High")**: real day-to-day CV by day type and volume (sampling noise removed) + bootstrap uncertainty of the B2 factors → one `log_sd` per route-hour; `occ_lo/occ_hi/p_high` in the API; "Medium (could be High) · ~25–55 on board" in planner, stop and bus sheets; ranking guard on `occ_hi` | **G3**: 80% interval covers 70–90% of test-week days (overall and per day type); app tests pass |
| 30 Nov–3 Dec | **M2** ride length, load assembly (ranges carry over to the new loads) | Conservation and leakage tests green |
| 3–6 Dec | **Serving + planner**: consumer contract, `perceived_min`, ML report | App end-to-end on M outputs; existing app tests pass |
| 4–7 Dec | **M3 / M4 (conditional)**: ETM calibration if received (after the population contract); operated departures from the archive | Held-out-route check (M3); departures vs GTFS cross-check (M4) |
| 7–10 Dec | Freeze: model card, technical note v2, demo video, rehearsal | Submission |

## 8. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Coverage can't be identified without ETM (finding #4) | High | Volume-aware confidence, ranking guard, compatible-line prior, honest relative ranking; M3 when ETM lands |
| Inconsistent time cohort between tickets, supply and lookups | High | One cohort definition (Section 2) used by every component; cohort B only if validated |
| Leakage (encodings, shared stops, whole-month outputs) | High | Raw split first, fold-local artefacts, route-group exclusion, leakage unit test |
| Optimistic scores from tuning on the test week | Med | Separate validation window; test week used once |
| Over-confident intervals | Med | Separate mean vs predictive intervals; assumption ranges reported separately; coverage gate |
| One month of data, only 2 holidays | Med | Explicit day types (holiday → Sunday); no extrapolated trend; stated limitation |
| ML doesn't beat B2 | — | **Happened** (§1b): GBM +3% at stop level, −1.2% at route-hour level. B2 ships, and the technical note says so |
| Serving changes larger than expected | Med | Single-run artefacts with `model_version`; consumer contract in Section 5 |
| Deadline pressure (Phase 1 in 2 days) | High | Phase 1 slice is optional, prioritised and gated |

## 9. Open questions (answer when possible)

1. **ETM data:** still pending? Does it include mobile sales? Are its units tickets or passengers?
   It's the single biggest accuracy lever (M3).
2. **November e-ticketing drop:** expected? It decides whether M4 can become a live nowcast.
3. **Bus capacity:** is 60 (35 seated + 25 standing) right for both standard and electric buses?
   Is per-fleet capacity available?
4. **Fare-free riders:** riders who don't buy a ticket (e.g. concession passes) aren't in ticket
   sales at all. Confirm with the organizer whether ETM counts them.

## References

- Spiess, H. & Florian, M. (1989). *Optimal strategies: A new assignment model for transit
  networks.* Transportation Research Part B, 23(2). (Frequency-share / common-lines assumption.)
- Wardman, M. & Whelan, G. (2011). *Twenty years of rail crowding valuation studies: evidence and
  lessons from British experience.* Transport Reviews, 31(3). (Crowding time multipliers.)
- Clayton, D. & Kaldor, J. (1987). *Empirical Bayes estimates of age-standardized relative risks
  for use in disease mapping.* Biometrics, 43(3). (Poisson–Gamma empirical Bayes smoothing of sparse
  counts, the idea behind B2.)
- scikit-learn: `HistGradientBoostingRegressor` (Poisson loss), `PoissonRegressor`.
