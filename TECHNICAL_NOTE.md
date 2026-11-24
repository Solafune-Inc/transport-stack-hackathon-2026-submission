# Delhi Bus Crowding: technical note

**Transport Stack Hackathon 2026 · Phase 1 · Problem 2, crowdedness-aware journey planner**
Team SOLAFUNE · 24 November 2026 ·
Code: [github.com/Solafune-Inc/transport-stack-hackathon-2026-submission](https://github.com/Solafune-Inc/transport-stack-hackathon-2026-submission)

This note covers our proposal, how we turn e-tickets into crowding estimates, how the planner uses
them, the checks we ran, and where the estimates are least reliable. How to run everything is in
[README.md](README.md).

## 1. Proposal

Delhi's journey planners rank trips by time and number of changes. Riders also care whether they
will get a seat, have room to stand, or be left at the stop. We built:

- **A crowding model** for every bus route (UP and DOWN separately), every stretch between stops,
  every hour, and three day types: weekday, Saturday, Sunday or public holiday. It is built from
  October 2026's 2.56 million mobile e-tickets and the static GTFS.
- **A journey planner** that shows each option's expected crowding next to its departure and travel
  time, for direct trips and trips with one change. Riders can sort by fastest, least crowded, or a
  balance of both.
- **A map app** (Android, iOS and web from one codebase). Every stop, route stretch and live bus is
  coloured by expected crowding, and each route has an hour-by-hour crowding chart.
- **Outputs for operators:** route-hours over capacity, ranked by riders above capacity per day
  (crowding report §4; full list in `data/eticketing/crowding_operator.csv.gz`).

If shortlisted, in Phase 2 we would add, in this order:
1. Crowding ranges ("standing room, could be crowded"), from the measured day-to-day variation (§5).
2. A ranking rule that stops a low-confidence option from winning on thin data.
3. A per-route correction for the mobile-ticket share, from ETM data if it is shared.
4. Capacity by bus type.
5. Bus + metro trips, if metro data arrives.

## 2. Data

| Source | What we use | Notes |
|---|---|---|
| Mobile e-ticketing, 1–31 Oct 2026 | `route` (it includes the direction, e.g. 8UP), `start_stop_name`, `end_stop_name`, `created_at`, `passenger_count` | 2,559,899 tickets. Fare, `vehicle_number`, `ticket_type_id` and `is_ac` are not used yet. No ETM data was provided. |
| Delhi Buses GTFS Static | stop order of each route, stop locations, timetable | 2,554 routes, 6,812 stops served, 65,322 scheduled trips a day. The timetable is the same every day. |
| Delhi Buses GTFS-RT | live bus positions on the map | Display only; the model doesn't use it. |

## 3. From tickets to crowding

1. **Match ticket stops to GTFS stops.** Each ticket's stop names are matched only against the stops
   of that ticket's route, so a same-named stop elsewhere can't be picked. This resolves 97.9% of
   tickets (`src/resolve_stops.py`, `reports/stop_resolution_report.html`).
2. **Keep usable tickets.** 89.1% of tickets (2.28 M) have both stops matched on their route. Of
   those, 98.7% get off after they board along the GTFS stop order. Only these are used, which also
   checks that the stop matching and the direction are right.
3. **Load along the route.** This is the brief's running count, done on a month of tickets per route
   and hour instead of per bus trip. For each route and hour, the month's boardings and alightings are
   placed on the stop sequence and summed in order:

   `load after stop i = boardings up to stop i − alightings up to stop i`

   Each ticket gives both stops, so alightings come from the data, not from a model.
4. **Per bus.** `per-bus load = load ÷ 0.045 (the mobile share of tickets) ÷ buses scheduled on that
   route in that hour over the month`.
5. **Day types.** Daily totals fall into three groups:
   - weekdays, about 98–110 k passengers a day;
   - Saturdays, 73–91 k;
   - Sundays, 40–57 k. The two October public holidays rode like Sundays.

   Each route-hour's monthly profile is then scaled for each day type by **B2**, a hierarchical
   Poisson–Gamma model of boardings per route, stop, hour and day type. A route-hour with few tickets
   borrows strength from its route and from the whole network. Scaling the whole profile keeps its
   shape along the route, and riders on still equal riders off.
6. **Level.** `occupancy = per-bus load ÷ 60` (about 35 seated and 25 standing):

   | Occupancy | Riders on board | Shown as |
   |---|---|---|
   | below 0.5 | under 30 | Seats available (green) |
   | 0.5 to 0.8 | 30–47 | Standing room (yellow) |
   | 0.8 to 1.0 | 48–59 | Crowded (orange) |
   | 1.0 or more | 60 or more | Packed (red) |

7. **Confidence.** A route-hour is *low confidence* if it has fewer than 2 scheduled buses a day in
   that hour, or fewer than 30 ticketed passengers in the month. 8,610 of the 20,739 route-hours are
   high confidence, and they carry 85.9% of ticketed passengers. The app marks low-confidence
   estimates wherever it shows them, including in the planner.

Code: `src/model/crowding.py`, `src/ml/demand.py`, `src/ml/daytypes.py`. The output tables and their
columns are described in [data/MODEL_CARD.md](data/MODEL_CARD.md).

## 4. The planner

- **Input:** any two stops (nearby stops with the same name are grouped), a departure time and a date.
  The date sets the day type; public holidays count as Sundays.
- **Options** (`/api/plan`; `src/api/network.py`, `src/api/journeys.py`):
  - direct buses from the GTFS timetable leaving in the next two hours;
  - trips with one change, at the same stop or after a short walk (up to 250 m). A change needs at
    least 2 minutes and at most a 30-minute wait.
  - A one-change option that another option beats on every count is dropped.
- **An option's crowding** is the worst expected level over the stretches the rider actually rides,
  in the hour the bus leaves their stop. With a change, it is the worse of the two rides. Each
  option shows its departure, ride time, changes, the level as a coloured badge, and "low confidence"
  where that applies.
- **Choosing:**
  - **Fastest** sorts by arrival time.
  - **Least crowded** sorts by level, then arrival.
  - **Balanced** sorts by the minutes until arrival plus a penalty: 0, 4, 10 or 18 minutes for seats
    available, standing room, crowded or packed, and 5 minutes per change.

  When the fastest option is crowded or packed, the app suggests the first calmer option that arrives
  at most 45 minutes later.
- **The brief's example** (Anand Vihar to Connaught Place at 6 pm on a weekday). We ran it from Anand
  Vihar ISBT Main Road to Super Bazar, Connaught Place, on Wednesday 25 November:
  - The fastest option is the direct 943UP, 18:06 to 18:43, with standing room (high confidence).
  - Seats are expected on 857UP with one change at LNJP Hospital, 18:00 to 18:45. That estimate is
    low confidence, and the app says so.

## 5. Checks against known patterns

All checks run on the tables the app serves. Details are in `reports/crowding_report.html` and
`reports/crowding_metrics.json`.

- **Morning and evening peaks.** On weekdays, the average peak occupancy of a route is 0.99 at 09:00
  and 0.72 at 18:00, against 0.26 at 14:00.
- **Weekday vs weekend.** At 09:00, Saturdays average 0.81 and Sundays/holidays 0.34, about a third
  of a weekday, and Sundays are much flatter through the day.
- **Busy corridors.** The most crowded high-confidence route-hours are peak hours in the commuting
  direction, for example 717A UP at 08:00 and 8 DOWN at 19:00 (report §3).
- **Shape along the route.** Load builds from the origin, peaks mid-route and falls toward the
  terminus (example: 623DOWN at 18:00, report §1).
- **Accounting.** Alightings ÷ boardings = 1.0, so every route's load returns to zero at the terminus.
- **Week to week.** We fitted on 1–24 October and tested once on the held-out week of 25–31 October.
  - Against the plain monthly average, B2 cut route-hour error by 27%: Poisson deviance fell from
    1.88 to 1.37, and WAPE from 0.39 to 0.29.
  - Over weekday route-hours with at least 10 riders, the predicted ranking correlates at 0.90 with
    the held-out week.
  - Gradient boosting did no better at route-hour level (deviance 1.39), so B2 serves the app.

  Source: `reports/ml_model_comparison.json`, `docs/ML_PLAN.md` §1b.
- **Day-to-day spread.** The ticket sample is small, so we removed its noise first. What remains is
  real day-to-day variation: riders on a weekday route-hour vary by 21–29%. An 80% range is about
  ×0.75 to ×1.35 of the shown value, so a bus shown as "standing room" can be crowded on some days.

## 6. Assumptions, and where the estimates are least reliable

Taking the brief's "things to think about" in turn:

1. **Running count per bus trip.** We don't count riders trip by trip.
   - **Why:** over the month there are only about 1.3 mobile tickets per scheduled bus trip, so a
     single trip's count is mostly 0, 1 or 2. Pooling a month per route and hour gives a stable
     profile of the *typical* bus in that hour.
   - **The cost:** we can't see one bus being fuller than usual, for example because the bus before
     it was late.
   - **The fix:** ticket `vehicle_number`s match GTFS-RT vehicle ids for 90% of ticketed buses.
     Tickets and bus positions from the same month would allow per-trip estimates.
2. **Riders missing from the ticket data.** One factor, 4.5%, scales every route and hour. It is the
   organizer's figure for mobile tickets as a share of ticket sales (4–5%).
   - Pass holders and other riders without a sold ticket are not covered.
   - The real mobile share surely differs by route and hour. If it is 3–4%, as the Problem 3 brief
     says, true loads are 1.1 to 1.5 times ours.
   - **This is the weakest point: absolute rider counts and the exact level boundaries.** A few routes
     come out impossibly high: on weekdays, 717A UP at 08:00 is over seven times capacity. That most
     likely means more mobile-ticket users there than average. We show these as packed and read them
     as "among the busiest", not as a count.
   - Which stretch, hour or route is busier is much more reliable than how many people are on board.
     ETM data would let us correct the share route by route.
3. **Planned vs actual stop.** We take the ticket's destination as where the rider got off, and count
   the alighting in the hour the ticket was bought. A long ride that crosses into the next hour is
   counted entirely in its boarding hour.
4. **Bus size.** Every bus is treated as holding 60. We have no data on which bus type runs each
   route, and `is_ac` isn't used yet. On routes run with 9 m buses, real crowding is worse than shown.
5. **Routes and hours with few tickets.** These are shown as low confidence: 58% of route-hours, but
   only 14% of riders. They are mostly route-hours with a single scheduled bus, or with few
   mobile-ticket users. B2 pulls them toward their route's and the network's pattern.
   - **Known gap:** a low-confidence option can still come first under *Least crowded*, as in the
     example in §4. The Phase 2 ranking rule fixes this.
6. **Simple display.** There are four levels, each with a word and a colour. The planner, the map,
   stops and buses all use them the same way.

Other limits:
- **Supply comes from the timetable.** The GTFS schedule is the same every day, so buses per hour
  don't change by day type. Where fewer buses run than scheduled, loads are underestimated.
- **One month of data.** October 2026 includes Gandhi Jayanti and Dussehra. Seasons, the monsoon and
  festival weeks such as Diwali are not in it.
- **Dropped tickets.** 11% of tickets are dropped: their stop was not matched, or it is out of order
  on the route. Routes with irregular stop names are therefore undercounted.

## 7. Reproducing it

- **Run the prototype:** clone the repository, add the GTFS, then run `docker compose up --build`
  (README.md, "Run it").
- **Run the tests:** `docker compose --profile test run --rm tests`.
- **Rebuild the model:**
  1. Put the October 2026 e-ticketing file in `data/eticketing/October-Delhi.csv`, and the GTFS in
     `data/delhi_buses_static_gtfs/`.
  2. Run `python src/resolve_stops.py && python src/model/crowding.py`.
- **Re-run the model comparison:** `python src/ml/compare_models.py` (about 50 minutes).

The data, libraries and AI tools we used are credited in [README.md](README.md#credits).
