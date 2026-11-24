"""Statistical models vs gradient boosting for bus boarding demand (ML_PLAN.md §3–4).

Question: does a learned model predict next week's boardings better than classical statistical
models, at the grain the crowding model needs?

Target: mobile-ticket boardings per day for each (route, stop position, hour, day type), the demand
input of src/model/crowding.py (hour = ticket purchase hour, as today). Cells: every (route, stop
position, hour) the GTFS timetable serves, plus any seen in the training window, x 3 day types.

Models
  B0   today's approach: average over all days (no day types)
  B1   average per day type
  B2   empirical Bayes (hierarchical Poisson-Gamma). Each cell is shrunk toward
       [route x hour x day-type volume] x [the route's stop share in that time band]. Those are
       shrunk toward route volume x the network's hourly profile, and route volume toward
       scheduled trips x network passengers per trip.
  GLM  penalised Poisson log-linear model (ridge, akin to Gaussian random effects): route x day
       type, route x hour, hour x day type, route-stop, route-stop x time band, stop x time band,
       log scheduled buses (route at the stop, and all routes at the stop)
  GBM  HistGradientBoostingRegressor(loss="poisson") on schedule/route/stop features plus
       historical rates at several levels (including B2's estimate). For training, those rates come
       from the other half of the training days, so a target never sees its own counts.
  GBM+B2  hybrid: the same boosting, learning a multiplicative correction to B2 (B2 as offset)

Protocol (ML_PLAN.md §4): tickets are split by date first, and every count-derived quantity is
recomputed from the training window only. Tuning: train 1-17 Oct, validate 18-24 Oct (picks the
smoothing strengths, GLM penalty and GBM settings). Final test, run once: train 1-24 Oct, test
25-31 Oct.

Run:    python src/ml/compare_models.py     (~50 min on a 16-core laptop; needs the same data/ as
                                             src/model/crowding.py)
Output: reports/ml_model_comparison.json
Data source: Delhi Transport Stack (DoT, GNCTD), License v1.0.
Third-party libs: scikit-learn, SciPy, pandas, NumPy.
"""
from __future__ import annotations
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import PoissonRegressor

if __package__ in (None, ""):  # run as a script: make src/ importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.daytypes import DAY_TYPES  # noqa: E402
from ml.demand import Fold, Static, b0_rates, b2_rates, load_static, load_tickets  # noqa: E402
from model.crowding import build_route_sequences  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "ml_model_comparison.json"

TUNE_TRAIN, TUNE_VALID = np.arange(1, 18), np.arange(18, 25)
FINAL_TRAIN, TEST = np.arange(1, 25), np.arange(25, 32)
MODELS = ("B0", "B1", "B2", "GLM", "GBM", "GBM+B2")

FLOORS = [1e-4, 3e-4, 1e-3, 3e-3, 1e-2, 3e-2]
EB_START = {"k0": 1.0, "kA": 3.0, "kB": 3.0, "kS0": 10.0, "kS": 30.0, "kC": 3.0}
EB_GRID = {"k0": [0.1, 0.3, 1, 3],                  # days of prior for route volume
           "kA": [0.3, 1, 3, 10, 30, 100],          # days, route x hour
           "kB": [1, 3, 10, 30, 100, 300],          # days, route x hour x day type
           "kS0": [3, 10, 30, 100, 300, 1000],      # passengers, stop share within route
           "kS": [10, 30, 100, 300, 1000, 3000],    # passengers, stop share within route and time band
           "kC": [1, 3, 10, 30, 100, 300]}          # days, the cell itself
GLM_ALPHAS = [1e-9, 3e-9, 1e-8, 3e-8]
GLM_MAX_ITER = 1000
# Strong L2 is essential: with Poisson loss a leaf's Newton step is ~ (actual - predicted) / predicted,
# which overshoots by orders of magnitude on busy cells that start near zero (sklearn has no
# max_delta_step). With l2_regularization=1 the model diverged within 20 trees.
GBM_CONFIGS = [dict(learning_rate=0.05, max_leaf_nodes=63, min_samples_leaf=200, l2_regularization=1000.0),
               dict(learning_rate=0.05, max_leaf_nodes=127, min_samples_leaf=100, l2_regularization=1000.0)]
GBM_MAX_ITER = 1000
STRUCT = ["hour", "day_type", "band", "pos", "relpos", "n_stops", "is_last", "sched_route",
          "sched_stop_all", "stop_routes", "route_trips_day", "direction", "night", "lat", "lon"]
HIST = ["h_cell", "h_cell_all_days", "h_route_stop", "h_route_hour", "h_route_hour_daytype",
        "h_route", "h_stop_other_routes", "h_b2"]
CATEGORICAL = [STRUCT.index(c) for c in ("day_type", "band", "direction")]
B2_COL = len(STRUCT) + HIST.index("h_b2")


def log(msg: str):
    print(msg, flush=True)


def pdev(y, mu):
    """Poisson unit deviance."""
    mu = np.maximum(mu, 1e-12)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(y > 0, y * np.log(y / mu), 0.0)
    return 2 * (t - y + mu)


def stop_deviance(rate, y, E, f: Fold) -> float:
    Ed = E[f.d]
    m = Ed > 0
    return float(pdev(y[m], rate[m] * Ed[m]).mean())


# ---------------------------------------------------------------- statistical models

def b1_rates(y, E, f: Fold):
    Ed = E[f.d]
    return np.divide(y, Ed, out=np.zeros_like(y), where=Ed > 0)


def tune_b2(ytr, Etr, yva, Eva, f: Fold):
    p = dict(EB_START)
    best = stop_deviance(b2_rates(ytr, Etr, f, p), yva, Eva, f)
    for _ in range(3):  # coordinate descent, three sweeps
        for k, grid in EB_GRID.items():
            for v in grid:
                q = {**p, k: float(v)}
                s = stop_deviance(b2_rates(ytr, Etr, f, q), yva, Eva, f)
                if s < best:
                    best, p = s, q
    return p


def glm_design(f: Fold):
    blocks = [f.r * 3 + f.d, f.g_rh, f.g_hd, f.rp, f.g_rpb, f.g_sb]
    cols, off = [], 0
    for b in blocks:
        _, inv = np.unique(b, return_inverse=True)
        cols.append(inv + off)
        off += int(inv.max()) + 1
    num = [np.log1p(f.sched), np.log1p(f.stop_sched)]
    cols += [np.full(f.n, off + j) for j in range(len(num))]
    k = len(cols)
    data = np.ones((f.n, k))
    for j, v in enumerate(num):
        data[:, len(blocks) + j] = v
    return sparse.csr_matrix((data.ravel(), np.stack(cols, axis=1).ravel(), np.arange(0, f.n * k + 1, k)),
                             shape=(f.n, off + len(num)))


def fit_glm(X, y, E, f: Fold, alpha: float):
    Ed = E[f.d]
    m = Ed > 0
    model = PoissonRegressor(alpha=alpha, solver="lbfgs", max_iter=GLM_MAX_ITER, tol=1e-6)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        model.fit(X[m], y[m] / Ed[m], sample_weight=Ed[m])
    return model


# ---------------------------------------------------------------- gradient boosting

def struct_features(f: Fold):
    st = f.st
    return np.column_stack([
        f.h, f.d, f.band, f.pos, f.relpos, st.n_stops[f.r], f.pos == st.n_stops[f.r] - 1, f.sched,
        f.stop_sched, st.stop_routes[f.s], st.trips_day[f.r], st.direction[f.r], st.night[f.r],
        st.stop_lat[f.s], st.stop_lon[f.s]]).astype(np.float32)


def hist_features(y, E, f: Fold, b2_params: dict):
    """Historical boardings per day at several levels, from one window's counts."""
    Etot, Ed = E.sum(), E[f.d]
    nan = np.full(f.n, np.nan)
    rhd = np.bincount(f.g_rhd, y)[f.g_rhd]
    stop_hd = np.bincount(f.g_shd, y)[f.g_shd]
    return np.column_stack([
        np.divide(y, Ed, out=nan.copy(), where=Ed > 0),
        np.bincount(f.i3, y, f.n3)[f.i3] / Etot,
        np.bincount(f.rp, y)[f.rp] / Etot,
        np.bincount(f.g_rh, y)[f.g_rh] / Etot,
        np.divide(rhd, Ed, out=nan.copy(), where=Ed > 0),
        np.bincount(f.r, y)[f.r] / Etot,
        np.divide(stop_hd - y, Ed, out=nan.copy(), where=Ed > 0),
        b2_rates(y, E, f, b2_params)]).astype(np.float32)


def halves_of(days: np.ndarray):
    return [days[days % 2 == 0], days[days % 2 == 1]]


def gbm_training_set(f: Fold, tk: dict, train_days: np.ndarray, S: np.ndarray, b2_params: dict):
    """Targets from one half of the training days, historical features from the other (both ways)."""
    halves = [f.counts(tk, h)[:2] for h in halves_of(train_days)]
    Xs, ys, ws = [], [], []
    for tgt, src in ((0, 1), (1, 0)):
        yt, Et = halves[tgt]
        w = Et[f.d]
        m = w > 0
        Xs.append(np.hstack([S[m], hist_features(*halves[src], f, b2_params)[m]]))
        ys.append(yt[m] / w[m])
        ws.append(w[m])
    return np.vstack(Xs), np.concatenate(ys), np.concatenate(ws), halves


def fit_gbm(X, y, w, cfg: dict, on_b2: bool):
    """on_b2: learn a multiplicative correction to B2 (B2 as a Poisson offset: target y / b2 with
    weight w * b2 has the same likelihood as y with mean w * b2 * correction)."""
    if on_b2:
        base = X[:, B2_COL].astype(float)
        y, w = y / base, w * base
    model = HistGradientBoostingRegressor(loss="poisson", max_iter=GBM_MAX_ITER, early_stopping=True,
                                          validation_fraction=0.1, n_iter_no_change=20,
                                          categorical_features=CATEGORICAL, random_state=0, **cfg)
    return model.fit(X, y, sample_weight=w)


def gbm_predict(model, S, f: Fold, ytr, Etr, halves, b2_params: dict, mode: str, on_b2: bool):
    """mode "full": historical features from the whole training window; "halves": average of the
    predictions from each half (same noise level as in training)."""
    def one(y, E):
        X = np.hstack([S, hist_features(y, E, f, b2_params)])
        p = model.predict(X)
        return p * X[:, B2_COL] if on_b2 else p
    if mode == "full":
        return one(ytr, Etr)
    return np.mean([one(*h) for h in halves], axis=0)


# ---------------------------------------------------------------- evaluation

def evaluate(rate, y, E, f: Fold, ytr) -> dict:
    """Held-out metrics at the stop grain and summed to route x hour x day type."""
    Ed = E[f.d]
    m = Ed > 0
    mu = rate * Ed
    dev = pdev(y, mu)
    vol3 = np.bincount(f.i3, ytr, f.n3)[f.i3]
    out = {"stop": {"deviance": float(dev[m].mean()),
                    "wape": float(np.abs(y - mu)[m].sum() / y[m].sum())},
           "stop_deviance_by_train_pax": {}}
    for lo, hi, label in ((0, 0, "0"), (1, 4, "1-4"), (5, 19, "5-19"), (20, np.inf, "20+")):
        s = m & (vol3 >= lo) & (vol3 <= hi)
        out["stop_deviance_by_train_pax"][label] = {"cells": int(s.sum()), "deviance": float(dev[s].mean())}

    G = f.R * 72
    Y, M = np.bincount(f.g_rhd, y, G), np.bincount(f.g_rhd, mu, G)
    g = np.arange(G)
    present = (np.bincount(f.g_rhd, minlength=G) > 0) & (E[g % 3] > 0)
    devG = pdev(Y, M)
    wk = present & (g % 3 == 0) & (Y >= 10)
    busy = present & (M >= 1)
    out["route_hour"] = {
        "deviance": float(devG[present].mean()),
        "wape": float(np.abs(Y - M)[present].sum() / Y[present].sum()),
        "spearman_weekday_10plus": float(spearmanr(Y[wk], M[wk]).statistic),
        "pearson_dispersion": float(((Y[busy] - M[busy]) ** 2 / M[busy]).mean()),
        "predicted_over_actual": float(M[present].sum() / Y[present].sum()),
    }
    vol_rh = np.bincount(f.g_rh, ytr, f.R * 24)[g // 3]
    out["route_hour_deviance_by_train_pax"] = {}
    for lo, hi, label in ((0, 0, "0"), (1, 29, "1-29"), (30, 99, "30-99"), (100, np.inf, "100+")):
        s = present & (vol_rh >= lo) & (vol_rh <= hi)
        out["route_hour_deviance_by_train_pax"][label] = {"cells": int(s.sum()), "deviance": float(devG[s].mean())}
    return out


def run_fold(label: str, st: Static, tk: dict, dt_of_day, train_days, eval_days, params: dict | None):
    """Fit every model on train_days and score on eval_days. params=None: tune on eval_days."""
    tuning = params is None
    params = {} if tuning else params
    log(f"\n=== {label}: train {train_days[0]}-{train_days[-1]} Oct, evaluate {eval_days[0]}-{eval_days[-1]} Oct ===")
    f = Fold(st, tk, train_days, dt_of_day)
    ytr, Etr, _, _ = f.counts(tk, train_days)
    yev, Eev, outside, total = f.counts(tk, eval_days)
    info = {"cells": f.n, "train_days": dict(zip(DAY_TYPES, Etr.astype(int).tolist())),
            "eval_days": dict(zip(DAY_TYPES, Eev.astype(int).tolist())),
            "train_pax": float(ytr.sum()), "eval_pax": total,
            "eval_pax_outside_cells_pct": round(100 * outside / total, 2)}
    log(f"  cells {f.n:,}; eval pax outside cells {info['eval_pax_outside_cells_pct']}%")
    preds, seconds = {}, {}

    for name, fn in (("B0", b0_rates), ("B1", b1_rates)):
        t0 = time.time()
        raw = fn(ytr, Etr, f)
        if tuning:
            params[f"{name}_floor"] = min(FLOORS, key=lambda fl: stop_deviance(np.maximum(raw, fl), yev, Eev, f))
        preds[name] = np.maximum(raw, params[f"{name}_floor"])
        seconds[name] = round(time.time() - t0, 1)

    t0 = time.time()
    if tuning:
        params["B2"] = tune_b2(ytr, Etr, yev, Eev, f)
        params["B2_at_grid_edge"] = [k for k, v in params["B2"].items() if v in (EB_GRID[k][0], EB_GRID[k][-1])]
        log(f"  B2 smoothing: {params['B2']} (at grid edge: {params['B2_at_grid_edge'] or 'none'})")
    preds["B2"] = b2_rates(ytr, Etr, f, params["B2"])
    seconds["B2"] = round(time.time() - t0, 1)

    t0 = time.time()
    X = glm_design(f)
    log(f"  GLM design {X.shape[0]:,} x {X.shape[1]:,}")
    if tuning:
        best = None
        for alpha in GLM_ALPHAS:
            t1 = time.time()
            model = fit_glm(X, ytr, Etr, f, alpha)
            pred = model.predict(X)
            s = stop_deviance(pred, yev, Eev, f)
            log(f"  GLM alpha={alpha:g}: valid deviance {s:.5f}, {model.n_iter_} iterations, {time.time() - t1:.0f}s")
            if best is None or s < best[0]:
                best = (s, alpha, pred)
        params["GLM_alpha"], preds["GLM"] = best[1], best[2]
    else:
        preds["GLM"] = fit_glm(X, ytr, Etr, f, params["GLM_alpha"]).predict(X)
    seconds["GLM"] = round(time.time() - t0, 1)
    del X

    t0 = time.time()
    S = struct_features(f)
    Xg, yg, wg, halves = gbm_training_set(f, tk, train_days, S, params["B2"])
    log(f"  GBM training rows {len(yg):,} x {Xg.shape[1]}")
    setup = time.time() - t0
    for name, on_b2 in (("GBM", False), ("GBM+B2", True)):
        t0 = time.time()
        if tuning:
            best = None
            for i, cfg in enumerate(GBM_CONFIGS):
                t1 = time.time()
                model = fit_gbm(Xg, yg, wg, cfg, on_b2)
                for mode in ("full", "halves"):
                    pred = gbm_predict(model, S, f, ytr, Etr, halves, params["B2"], mode, on_b2)
                    s = stop_deviance(pred, yev, Eev, f)
                    log(f"  {name} config {i} ({model.n_iter_} trees, {time.time() - t1:.0f}s), {mode}: "
                        f"valid deviance {s:.5f}")
                    if best is None or s < best[0]:
                        best = (s, {"config": i, "mode": mode, "trees": int(model.n_iter_)}, pred)
            params[name], preds[name] = best[1], best[2]
        else:
            model = fit_gbm(Xg, yg, wg, GBM_CONFIGS[params[name]["config"]], on_b2)
            preds[name] = gbm_predict(model, S, f, ytr, Etr, halves, params["B2"], params[name]["mode"], on_b2)
            log(f"  {name}: {model.n_iter_} trees")
        seconds[name] = round(time.time() - t0 + setup, 1)
    del Xg, yg, wg

    results = {name: evaluate(preds[name], yev, Eev, f, ytr) for name in MODELS}
    for name in MODELS:
        results[name]["fit_seconds"] = seconds[name]
        results[name]["stop_deviance_vs_B2_pct"] = round(
            100 * (1 - results[name]["stop"]["deviance"] / results["B2"]["stop"]["deviance"]), 2)
    print_table(results)
    return {"info": info, "models": results}, params


def print_table(results: dict):
    log(f"  {'model':6} {'stop dev':>9} {'vs B2':>7} {'stop WAPE':>9} {'RH dev':>8} {'RH WAPE':>8} "
        f"{'RH rho':>7} {'pred/act':>8} {'disp':>6} {'secs':>6}")
    for name, r in results.items():
        rh = r["route_hour"]
        log(f"  {name:6} {r['stop']['deviance']:9.5f} {r['stop_deviance_vs_B2_pct']:6.1f}% {r['stop']['wape']:9.3f} "
            f"{rh['deviance']:8.3f} {rh['wape']:8.3f} {rh['spearman_weekday_10plus']:7.3f} "
            f"{rh['predicted_over_actual']:8.3f} {rh['pearson_dispersion']:6.2f} {r['fit_seconds']:6.0f}")


def main():
    t0 = time.time()
    log("Loading GTFS + resolved e-tickets ...")
    seqs, tph = build_route_sequences()
    st = load_static(seqs, tph)
    tk, dt_of_day = load_tickets(seqs, st)
    log(f"  {len(st.routes):,} routes, {len(tk['pax']):,} tickets with a boarding stop on their route "
        f"({time.time() - t0:.0f}s)")

    validation, params = run_fold("Tuning", st, tk, dt_of_day, TUNE_TRAIN, TUNE_VALID, None)
    test, _ = run_fold("Final test", st, tk, dt_of_day, FINAL_TRAIN, TEST, params)

    report = {
        "question": "Statistical models vs gradient boosting for boardings per (route, stop, hour, day type)",
        "generated_at": pd.Timestamp.now(tz="Asia/Kolkata").isoformat(timespec="seconds"),
        "target": "mobile-ticket boardings per day; hour = purchase hour; day types " + ", ".join(DAY_TYPES),
        "splits": {"tuning": "train 1-17 Oct, validate 18-24 Oct",
                   "final_test": "train 1-24 Oct, test 25-31 Oct (run once with the tuned settings)"},
        "metrics": {
            "deviance": "mean Poisson deviance per cell (lower is better)",
            "wape": "sum |actual - predicted| / sum actual",
            "spearman_weekday_10plus": "rank correlation over weekday route-hours with >= 10 test pax",
            "pearson_dispersion": "mean (actual - predicted)^2 / predicted over route-hours expecting >= 1 "
                                  "passenger; 1 = Poisson noise only",
            "predicted_over_actual": "total predicted / total actual passengers",
        },
        "tuned_params": params,
        "features": {"gbm_structural": STRUCT, "gbm_historical": HIST},
        "validation": validation,
        "test": test,
        "runtime_sec": round(time.time() - t0, 1),
    }
    OUT.write_text(json.dumps(report, indent=2))
    log(f"\nreport -> {OUT.relative_to(ROOT)}  ({report['runtime_sec']}s)")


if __name__ == "__main__":
    main()
