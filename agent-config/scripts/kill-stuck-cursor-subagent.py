#!/usr/bin/env python3
"""Archive a stuck Cursor Multitask/Working subagent that Stop/restart cannot clear.

IMPORTANT: Fully Quit Cursor (Cmd+Q) before running. Writing while Cursor is open
will usually be overwritten on next save / exit.

Default target: E2E validate Discover IA / Kill Discover E2E
  composerId = 0ceea54a-1f8e-4fb9-be3a-bc12ff09a4ad
  parent     = 54ba56c5-894e-495f-8437-a40c087f7d80
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path

DEFAULT_CID = "0ceea54a-1f8e-4fb9-be3a-bc12ff09a4ad"
DEFAULT_PARENT = "54ba56c5-894e-495f-8437-a40c087f7d80"
DB = (
    Path.home()
    / "Library/Application Support/Cursor/User/globalStorage/state.vscdb"
)


def cursor_running() -> bool:
    # Best-effort: Cursor main process holding UI / state.vscdb.
    import subprocess

    patterns = (
        "/Applications/Cursor.app/Contents/MacOS/Cursor",
        "Cursor.app/Contents/MacOS/Cursor",
    )
    for pat in patterns:
        try:
            out = subprocess.check_output(["pgrep", "-f", pat], text=True).strip()
            if out:
                return True
        except subprocess.CalledProcessError:
            continue
    return False


def archive_header(cur: sqlite3.Cursor, cid: str) -> None:
    row = cur.execute(
        "SELECT isArchived, value FROM composerHeaders WHERE composerId=?",
        (cid,),
    ).fetchone()
    if not row:
        raise SystemExit(f"composerHeaders row not found for {cid}")
    is_archived, value = row
    data = json.loads(value) if value else {}
    data["isArchived"] = True
    # Keep UI consistent if it reads status from header blob.
    if data.get("status") not in ("aborted", "completed", "cancelled"):
        data["status"] = "aborted"
    cur.execute(
        """
        UPDATE composerHeaders
        SET isArchived=1, value=?, lastUpdatedAt=?
        WHERE composerId=?
        """,
        (json.dumps(data, ensure_ascii=False, separators=(",", ":")), int(time.time() * 1000), cid),
    )
    print(f"composerHeaders: {cid} isArchived {is_archived} -> 1")


def patch_composer_data(cur: sqlite3.Cursor, key: str, mutator) -> None:
    row = cur.execute(
        "SELECT value FROM cursorDiskKV WHERE key=?", (key,)
    ).fetchone()
    if not row:
        print(f"skip missing {key}")
        return
    raw = row[0]
    text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
    data = json.loads(text)
    before = json.dumps(data.get("subagentComposerIds"), sort_keys=True)
    mutator(data)
    after = json.dumps(data.get("subagentComposerIds"), sort_keys=True)
    new = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    cur.execute("UPDATE cursorDiskKV SET value=? WHERE key=?", (new, key))
    print(f"patched {key}")
    if before != after:
        print(f"  subagentComposerIds changed")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--composer-id", default=DEFAULT_CID)
    ap.add_argument("--parent-id", default=DEFAULT_PARENT)
    ap.add_argument(
        "--force-while-cursor-running",
        action="store_true",
        help="Dangerous: write even if Cursor is running (often overwritten)",
    )
    ap.add_argument(
        "--archive-all-aborted-siblings",
        action="store_true",
        help="Also archive other aborted, non-archived subagents of the same parent",
    )
    args = ap.parse_args()

    if not DB.exists():
        raise SystemExit(f"DB not found: {DB}")

    if cursor_running() and not args.force_while_cursor_running:
        print(
            "Cursor is still running. Fully Quit Cursor (Cmd+Q), then re-run:\n"
            f"  python3 {Path(__file__).resolve()}",
            file=sys.stderr,
        )
        return 2

    backup = DB.with_suffix(f".vscdb.bak-kill-subagent-{int(time.time())}")
    print(f"backup -> {backup}")
    shutil.copy2(DB, backup)

    con = sqlite3.connect(str(DB))
    try:
        cur = con.cursor()
        archive_header(cur, args.composer_id)

        def mut_child(d: dict) -> None:
            d["status"] = "aborted"
            d["generatingBubbleIds"] = []
            d["isArchived"] = True

        def mut_parent(d: dict) -> None:
            subs = list(d.get("subagentComposerIds") or [])
            if args.composer_id in subs:
                d["subagentComposerIds"] = [x for x in subs if x != args.composer_id]
            # Do not touch parent status; parent chat may still be active later.

        patch_composer_data(cur, f"composerData:{args.composer_id}", mut_child)
        patch_composer_data(cur, f"composerData:{args.parent_id}", mut_parent)

        if args.archive_all_aborted_siblings:
            parent_raw = cur.execute(
                "SELECT value FROM cursorDiskKV WHERE key=?",
                (f"composerData:{args.parent_id}",),
            ).fetchone()
            parent = json.loads(
                parent_raw[0].decode()
                if isinstance(parent_raw[0], (bytes, bytearray))
                else parent_raw[0]
            )
            remaining = list(parent.get("subagentComposerIds") or [])
            removed = []
            for sid in list(remaining):
                crow = cur.execute(
                    "SELECT value FROM cursorDiskKV WHERE key=?",
                    (f"composerData:{sid}",),
                ).fetchone()
                if not crow:
                    continue
                cdata = json.loads(
                    crow[0].decode()
                    if isinstance(crow[0], (bytes, bytearray))
                    else crow[0]
                )
                if cdata.get("status") in ("aborted", "completed", "cancelled"):
                    archive_header(cur, sid)
                    remaining = [x for x in remaining if x != sid]
                    removed.append(sid)
            parent["subagentComposerIds"] = remaining
            cur.execute(
                "UPDATE cursorDiskKV SET value=? WHERE key=?",
                (
                    json.dumps(parent, ensure_ascii=False, separators=(",", ":")).encode(
                        "utf-8"
                    ),
                    f"composerData:{args.parent_id}",
                ),
            )
            print(f"archived aborted siblings: {len(removed)}")

        con.commit()
        cur.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        print("OK — reopen Cursor; Working entry should be gone.")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
