"""Resolve e-ticketing stop names to GTFS stops (stop_id + coordinates).

The e-ticketing feed records free-text stop names (start_stop_name / end_stop_name)
that only exact-match GTFS stop_name ~48% of the time (spacing, punctuation,
abbreviations: "Bdr"->"Border", "Sec"->"Sector", "(T)" terminal markers, ...).

To place boardings/alightings onto a route's stop sequence for the crowding model,
each (route, stop_name) must map to a GTFS stop. Strategy:

  1. ROUTE-SCOPED match — match the name only against the stops that the GTFS route
     actually serves (route string matches GTFS route_short_name for 100% of tickets).
     This is both accurate (disambiguates same-named stops) and fast (small candidate
     sets), and yields the GTFS stop_id + lat/lon directly.
  2. Fall back to a GLOBAL match (any GTFS stop) when the route has no candidate / no
     good route-scoped match.

Matching = normalize + expand abbreviations on BOTH sides, then token-set Jaccard
(tie-broken by difflib ratio). No third-party fuzzy dependency.

Run:  python src/resolve_stops.py
Out:  data/eticketing/stop_resolution.csv        (gitignored mapping, per route+name)
      reports/stop_resolution_metrics.json       (coverage summary)
Data source: Delhi Transport Stack (DoT, GNCTD) — License v1.0.
"""
from __future__ import annotations
import json, re, time
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
GTFS = ROOT / "data" / "delhi_buses_static_gtfs"
ETK = ROOT / "data" / "eticketing" / "October-Delhi.csv"
OUT = ROOT / "data" / "eticketing" / "stop_resolution.csv"
REP = ROOT / "reports"; REP.mkdir(exist_ok=True)

ROUTE_JACCARD_MIN = 0.50   # accept a route-scoped fuzzy match at/above this
GLOBAL_JACCARD_MIN = 0.67  # stricter for global (no route context to disambiguate)

ABBR = {
    "bdr": "border", "sec": "sector", "sect": "sector", "vill": "village",
    "gaon": "village", "vlg": "village", "mkt": "market", "rd": "road",
    "stn": "station", "chk": "chowk", "extn": "extension", "ext": "extension",
    "hosp": "hospital", "sch": "school", "clny": "colony", "term": "terminal",
    "termnl": "terminal", "nr": "near", "opp": "opposite", "blk": "block",
    "pkt": "pocket", "grd": "ground", "grnd": "ground", "no": "number",
    "metrostn": "metro station", "xing": "crossing", "crsng": "crossing",
    "flyovr": "flyover", "vihaar": "vihar", "enclv": "enclave", "indl": "industrial",
}

def norm_tokens(s: str):
    """Return (normalized string, token set, spaceless string) with abbreviations expanded."""
    s = s.lower().strip()
    s = re.sub(r"\s*\(\s*t\s*\)$", " terminal", s)   # trailing (T) = terminal
    s = re.sub(r"[()]", " ", s)
    s = re.sub(r"\s*/\s*", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    toks = [ABBR.get(t, t) for t in s.split()]
    toks = " ".join(toks).split()                    # re-split multi-word expansions
    nstr = " ".join(toks)
    return nstr, frozenset(toks), nstr.replace(" ", "")


# Generic structural tokens — shared ONLY on these must not establish a match
# (e.g. two different 'X Metro Station' / 'Y GT Road' stops share metro/station/gt/road).
GENERIC = {
    # structural / positional
    "metro", "station", "road", "gt", "crossing", "xing", "flyover", "bridge",
    "terminal", "depot", "stand", "gate", "marg", "chowk", "border", "block",
    "pocket", "sector", "number", "near", "opposite", "main", "bus", "stop",
    "colony", "extension", "village", "mandi", "camp", "more", "club",
    # facility / feature types — must not carry a match alone ('X Hospital' != 'Y Hospital')
    "hospital", "school", "college", "university", "vidyalaya", "temple", "mandir",
    "masjid", "church", "gurudwara", "park", "stadium", "office", "market",
    "bazar", "bazaar", "chowki", "thana", "complex",
    # housing-scheme types — same ('Jhil Mil DDA Flats' != 'Tahir Pur DDA Flats')
    "flats", "flat", "dda", "lig", "mig", "hig", "ews", "jj", "esi", "industrial",
}

def distinctive(toks) -> frozenset:
    """Place-identifying tokens: >=3 chars and not a generic structural word."""
    return frozenset(t for t in toks if len(t) >= 3 and t not in GENERIC)


def pair_score(nnorm, ntoks, ncol, gnorm, gtoks, gcol) -> float:
    """Score on DISTINCTIVE tokens only (locality words, not 'metro'/'station'/'road'),
    so a match must agree on the place name — two different 'X Metro Station' or
    'Y Stand Najafgarh' stops no longer match on their shared generic words. Containment
    handles GTFS supersets ('Mahipal Pur' in 'Mahipal Pur Extension'); a spaceless ratio
    rescues split/joined spellings ('Azad Pur' vs 'Azadpur', 'Chhattar Pur' vs 'Chhatarpur')."""
    qd, cd = distinctive(ntoks), distinctive(gtoks)
    di = len(qd & cd)
    if di == 0:
        sr = SequenceMatcher(None, ncol, gcol).ratio()
        return sr if sr >= 0.92 else 0.0       # only near-identical spaceless can match
    dj = di / len(qd | cd)
    dcont = di / min(len(qd), len(cd))
    trust = di >= 2 or di == min(len(qd), len(cd))   # shorter distinctive set fully covered
    base = max(dj, dcont if trust else 0.0)
    sr = SequenceMatcher(None, ncol, gcol).ratio()
    return max(base, sr if sr >= 0.90 else 0.0)


def best_match(nnorm, ntoks, ncol, candidates):
    """candidates: list of (stop_id, gnorm, gtoks, gcol). Return (stop_id, score)."""
    best_id, best = None, 0.0
    for sid, gnorm, gtoks, gcol in candidates:
        s = pair_score(nnorm, ntoks, ncol, gnorm, gtoks, gcol)
        if s > best:
            best_id, best = sid, s
    return best_id, best


def build_gtfs_index():
    stops = pd.read_csv(GTFS / "stops.txt", dtype=str)
    stops["stop_lat"] = pd.to_numeric(stops.stop_lat)
    stops["stop_lon"] = pd.to_numeric(stops.stop_lon)
    meta = {r.stop_id: (r.stop_name, r.stop_lat, r.stop_lon) for r in stops.itertuples()}
    norms = {sid: norm_tokens(nm) for sid, (nm, _, _) in meta.items()}

    # route_short_name -> set of stop_ids (via trips -> stop_times)
    routes = pd.read_csv(GTFS / "routes.txt", dtype=str)
    r2short = dict(zip(routes.route_id, routes.route_short_name))
    trips = pd.read_csv(GTFS / "trips.txt", dtype=str, usecols=["route_id", "trip_id"])
    t2short = {t: r2short.get(r) for t, r in zip(trips.trip_id, trips.route_id)}
    st = pd.read_csv(GTFS / "stop_times.txt", dtype=str, usecols=["trip_id", "stop_id"])
    st["short"] = st.trip_id.map(t2short)
    route_stops = (st.dropna(subset=["short"])
                     .groupby("short")["stop_id"].agg(lambda s: list(dict.fromkeys(s))))
    route_cands = {}
    for short, sids in route_stops.items():
        route_cands[short] = [(sid, *norms[sid]) for sid in sids if sid in norms]
    # global candidates + inverted index (token -> candidate tuples) for fast fuzzy fallback
    global_cands = [(sid, *norms[sid]) for sid in norms]
    global_index = defaultdict(list)
    for cand in global_cands:
        for tok in cand[2]:                 # cand = (sid, gnorm, gtoks, gcol)
            global_index[tok].append(cand)
    return meta, route_cands, global_cands, global_index


def main():
    t0 = time.time()
    print("Building GTFS index (route -> stops)...")
    meta, route_cands, global_cands, global_index = build_gtfs_index()
    print(f"  routes with stops: {len(route_cands):,}  | GTFS stops: {len(meta):,}")

    print("Loading e-ticketing (route, stop) pairs + weights...")
    df = pd.read_csv(ETK, usecols=["route", "start_stop_name", "end_stop_name"], dtype="string")
    a = df[["route", "start_stop_name"]].rename(columns={"start_stop_name": "stop"})
    b = df[["route", "end_stop_name"]].rename(columns={"end_stop_name": "stop"})
    allp = pd.concat([a, b], ignore_index=True).dropna()
    weights = allp.value_counts(["route", "stop"])          # occurrences per (route, stop)
    pairs = weights.index.tolist()
    total_occ = int(weights.sum())
    print(f"  distinct (route,stop) pairs: {len(pairs):,}  | total occurrences: {total_occ:,}")

    # global exact-normalized index: norm string -> stop_id (first)
    global_by_norm = {}
    for sid, gnorm, _, _ in global_cands:
        global_by_norm.setdefault(gnorm, sid)

    rows, method_count, occ_by_method = [], defaultdict(int), defaultdict(int)
    for (route, stop) in pairs:
        w = int(weights[(route, stop)])
        nnorm, ntoks, ncol = norm_tokens(stop)
        cands = route_cands.get(route, [])
        sid = method = None; score = 0.0

        # 1. route-scoped exact-normalized
        exact = next((c[0] for c in cands if c[1] == nnorm), None)
        if exact is not None:
            sid, method, score = exact, "exact_route", 1.0
        elif cands:
            # 2. route-scoped fuzzy (small candidate set -> full blended scorer)
            cid, cs = best_match(nnorm, ntoks, ncol, cands)
            if cid is not None and cs >= ROUTE_JACCARD_MIN:
                sid, method, score = cid, "fuzzy_route", round(cs, 3)
        if sid is None:
            # 3. global exact-normalized
            if nnorm in global_by_norm:
                sid, method, score = global_by_norm[nnorm], "exact_global", 1.0
            else:
                # 4. global fuzzy — only score candidates sharing >=1 token (inverted index)
                seen, sub = set(), []
                for tok in ntoks:
                    for cand in global_index.get(tok, ()):
                        if cand[0] not in seen:
                            seen.add(cand[0]); sub.append(cand)
                cid, cs = best_match(nnorm, ntoks, ncol, sub)
                if cid is not None and cs >= GLOBAL_JACCARD_MIN:
                    sid, method, score = cid, "fuzzy_global", round(cs, 3)
                else:
                    method = "unresolved"

        method_count[method] += 1
        occ_by_method[method] += w
        gname, glat, glon = meta.get(sid, (None, None, None))
        rows.append([route, stop, w, sid, gname, glat, glon, method, score])

    res = pd.DataFrame(rows, columns=["route", "stop_name", "occurrences", "stop_id",
                                      "gtfs_stop_name", "lat", "lon", "method", "score"])
    res.sort_values("occurrences", ascending=False).to_csv(OUT, index=False)

    resolved = res.method != "unresolved"
    dpct = 100 * resolved.sum() / len(res)
    wpct = 100 * res.loc[resolved, "occurrences"].sum() / total_occ
    print("\n=== COVERAGE ===")
    print(f"  distinct pairs resolved : {resolved.sum():,}/{len(res):,} ({dpct:.1f}%)")
    print(f"  ticket-weighted resolved: {wpct:.1f}%")
    print("  by method (distinct | ticket-weighted):")
    for m in ["exact_route", "fuzzy_route", "exact_global", "fuzzy_global", "unresolved"]:
        print(f"    {m:<14} {method_count[m]:>7,}  |  {100*occ_by_method[m]/total_occ:>5.1f}%")

    print("\n  sample resolved (fuzzy_route):")
    for r in res[res.method == "fuzzy_route"].sort_values("occurrences", ascending=False).head(6).itertuples():
        print(f"    '{r.stop_name}' @ {r.route}  ->  '{r.gtfs_stop_name}'  (j={r.score})")
    print("  sample UNRESOLVED (top by volume):")
    for r in res[res.method == "unresolved"].sort_values("occurrences", ascending=False).head(6).itertuples():
        print(f"    '{r.stop_name}' @ {r.route}  ({r.occurrences:,} occ)")

    M = {
        "distinct_pairs": len(res), "total_occurrences": total_occ,
        "distinct_resolved_pct": round(dpct, 1), "ticket_weighted_resolved_pct": round(wpct, 1),
        "method_distinct": {m: int(method_count[m]) for m in method_count},
        "method_occ_pct": {m: round(100*occ_by_method[m]/total_occ, 1) for m in occ_by_method},
        "runtime_sec": round(time.time() - t0, 1),
    }
    (REP / "stop_resolution_metrics.json").write_text(json.dumps(M, indent=2, default=str))
    print(f"\nWrote {OUT.relative_to(ROOT)} and reports/stop_resolution_metrics.json "
          f"({M['runtime_sec']}s)")


if __name__ == "__main__":
    main()
