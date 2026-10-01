# Reliability

| File | What it does |
|------|--------------|
| `health_sentinel.py` | Daily liveness check over a list of contracts (launchd exit codes, file freshness, newest output, local ports). Writes a JSON status and an inbox alert when something is red. |

Liveness only tells you a job ran. For the second check, whether it did anything, see [`docs/08-keeping-automations-honest.md`](../../docs/08-keeping-automations-honest.md).

Schedule it once a day with the plist template in `examples/watchers/`, before your morning briefing reads the status file.
