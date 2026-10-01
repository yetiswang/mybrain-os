# Keeping automations honest

A personal OS runs on jobs nobody watches: a nightly synthesis, an hourly log writer, a weekly watcher, a daily sweep. Over a few months I found that the dangerous failures were never the loud ones. A job that crashes leaves a traceback. The ones that cost weeks were jobs that ran, logged, exited 0, and did nothing.

This doc collects that lesson and the checks that came out of it.

## Two kinds of check

**Liveness**: did the job run? Its last exit code is 0, its log was written today, its output file is fresh. `examples/reliability/health_sentinel.py` does this once a day and drops an alert note in the inbox when something is red.

**Efficacy**: did the job do anything? Liveness cannot answer this. Every case below passed its liveness check for weeks.

The rule I now apply: **any job whose healthy output is "0 findings" needs an independent check that 0 is real.**

## Cases

**The stale-item flag that never fired (96 days).** A nightly job flagged dashboard items untouched for 30 days. It recognised items across runs by hashing each line with Python's built-in `hash()`, which is salted per process. Every run saw every item as new, nothing ever aged, and the log said "0 items flagged" every night while its state file grew by hundreds of dead entries a day. The liveness check (log younger than 26 hours) was green throughout. Fix: a stable hash (`sha1` of the text). Lesson: if state is keyed on a hash, make sure the hash survives a restart.

**The sweep that looked in the wrong place.** A daily step searched recent notes for open action items. The search roots were relative paths, errors went to `/dev/null`, and from any working directory except the vault the sweep returned 0 files. That is indistinguishable from "no new actions today". Measured once: relative paths found 0 files, absolute paths found 31. Fix: absolute paths, a check that each root exists, and the file count reported in every run. A zero on a working day is a red flag.

**The guard that measured a different window.** The daily email fetch got a plausibility guard: compare the harvest with Mail.app's own count. The guard counted 55 hours; the script fetched 7. It reported a shortfall every day and retried a fetch that was working correctly. A guard that cries wolf daily is worse than none, because you learn to ignore it. Fix: the fetch script prints the window it used, and the guard reads that number. One source of truth.

**Presence is not completeness.** Before the guard existed, the fetch was checked by looking for its section marker. A cold Mail.app once returned 1 of 18 messages with the marker present. Fix: compare against a ground-truth count, and retry below half.

**The failure that printed nothing.** A voice-memo step was told to "skip silently" when it found no memos or hit a permissions error. Both cases print nothing. Fix: read the exit code. Exit 0 with no results is an empty day; a non-zero exit is a coverage gap and goes in the report.

**The job that kept its own model.** The nightly synthesis agent pinned a provider and model per scheduled job. When the default provider changed, the interactive agent worked fine, so everything looked healthy, while the scheduled job kept calling a dead account and failed for eleven nights. Twice. Lesson: scheduled jobs often carry their own configuration. Check the job, not the default.

**One upgrade, three dead jobs.** A package-manager upgrade removed a Python minor version. Three launchd jobs pinned to that interpreter, or to a virtual environment built on it, failed at once with exit 78 (configuration error, before the process even starts). When several jobs fail together with the same code, suspect a shared cause.

**The backup that would have restored nothing.** For SQLite databases written live in WAL mode: copy with `sqlite3 .backup`, not `cp`, which can capture a torn page. Do not open the source read-only (`?mode=ro`): a WAL database that needs recovery opens with zero tables and no error. Verify every snapshot with `PRAGMA integrity_check` and a table count before you keep it, and refuse a 0-byte file. A backup job whose healthy output is "done" needs the same independent check as everything else.

## Patterns

- **Report the denominator.** "Swept 31 files, found 2 actions" can be checked. "Found 0 actions" cannot.
- **Size a guard from the job's own output.** Have the job state its window, scope or input count, and check against that.
- **Separate empty from blind.** Exit codes, existence checks on inputs, and an explicit "could not look" state that is never reported as a pass.
- **Keep a run log.** One append-only line per run, listing steps done and steps skipped with a reason. "Did step X run on day Y?" becomes a `grep`.
- **Liveness daily, efficacy by design.** The sentinel catches dead jobs within a day. Efficacy checks have to be built into each job, because only the job knows what "did something" means.

## Files

- [`examples/reliability/health_sentinel.py`](../examples/reliability/health_sentinel.py): the daily liveness check, driven by a list of contracts.
- [`examples/commands/5pmsummary.md`](../examples/commands/5pmsummary.md): the end-of-day ritual with the plausibility guard, the attachment reconciliation, absolute-path sweeps and the run log in place.
