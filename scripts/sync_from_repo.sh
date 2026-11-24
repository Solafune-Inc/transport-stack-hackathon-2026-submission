#!/usr/bin/env bash
# Refresh submission_1st_phase/ from the main repo tree: code, mobile app, the team's EDA and
# reports, the crowding model tables (gzipped) and a local copy of the raw GTFS (gitignored).
# Rerunnable. Never touches the hand-authored files (README, docker/, compose, findings/, ...).
#
#   bash submission_1st_phase/scripts/sync_from_repo.sh
set -euo pipefail

SUB="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(git -C "$SUB" rev-parse --show-toplevel)"
if [[ "$REPO" == "$SUB" ]]; then
  echo "this is the submission repo itself: run the script from the team's working repo" >&2
  exit 1
fi
cd "$REPO"

need() { [[ -e "$1" ]] || { echo "missing $REPO/$1 ($2)" >&2; exit 1; }; }
need data/delhi_buses_static_gtfs/stop_times.txt "get the GTFS: see data/README.md"
for t in segments_daytype route_hour_daytype stop_hour_daytype operator; do
  need "data/eticketing/crowding_${t}.csv" "run: python src/resolve_stops.py && python src/model/crowding.py"
done
need data/eticketing/crowding_model.json "run: python src/model/crowding.py"

RSYNC=(rsync -a --delete --exclude __pycache__ --exclude .pytest_cache --exclude .DS_Store)

echo "- code"
"${RSYNC[@]}" src/ "$SUB/src/"
"${RSYNC[@]}" tests/ "$SUB/tests/"
cp pytest.ini requirements.txt "$SUB/"

echo "- mobile app"
"${RSYNC[@]}" --exclude node_modules --exclude .expo --exclude dist --exclude web-build \
  --exclude .local --exclude ios --exclude android --exclude 'src/map/*.generated.ts' --exclude '.env*' \
  mobile-implementation/ "$SUB/mobile-implementation/"

echo "- team EDA, reports, plans"
"${RSYNC[@]}" notebooks/ "$SUB/notebooks/"
# coverage / live / per-bus maps embed raw GTFS-RT positions (gitignored in the repo too)
"${RSYNC[@]}" --exclude 'coverage_map*.html' --exclude live_bus_map.html --exclude 'track_*.html' \
  reports/ "$SUB/reports/"
mkdir -p "$SUB/docs"
cp PLAN.md ML_PLAN.md "$SUB/docs/"

echo "- crowding model tables + operator table (gzipped)"
mkdir -p "$SUB/data/eticketing"
for t in segments_daytype route_hour_daytype stop_hour_daytype operator; do
  # -n: no name/timestamp in the header, so unchanged tables stay byte-identical in git
  gzip -9 -n -c "data/eticketing/crowding_${t}.csv" > "$SUB/data/eticketing/crowding_${t}.csv.gz"
done
cp data/eticketing/crowding_model.json "$SUB/data/eticketing/"
cp data/README.md data/LICENSE-NOTES.md "$SUB/data/"

echo "- raw GTFS (local only, gitignored)"
GTFS="$SUB/data/delhi_buses_static_gtfs"
mkdir -p "$GTFS"
cp -L data/delhi_buses_static_gtfs/*.txt "$GTFS/"
chmod -R a+rX "$GTFS"   # the source is owner-only; the container runs as a non-root user

{
  echo "commit:      $(git rev-parse HEAD) ($(git rev-parse --abbrev-ref HEAD))"
  echo "uncommitted: $(git status --porcelain -- . ':!submission_1st_phase' | wc -l | tr -d ' ') changed files in the repo at sync time"
  echo "synced:      $(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$SUB/SNAPSHOT.txt"

echo "done: $(du -sh "$SUB" | cut -f1) in $SUB (GTFS copy: $(du -sh "$GTFS" | cut -f1), not committed)"
