#!/usr/bin/env python3
"""health_sentinel.py: a daily check that your automations are alive.

Runs once a day (launchd), reads a list of "contracts", and writes:
  - a JSON status file (always), for a morning briefing to read
  - an inbox alert note (only when something is red, at most one per day)

A contract says what "alive" means for one job:
  launchd  the job's last exit status is 0
  fresh    a file (log, output, database) was modified within N hours
  newest   the newest file matching a glob is younger than N hours
  port     something answers on a local TCP port

This is a LIVENESS check. It tells you a job ran. It cannot tell you the job
did anything useful: a job that runs, logs, exits 0 and finds nothing will
pass every check here. See docs/08-keeping-automations-honest.md for the
second kind of check that catches that.

    python3 health_sentinel.py [--config contracts.json] [--dry-run]
"""
import argparse
import datetime
import glob
import json
import os
import pathlib
import socket
import subprocess

NOW = datetime.datetime.now()
HOME = pathlib.Path.home()

# Adapt: your launchd label prefix, vault inbox and contracts.
DEFAULT = {
    "launchd_prefix": "com.example.",
    "inbox": "~/Vault/00-Inbox",
    "status_file": "~/.local/share/watchers/health.json",
    "contracts": [
        {"name": "vault auto-commit", "kind": "fresh", "path": "~/Vault/.git/refs/heads/main", "hours": 3},
        {"name": "nightly synthesis", "kind": "newest", "glob": "~/Vault/00-Inbox/dream-*.md", "hours": 48},
        {"name": "index rebuild log", "kind": "fresh", "path": "~/.local/share/watchers/index.log", "hours": 26},
        {"name": "db backup log", "kind": "fresh", "path": "~/.local/share/watchers/db-backup.log", "hours": 26},
        {"name": "weekly watcher", "kind": "fresh", "path": "~/.local/share/watchers/books.log", "hours": 192,
         "level": "yellow"},
        {"name": "local feed server", "kind": "port", "port": 8001, "level": "yellow"},
    ],
}


def age_hours(path):
    return (NOW - datetime.datetime.fromtimestamp(os.path.getmtime(path))).total_seconds() / 3600


def check(c, red, yellow, green):
    bucket = red if c.get("level", "red") == "red" else yellow
    kind = c["kind"]
    try:
        if kind == "fresh":
            h = age_hours(os.path.expanduser(c["path"]))
            ok, why = h <= c["hours"], f"{h:.0f}h old (limit {c['hours']}h)"
        elif kind == "newest":
            files = sorted(glob.glob(os.path.expanduser(c["glob"])), key=os.path.getmtime)
            if not files:
                bucket.append(f"{c['name']}: no files match {c['glob']}")
                return
            h = age_hours(files[-1])
            ok, why = h <= c["hours"], f"newest {pathlib.Path(files[-1]).name} is {h:.0f}h old"
        elif kind == "port":
            with socket.create_connection(("127.0.0.1", c["port"]), timeout=3):
                ok, why = True, ""
        else:
            raise ValueError(f"unknown kind {kind}")
    except OSError as e:
        ok, why = False, f"cannot check ({e.__class__.__name__}: {e})"
    (green if ok else bucket).append(c["name"] if ok else f"{c['name']}: {why}")


def check_launchd(prefix, red, green):
    out = subprocess.run(["launchctl", "list"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        f = line.split()
        if len(f) != 3 or not f[2].startswith(prefix):
            continue
        pid, status, label = f
        name = label[len(prefix):]
        # exit 78 (EX_CONFIG) usually means the interpreter or working directory is gone,
        # e.g. after a Homebrew Python upgrade: suspect a shared cause when several appear.
        if status not in ("0", "-") and pid == "-":
            red.append(f"launchd `{name}` last exited {status}")
        else:
            green.append(name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    cfg = json.load(open(a.config)) if a.config else DEFAULT

    red, yellow, green = [], [], []
    check_launchd(cfg["launchd_prefix"], red, green)
    for c in cfg["contracts"]:
        check(c, red, yellow, green)

    status = {"checked_at": NOW.isoformat(timespec="minutes"), "red": red, "yellow": yellow, "green": len(green)}
    print(json.dumps(status, indent=1))
    if a.dry_run:
        return
    sf = pathlib.Path(os.path.expanduser(cfg["status_file"]))
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text(json.dumps(status, indent=1))
    if red:
        note = pathlib.Path(os.path.expanduser(cfg["inbox"])) / f"{NOW:%Y-%m-%d}-health-alert.md"
        if not note.exists():
            body = [f"---\ndate: {NOW:%Y-%m-%d}\ntype: note\ntags: [automation, health]\n---",
                    "# Automation health alert", "", "Red (broken, act):"] + [f"- {r}" for r in red]
            if yellow:
                body += ["", "Yellow (degraded):"] + [f"- {y}" for y in yellow]
            body += ["", f"*{len(green)} checks green.*"]
            note.write_text("\n".join(body) + "\n")


if __name__ == "__main__":
    main()
