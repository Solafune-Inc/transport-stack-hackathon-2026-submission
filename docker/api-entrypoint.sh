#!/bin/sh
# Fail fast with a readable message when the (licensed, gitignored) GTFS feed isn't mounted,
# instead of a pandas traceback ten seconds into startup.
set -eu

GTFS=/app/data/delhi_buses_static_gtfs
missing=""
for f in routes trips stop_times stops shapes; do
  [ -s "$GTFS/$f.txt" ] || missing="$missing $f.txt"
done

if [ -n "$missing" ]; then
  cat >&2 <<EOF

  GTFS static feed not found (missing:$missing).

  Put the Delhi Buses GTFS .txt files in data/delhi_buses_static_gtfs/:
  download "Delhi Buses GTFS Static" from https://delhi.transportstack.in
  and unzip it there (see README.md, "Data").
  Then run: docker compose up --build

EOF
  exit 1
fi

exec python src/api/main.py --host 0.0.0.0 --port 8787 "$@"
