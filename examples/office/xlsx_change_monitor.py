#!/usr/bin/env python3
"""
Shared-spreadsheet change monitor — snapshot / diff / attributed change-log
for a workbook that several people edit online (OneDrive / SharePoint / Teams,
Google Drive desktop sync, a shared Dropbox folder, etc.).

The problem: a shared sheet drifts between the times you touch it, and you
have no record of who changed what. This keeps a private baseline of the
sheet's contents and, on demand, diffs the current file against it — so you
can log other people's edits AND your own to a human-readable change-log
that lives next to the sheet.

Run it as a three-step ritual whenever you (or your agent) edit the sheet:

  1. python3 xlsx_change_monitor.py check --author "teammates (online)"
        -> logs any drift since the last baseline (edits others made), re-snapshots
  2. <make your edit to the workbook>
  3. python3 xlsx_change_monitor.py check --author "me"
        -> logs the edit you just made, re-snapshots

Other commands:
  snapshot   -> (re)initialise the baseline silently, no logging
  status     -> print the current diff vs baseline without logging or re-snapshotting

Rows are keyed by one or more "key columns" (e.g. a name or an ID) so the log
reads by row identity ("CHANGED row X: Email a -> b"), not by opaque cell refs.

Caveat: detection relies on the cloud client having synced others' online
edits down to local disk. Sync can lag a minute or two; if you know someone
just edited, wait before running `check`.
"""
import json
import os
import argparse
import datetime

# --- Config ---
SHEET = os.path.expanduser("<shared-sheet>.xlsx")          # the workbook to watch
BASELINE = os.path.expanduser("<watcher-dir>/sheet-baseline.json")  # private, NOT in the shared folder
LOG = os.path.join(os.path.dirname(SHEET), "change log.txt")        # lives next to the sheet (others can see it)

HEADER_ROW = 1          # 1-based row holding the column names
DATA_START = 2          # 1-based first data row
KEY_COLS = (0,)         # 0-based column indices that together identify a row


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def read_sheet():
    import openpyxl
    wb = openpyxl.load_workbook(SHEET, data_only=True)
    ws = wb.worksheets[0]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]

    def s(v):
        return "" if v is None else str(v).strip()

    headers = [s(c) for c in rows[HEADER_ROW - 1]] if len(rows) >= HEADER_ROW else []
    # cells above the header row are tracked verbatim by cell ref (titles, banners)
    banner = {}
    for ri in range(0, HEADER_ROW - 1):
        if ri < len(rows):
            for ci, c in enumerate(rows[ri]):
                if s(c):
                    banner["R%dC%d" % (ri + 1, ci + 1)] = s(c)
    data = {}
    for ri in range(DATA_START - 1, len(rows)):
        vals = [s(c) for c in rows[ri]]
        if not any(vals):
            continue
        key = " || ".join(vals[k] if k < len(vals) else "" for k in KEY_COLS)
        base, n = key, 2
        while key in data:               # disambiguate duplicate keys
            key = "%s #%d" % (base, n); n += 1
        data[key] = {h: (vals[ci] if ci < len(vals) else "")
                     for ci, h in enumerate(headers) if h}
    return {"headers": headers, "banner": banner, "data": data}


def load_baseline():
    if not os.path.exists(BASELINE):
        return None
    with open(BASELINE) as f:
        return json.load(f)


def save_baseline(state):
    os.makedirs(os.path.dirname(BASELINE), exist_ok=True)
    with open(BASELINE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


def diff(old, new):
    changes = []
    ob, nb = old.get("banner", {}), new.get("banner", {})
    for k in sorted(set(ob) | set(nb)):
        if ob.get(k, "") != nb.get(k, ""):
            changes.append('~ banner %s: "%s" -> "%s"' % (k, ob.get(k, ""), nb.get(k, "")))
    if old.get("headers") != new.get("headers"):
        changes.append('~ column headers: %s -> %s' % (old.get("headers"), new.get("headers")))
    od, nd = old.get("data", {}), new.get("data", {})
    for key in nd:
        if key not in od:
            detail = ", ".join("%s=%s" % (h, v) for h, v in nd[key].items() if v)
            changes.append('+ ADDED   %s  [%s]' % (key, detail))
    for key in od:
        if key not in nd:
            changes.append('- REMOVED %s' % key)
    for key in nd:
        if key in od:
            fields = []
            for h in dict.fromkeys(list(od[key]) + list(nd[key])):
                ov, nv = od[key].get(h, ""), nd[key].get(h, "")
                if ov != nv:
                    fields.append('%s: "%s" -> "%s"' % (h, ov, nv))
            if fields:
                changes.append('~ CHANGED %s: ' % key + "; ".join(fields))
    return changes


def append_log(author, changes):
    block = "\n".join(["%s | %s | %d change(s)" % (now(), author, len(changes))]
                      + ["    " + c for c in changes]) + "\n"
    new_file = not os.path.exists(LOG)
    with open(LOG, "a", encoding="utf-8") as f:
        if new_file:
            f.write("CHANGE LOG\n==========\n")
            f.write("Logs edits teammates make online AND edits you make.\n")
            f.write("Format: YYYY-MM-DD HH:MM | author | N change(s), then indented detail.\n\n")
        f.write(block + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["snapshot", "check", "status"])
    ap.add_argument("--author", default="unknown")
    args = ap.parse_args()

    cur = read_sheet()

    if args.cmd == "snapshot":
        save_baseline(cur)
        print("baseline initialised: %d rows" % len(cur["data"]))
        return

    base = load_baseline()
    if base is None:
        save_baseline(cur)
        if args.cmd == "check":
            append_log("baseline initialised", ["tracking %d rows from this point" % len(cur["data"])])
        print("no baseline existed; initialised with %d rows" % len(cur["data"]))
        return

    changes = diff(base, cur)

    if args.cmd == "status":
        print("%d change(s) vs baseline:" % len(changes) if changes else "no changes vs baseline")
        for c in changes:
            print("  " + c)
        return

    # cmd == check
    if changes:
        append_log(args.author, changes)
        print("logged %d change(s) under '%s'" % (len(changes), args.author))
        for c in changes:
            print("  " + c)
    else:
        print("no changes vs baseline (nothing logged for '%s')" % args.author)
    save_baseline(cur)


if __name__ == "__main__":
    main()
