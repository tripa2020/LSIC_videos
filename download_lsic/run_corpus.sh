#!/usr/bin/env bash
# Drive the LSIC pipeline over a set of events, end to end.
#
# Bakes in the correct asset ordering (the gap that caused a "Package not found" at ingest):
#   1. group_manifest  → build events.json (relocates any docs already present)
#   2. fetch_docs       → download the targets' decks (PDF/PPTX) flat
#   3. group_manifest   → re-run so the now-present decks get relocated into event folders
#   4. pipeline loop    → ingest downloads each video, then the full per-event pipeline
#
# SYNC by default → same output as a local run (Part 2 "same state" requirement).
# Set EXTRA=--batch to route LLM stages through Gemini Batch (Part 3, cheaper, async).
#
# Usage:
#   ./download_lsic/run_corpus.sh slice            # the 5 batch-1 picks (batch1_slice.txt)
#   ./download_lsic/run_corpus.sh filter           # the full Energy∪ISRU 122-with-video set
#   ./download_lsic/run_corpus.sh ids.txt          # a file of catalog event_ids (one per line)
#
# Env knobs (all optional):
#   PY=python  CAP_HOURS=4  CONC=1  EXTRA=--batch  GCS_BUCKET=gs://my-bucket/lsic
set -uo pipefail

PY="${PY:-python}"
CAP_HOURS="${CAP_HOURS:-4}"
CONC="${CONC:-1}"
EXTRA="${EXTRA:-}"
GCS_BUCKET="${GCS_BUCKET:-}"
SOURCE="${1:-slice}"

# --- 1. resolve catalog event_ids to process ---
case "$SOURCE" in
  slice)  IDS=$(grep -v '^#' download_lsic/batch1_slice.txt | awk '{print $1}') ;;
  filter) IDS=$("$PY" -c "from src.topic_filter import energy_isru_event_ids, with_video; print('\n'.join(sorted(with_video(ids=energy_isru_event_ids()))))") ;;
  *)      IDS=$(grep -v '^#' "$SOURCE" | awk '{print $1}') ;;
esac
[ -z "$IDS" ] && { echo "no event_ids resolved from '$SOURCE'"; exit 1; }
echo "[run_corpus] $(echo "$IDS" | wc -w | tr -d ' ') events from '$SOURCE'"

# --- 2. fetch decks, then group so they relocate (correct order) ---
"$PY" -m src.group_manifest $IDS >/dev/null
DOC_IDS=$("$PY" - "$IDS" <<'PYEOF'
import json, sys
ids = set(sys.argv[1].split())
rows = json.load(open("download_lsic/selected_manifest.json"))
print(" ".join(str(r["lsic_id"]) for r in rows
                if r.get("event_id") in ids
                and r.get("kind") in ("pdf", "pptx") and r.get("lsic_id")))
PYEOF
)
[ -n "$DOC_IDS" ] && "$PY" -m download_lsic.fetch_docs $DOC_IDS
"$PY" -m src.group_manifest $IDS >/dev/null   # re-relocate the freshly-fetched decks

# --- 3. resolve to pipeline lsic_<date> ids ---
EVTS=$("$PY" -c "import json; print('\n'.join(e['event_id'] for e in json.load(open('work/events.json'))['events']))")

# --- 4. run the pipeline per event (isolated → safe to parallelize) ---
mkdir -p logs
run_one() {
  local evt="$1" rc
  echo "===== $evt =====" >&2
  if [ -n "${VERBOSE:-}" ]; then          # VERBOSE=1 → stream live to terminal AND log
    "$PY" -m src.main --pipeline --event "$evt" --keep-going \
        --cap-video-hours "$CAP_HOURS" $EXTRA 2>&1 | tee "logs/${evt}.log"
    rc=${PIPESTATUS[0]}
  else                                     # default → quiet to log file (good for -P parallel)
    "$PY" -m src.main --pipeline --event "$evt" --keep-going \
        --cap-video-hours "$CAP_HOURS" $EXTRA > "logs/${evt}.log" 2>&1
    rc=$?
  fi
  if [ "$rc" -eq 0 ]; then
    echo "✅ $evt"
    [ -n "$GCS_BUCKET" ] && gsutil -m rsync -r "work/events/${evt}/Report" \
        "${GCS_BUCKET}/${evt}/Report" >/dev/null 2>&1
  else
    echo "❌ $evt  (tail: $(tail -1 "logs/${evt}.log"))"
  fi
}
export -f run_one; export PY CAP_HOURS EXTRA GCS_BUCKET

if [ "$CONC" -gt 1 ] && command -v xargs >/dev/null; then
  echo "$EVTS" | xargs -P "$CONC" -I{} bash -c 'run_one "$@"' _ {}
else
  while IFS= read -r evt; do [ -n "$evt" ] && run_one "$evt"; done <<< "$EVTS"
fi

# --- 5. summary ---
done_n=$(grep -lc "report OK\|report ·" logs/*.log 2>/dev/null | wc -l | tr -d ' ')
echo "[run_corpus] done — Report bundles in work/events/<id>/Report/"
[ -n "$GCS_BUCKET" ] && echo "[run_corpus] synced to ${GCS_BUCKET}/<id>/Report/"
