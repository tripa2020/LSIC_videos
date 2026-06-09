"""Stage B — Download the selected docs (PDF/PPTX) into ../LSIC_Downloads/. KEPT.

Docs are public on lsic.jhuapl.edu; target filename == basename(filePath), already
`<lsic_id>-<name>.<ext>` matching the pipeline's convention. Idempotent (skip-existing),
atomic (temp → rename), with a results log and one retry pass.

Run:  python download_lsic/fetch_docs.py            # all pdf/pptx in the selection
      python download_lsic/fetch_docs.py 3105 3106  # only these lsic_ids (pilot)
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
SELECTED = HERE / "selected_manifest.json"
DEST = HERE.parent / "LSIC_Downloads"
RESULTS = HERE / "download_results.json"
KINDS = {"pdf", "pptx"}


def encode(url: str) -> str:
    return urllib.parse.quote(url, safe=":/?&=%")


def curl(url: str, dest: Path) -> tuple[bool, str]:
    tmp = dest.with_suffix(dest.suffix + ".part")
    r = subprocess.run(
        ["curl", "-sL", "--fail", "--max-time", "300", "-o", str(tmp), encode(url)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        tmp.unlink(missing_ok=True)
        return False, f"curl rc={r.returncode}"
    # sanity: non-empty + right magic
    head = tmp.read_bytes()[:4] if tmp.exists() else b""
    ok = head[:4] == b"%PDF" if dest.suffix == ".pdf" else head[:2] == b"PK"
    if not ok:
        tmp.unlink(missing_ok=True)
        return False, f"bad magic {head!r}"
    tmp.rename(dest)
    return True, "ok"


def main(argv: list[str]) -> None:
    rows = json.loads(SELECTED.read_text())
    want_ids = {int(a) for a in argv if a.isdigit()} or None

    docs, seen = [], set()
    for r in rows:
        if r["kind"] not in KINDS or not r["url"] or not r["target_filename"]:
            continue
        if want_ids and r["lsic_id"] not in want_ids:
            continue
        if r["target_filename"] in seen:  # dedup within selection
            continue
        seen.add(r["target_filename"])
        docs.append(r)

    DEST.mkdir(exist_ok=True)
    ok, failed, skipped = [], [], []
    for i, r in enumerate(docs, 1):
        dest = DEST / r["target_filename"]
        if dest.exists():
            skipped.append(r["target_filename"])
            continue
        good, why = curl(r["url"], dest)
        (ok if good else failed).append({"file": r["target_filename"], "why": why, "url": r["url"]})
        if i % 25 == 0 or i == len(docs):
            print(f"  {i}/{len(docs)}  ok={len(ok)} fail={len(failed)} skip={len(skipped)}")

    # one retry pass for failures
    retry_ok = []
    for f in list(failed):
        dest = DEST / f["file"]
        good, why = curl(f["url"], dest)
        if good:
            retry_ok.append(f["file"]); failed.remove(f); ok.append(f)
    if retry_ok:
        print(f"  retry recovered {len(retry_ok)}")

    RESULTS.write_text(json.dumps(
        {"downloaded": len(ok), "skipped": len(skipped), "failed": failed,
         "dest": str(DEST)}, indent=2))
    print(f"\n[done] downloaded={len(ok)} skipped(existing)={len(skipped)} failed={len(failed)}")
    if failed:
        print("  FAILURES:")
        for f in failed[:20]:
            print(f"   - {f['file']}: {f['why']}")
    print(f"[ok] results → {RESULTS.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main(sys.argv[1:])
