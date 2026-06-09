# /5pmsummary — End-of-day summary

## Resume support

Before starting, check for existing state:

```bash
bash '<vault>/.claude/hooks/skill-state.sh' read 5pmsummary
```

If the output is not `{}`, a previous run was interrupted. Show the user which steps completed and ask: **"Resume from step N, or start fresh?"** If resuming, skip completed steps. If starting fresh or no state found, initialize:

```bash
bash '<vault>/.claude/hooks/skill-state.sh' init 5pmsummary 10
```

Your daily end-of-day ritual.

## Date discipline (READ FIRST)

Before parsing any date from email, calendar, or AppleScript output:

1. **Anchor on real time, not injected context.** Run `date "+%A %Y-%m-%d %H:%M %Z"` and use that as ground truth. Session-injected dates can be stale.
2. **Never resolve relative dates ("Wednesday", "tomorrow", "next week") without verifying weekday alignment.** If an email says "Wednesday Apr 30", verify: `date -j -f "%Y-%m-%d" "2026-04-30" "+%A"`. **If weekday and date don't match, STOP and ask the user which is right.**
3. **Calendar events: trust the local-time string from `fetch_calendar.swift`** (format: `Wed 2026-04-29 10:30 GMT+2`). The `Anchor:` line at the top of the output is authoritative for "now". Never reinterpret as UTC.
4. **When writing any date to Dashboard / meeting note / stakeholder log, include the weekday in your reasoning** so weekday-vs-date inconsistencies surface before the bad date propagates.

<!-- Adapt to your own context: this originated from a date-propagation bug caught in a specific run. The principle: always verify weekday/date alignment before writing to any vault file. -->

## Vault & paths

- Vault: `<vault>`
- Meetings: `20-Work/Meetings/` — filename: `YYYY-MM-DD-<slug>.md`
- Stakeholders: `20-Work/Stakeholders/` — filename: `Firstname-Lastname.md`
- Projects: `30-Projects/<MyProject>.md`
- Inbox: `00-Inbox/`

## Step 0 — Dynamic task list (NEW, mandatory)

After resume-state and date-discipline checks, **create a TaskCreate task list** representing every step of this run before doing any other work. The point: you see a live progress board, blockers are visible immediately, and skipped sub-steps cannot disappear silently.

Required tasks (one TaskCreate call per row, in order):

| Subject | Active form |
|---|---|
| Step 1: Fetch Calendar / Mail / Notes | Fetching raw data |
| Step 1b: Update email archive + completeness check | Updating email archive |
| Step 1c: Transcribe Voice Memos | Transcribing voice memos |
| Step 2: Parse and analyse | Parsing today's data |
| Step 2b: Process email attachments | Processing attachments |
| Step 3: Write meeting notes | Writing meeting notes |
| Step 4: Update stakeholder files | Updating stakeholder logs |
| Step 5: Update project log + Lab-Ops docs | Updating project log |
| Step 5c: Sweep recent docs for action items | Sweeping recent docs |
| Step 6: Update project memory files | Updating project memories |
| Step 6b: Update Dashboard + Lab-Ops-Dashboard | Updating Dashboard |
| Step 7: Tomorrow preview | Previewing tomorrow |
| Step 8: Rebuild vault indexes | Rebuilding indexes |
| Step 8c: Agentic activity recap | Recapping agentic work |
| Step 9: Write daily digest | Writing digest |
| Step 10: QA pass + completeness reconciliation | Running QA pass |

Mark each task `in_progress` when starting it and `completed` when finished. Use TaskUpdate, not TaskCreate, after the initial seeding.

If a step legitimately doesn't apply on a given day (e.g. Step 1c — no voice memos), mark it `completed` with a one-line note in the digest's QA section ("Step 1c — no voice memos found, skipped"). Never delete it.

## Step 1 — Fetch raw data

Launch Calendar, Mail, and Notes first (AppleScript fails if the app isn't running), then run both fetch scripts:

```bash
open -a Calendar && open -a Mail && open -a Notes && sleep 4 && \
cp ~/vault-infrastructure/scripts/fetch_day.applescript \
   /tmp/5pm_fetch.applescript && \
osascript /tmp/5pm_fetch.applescript
```

Then fetch sent emails separately:

```bash
cp ~/vault-infrastructure/scripts/fetch_sent.applescript \
   /tmp/5pm_sent.applescript && \
osascript /tmp/5pm_sent.applescript
```

**Note on the sent script:** it reads `Sent Items` in your work email account, iterates index-by-index from most recent, and stops when the date goes before the lookback window. Large mailboxes (10k+ messages): never use `every message of mb` iteration or `whose` filters — both hang. The script is already correct; just run it as-is.

**CRITICAL: never truncate the sent-fetch output via `head` / `tail` / Read-with-limit.** Each sent record is multi-line; truncating by line count silently drops the older half of the day. If the output is too large for context, persist it to disk (the harness already does this for `Output too large` cases) and read structured slices, or count `^---SENT---` markers and re-fetch by subject filter.

<!-- Adapt: filter the sent-script's `whose name contains` to match your own mail account name. -->

The inbox fetch output has four blocks: `===EMAILS===`, `===CALENDAR===`, `===NOTES===`, `===TOMORROW===`. Each item is separated by `---MSG---`, `---EVT---`, or `---NOTE---`. The sent fetch output has one block: `===SENT===`, with items separated by `---SENT---`.

**Critical:** always write AppleScript to a file, then run with `osascript <file>`. Never use shell heredocs — they fail in the exec environment.

## Step 1b — Update email archive + 48-hour catch-up

Run the fast email extraction to capture any new emails since the last run:

```bash
python3 -u <watcher-dir>/extract_email_archive.py --fast 2>&1 | tail -5
```

Idempotent, ~60-90 seconds. Keeps `email-archive.db` current for `/email-search` and `/email-story`.

After the extractor finishes, run a **48-hour catch-up query** to surface any substantive emails that arrived after the previous day's 5pm summary ran (e.g. late-evening replies, or emails from a day where the summary was skipped):

```bash
sqlite3 <watcher-dir>/email-archive.db \
  "SELECT date, sender_name, sender_email, subject, substr(body,1,300) FROM emails \
   WHERE date >= datetime('now','-48 hours') \
   AND sender_email NOT LIKE '%no-reply%' AND sender_email NOT LIKE '%noreply%' \
   AND sender_email NOT LIKE '%notification%' AND sender_email NOT LIKE '%alert%' \
   AND sender_email NOT LIKE '%mailer-daemon%' AND sender_email NOT LIKE '%<internal-system>@<institution-tld>%' \
   ORDER BY date ASC LIMIT 40;"
```

Compare against the last 2 daily digests (`00-Inbox/YYYY-MM-DD-5pm-summary.md` for today-1 and today-2). Any email thread not mentioned in either digest is a **catch-up email** — include it in Step 2's synthesis pass. Label it `[catch-up: YYYY-MM-DD]` in the digest so it is clear when it arrived.

### Step 1b.1 — Email-DB completeness check (NEW, mandatory)

Before moving on, verify the archive caught everything. Run two cross-checks and record the numbers in the QA section of today's digest.

**Check A — Today's sent count: Mail.app vs email-archive.db.** Mail.app's `Sent Items` is the ground truth for what you sent today. Count it via AppleScript and compare against the archive:

```bash
# Count sent today via Mail.app (ground truth)
cat > /tmp/sent_today_count.applescript << 'EOF'
tell application "Mail"
  set theAccount to first account whose name contains "<your-account-name>"
  set theMailbox to mailbox "Sent Items" of theAccount
  set today_start to current date
  set hours of today_start to 0
  set minutes of today_start to 0
  set seconds of today_start to 0
  set msgs to (every message of theMailbox whose date sent ≥ today_start)
  log (count of msgs)
end tell
EOF
MAIL_SENT_COUNT=$(osascript /tmp/sent_today_count.applescript 2>&1 | tail -1)

# Count sent today in archive
DB_SENT_COUNT=$(sqlite3 <watcher-dir>/email-archive.db \
  "SELECT COUNT(*) FROM emails WHERE mailbox = 'Sent Items' AND date >= date('now', 'localtime');")

echo "Mail.app sent today: $MAIL_SENT_COUNT | Archive sent today: $DB_SENT_COUNT"
```

If the two numbers diverge by more than 1, the archive is stale. Re-run the extractor and re-check before continuing. Record the final numbers in the QA section of the digest.

**Check B — Sent-mail enumeration vs digest coverage.** Pull the full list of subjects + recipients sent today and verify each substantive thread is reflected somewhere in the digest. **Do not truncate the listing via `head`** (see warning in Step 1).

```bash
osascript -e 'tell application "Mail"
  set theAccount to first account whose name contains "<your-account-name>"
  set theMailbox to mailbox "Sent Items" of theAccount
  set today_start to current date
  set hours of today_start to 0
  set minutes of today_start to 0
  set seconds of today_start to 0
  set msgs to (every message of theMailbox whose date sent ≥ today_start)
  repeat with m in msgs
    log (date sent of m as string) & " | TO:" & (extract address from (address of (to recipient 1 of m))) & " | SUBJ:" & (subject of m)
  end repeat
end tell' 2>&1
```

Output goes to a `/tmp/5pm_sent_today.txt` file. Cross-check this list against the digest's Emails section and the Dashboard `[ ]` items added today. Anything sent but missing from the digest is a coverage gap and must be patched before Step 10 closes.

**Check C — Inbox count today.** Same idea on the inbound side: Mail.app's count of received-today vs `mailbox = 'Inbox' AND date >= date('now', 'localtime')` in the archive. Mismatch by more than 2 suggests the archive needs a fresh pass.

**Check D — Year-to-date telemetry (calendar year).** Capture a running ledger of correspondence volume to surface trends. Run once per `/5pmsummary` and write the numbers into the QA section:

```bash
sqlite3 <watcher-dir>/email-archive.db "
SELECT 'Sent YTD' AS label, COUNT(*) FROM emails WHERE mailbox = 'Sent Items' AND date >= date('now', 'localtime', 'start of year')
UNION ALL
SELECT 'Inbox YTD', COUNT(*) FROM emails WHERE mailbox = 'Inbox' AND date >= date('now', 'localtime', 'start of year');"
```

Record both numbers and the Sent : Inbox ratio in the QA section's "Email-DB telemetry (year-to-date)" block. Useful as a long-term signal of correspondence load and reply discipline.

These four checks (today-sent match, today-inbox match, sent enumeration cross-check, YTD telemetry) are printed in Step 9's QA section in the digest. They are not optional.

## Step 1c — Transcribe Voice Memos

Check for any Voice Memos recorded today and transcribe them:

```bash
python3.13 <watcher-dir>/transcribe_memos.py --days 1 2>&1
```

If the script returns results, treat each transcript as additional context for Steps 2–5:
- Work content feeds into the same synthesis pass as emails and meetings
- Life content (personal reflections, family, feelings) → append to today's diary entry at `40-Life/Hypomnemata/YYYY-MM-DD.md`
- Save each full transcript to `00-Inbox/YYYY-MM-DD-voice-memo-<slug>.md`
- Add a `## Voice Memos` section to the daily digest (after Meetings) listing: memo name, duration hint (from transcript length), and a 1–2 sentence summary

If no memos found or script fails with permissions error, skip silently. Note in digest only if memos were processed.

## Step 2 — Parse and analyse

From the raw output:

- **Emails** (`===EMAILS===`): extract sender, subject, date, body snippet. Identify: action items, stakeholder names, project references (<MyProject>, <my-institute>, <funder-programme>, and your domain-specific keywords).
- **Sent emails** (`===SENT===`): extract recipient, subject, date, body snippet. For each substantive reply, note: who you replied to, what was said, what decision or tone the reply reflects. This gives the full conversation picture — not just what arrived but what was done about it.
- **Calendar events**: extract title, time, attendees. Match to Apple Notes by event title similarity.
- **Apple Notes**: strip HTML from body (treat `<div>` as paragraph breaks, strip all tags). Parse `#meeting <Name>` convention to extract stakeholder name.

## Step 2b — Process email attachments

The fetch script saves document attachments (PDF, DOCX, XLSX, PPTX, TXT, CSV, MD) to `/tmp/5pm-attachments/` and logs filenames in the `Attachments:` line of each email.

For each email with attachments:

1. **Save to vault:** Copy substantive files (skip signature images) to `20-Work/Email-Attachments/YYYY-MM-DD-<topic-slug>/`, one folder per email thread
2. **Convert DOCX/DOC to markdown** using `textutil -convert txt` so they are readable in Obsidian. Keep originals for fidelity.
3. **Read and parse** all documents using the appropriate tool (Read for PDF/TXT/MD, markitdown or dedicated skill for DOCX/PPTX/XLSX)
4. **Write a `Synthesis.md`** inside the attachment folder: what is happening, documents parsed (table), key intelligence (cross-referenced with projects/stakeholders), strategic opportunities, actions with deadlines, stakeholder connections, timeline
5. **Surface in the digest:** Add a `## Attachments` section (after Emails) with flag level, summary, key intelligence, strategic relevance, and all action items. Action items from attachments must also appear in the digest's `## Actions identified today` section.
6. **Clean up:** `rm -rf /tmp/5pm-attachments/`

See the canonical SKILL.md for the full Synthesis.md template and digest format.

## Step 3 — Write meeting notes to vault

For each `#meeting` note matched to a calendar event:

1. Check if a file exists at `20-Work/Meetings/YYYY-MM-DD-<slug>.md`.
2. If yes and `## Notes` is empty, fill it in. If it already has content, append after a `---` separator.
3. If no file exists, create one.

**Meeting note frontmatter:**
```yaml
---
type: meeting
date: YYYY-MM-DD
title: <meeting title>
people: ["[[Firstname-Lastname]]"]
org: [<my-institute>, <my-institution>]
project: [<MyProject>]
topic: []
tags: [meeting]
source: apple-notes
---
```

Write `## Notes` in the vault owner's style: prose not bullets, no dashes, parentheses for asides, direct and warm. Write `## Actions` as `- [ ]` checkboxes.

## Step 4 — Update stakeholder files

For each person identified in today's notes, emails, or calendar attendees:

### 4a — Check for existing file
List `20-Work/Stakeholders/`. Fuzzy-match on first or last name. Filenames use hyphen-case ASCII (e.g. `Firstname-Lastname.md`).

### 4b — New stakeholder: create placeholder
```markdown
---
name: Firstname Lastname
type: person
org: <inferred or "Unknown">
role: <inferred or "Unknown">
relationship: <internal | external | partner>
tags: [stakeholder]
---

## Context
<1–2 sentences inferred from today's context. Mark as inferred if not confirmed.>

## Notes
- First encountered: YYYY-MM-DD

## Context Log
- **YYYY-MM-DD** — <summary of first interaction>
```

### 4c — Existing stakeholder: append to Context Log
Add a dated bullet: `- **YYYY-MM-DD** — <1–2 sentence summary of interaction and outcome>`

## Step 5 — Update project log

In `30-Projects/<MyProject>.md`, append a row to the `## Change Log` table:
`| YYYY-MM-DD | <concise description of what happened or was decided today> |`

For other active projects mentioned, do the same in their respective files.

## Step 5b — Update Lab Operations docs

If today's emails contained equipment, vendor, procurement, maintenance, or finance activity, update the relevant docs in `30-Projects/Lab-Operations/`:

- **Service-Maintenance-Log.md** — new issues, resolution updates, scheduled maintenance changes
- **Procurement-History.md** — new POs, invoice status changes, payment confirmations
- **Equipment-Registry.md** — instrument status changes, new installations
- **Vendor-Map.md** — new vendor contacts, relationship changes
- **Finance-Tracker.md** — PO status changes, reimbursement updates, budget figure corrections. Trigger keywords: finance contacts, budget codes, invoice, PO, reimbursement.

<!-- Adapt: replace with your own finance contact names and cost centre codes. -->

Skip this step entirely if no lab ops activity was detected today.

## Step 5c — Sweep recent docs for action items

Beyond emails/meetings/voice memos (already covered in earlier steps), the vault owner authors action items directly in strategy docs, inbox notes, project notes, lab-ops docs, and stakeholder context logs. This step catches them.

### 5c.1 — Find the cutoff
The cutoff is the most recent prior 5pm summary file:

```bash
LAST_SUMMARY=$(ls -t "<vault>/00-Inbox/"*-5pm-summary.md 2>/dev/null | head -1)
```

If none exists, use 7 days ago. Use the file's mtime as the cutoff for `find -newer`.

### 5c.2 — Sweep these folders for `.md` files modified since cutoff

```bash
find "20-Work/Strategy" "20-Work/Meetings" "30-Projects" "20-Work/Stakeholders" "20-Work/External-People" \
  -name "*.md" -newer "$LAST_SUMMARY" 2>/dev/null
find "00-Inbox" -name "*.md" -newer "$LAST_SUMMARY" 2>/dev/null | grep -v "5pm-summary"
```

`30-Projects/Lab-Operations/` is included — the user authors todos directly in `Service-Maintenance-Log.md`, `Procurement-History.md`, `Finance-Tracker.md`, `Lab-Ops-Dashboard.md`, etc.

### 5c.3 — Extract unchecked items
For each modified file, grep for lines matching `^- \[ \]` (unchecked). For each match:

1. Capture full line text minus the `- [ ]` prefix.
2. Note the source filename (without `.md`) for wikilink suffix.

### 5c.4 — Deduplicate against existing Dashboard
For each candidate item:

1. **Normalize** both candidate and every existing Dashboard item (`[ ]` AND `[x]`):
   - Lowercase
   - Strip `[[wikilinks]]` → `wikilinks`
   - Remove markdown bold/italic
   - Drop filler tokens: `the`, `a`, `an`, `to`, `with`, `for`, `on`, `in`, `at`
   - Tokenize on whitespace
2. **Compare** candidate token-set to each existing item token-set using **Jaccard similarity** (intersection / union). If max similarity > 0.5, skip the candidate.
3. Bias: high-signal entity tokens (capitalized words, person and project names) carry double weight in the similarity calc. Two items mentioning the same person name and topic with different filler are duplicates.

### 5c.5 — Categorize new items
Map source folder → Dashboard category:

| Source | Dashboard category |
|--------|-------------------|
| `20-Work/Strategy/` | <MyProject> — Strategic |
| `20-Work/Meetings/` | by meeting topic/attendees: <MyProject>, Partnerships, or Lab-Ops |
| `00-Inbox/` | <MyProject> — Strategic (default) or content-keyword override |
| `30-Projects/Lab-Operations/` | Lab Operations |
| `30-Projects/<MyProject>.md` | <MyProject> — Strategic |
| `30-Projects/<other>` | <MyProject> — Strategic (default) |
| `20-Work/Stakeholders/` or `External-People/` | Partnerships |

### 5c.6 — Within-category themed subtitle placement
Each Dashboard category callout uses **bold-line themed subtitles** to group related items (see Step 6b). For each new item:

1. **Match against existing themed subtitles** in the target category by entity overlap (e.g., item mentions a stakeholder name → find the subtitle for their workstream; mentions a project partner → find the relevant partnership subtitle).
2. If no match, derive a new subtitle from the source doc's title (e.g., strategy doc `ProjectA-PartnerB-Bridge.md` → subtitle "Project A–Partner B bridge").
3. Items without an obvious theme go under "**General**" subtitle.

### 5c.7 — Format with source wikilink
Every new item written to Dashboard:

```
- [ ] <action text> — [[source-note-name]]
```

Where `source-note-name` is the source filename without `.md` extension. If the action item is highly specific to a strategy doc, link the strategy doc; if it came from a meeting, link the meeting note.

### 5c.8 — Output for Step 6b
This step does not write to Dashboard directly. It produces a structured list of `(item_text, themed_subtitle, target_category, source_wikilink)` tuples for Step 6b to merge.

## Step 6 — Update project memory files

Review all project-type memory files in `~/.claude/projects/<project-memory-dir>/memory/` (files starting with `project_`).

<!-- Adapt: replace the path above with your own Claude Code project memory directory. -->

For each project memory file:
1. Read the current content.
2. Check whether today's emails, meetings, or calendar events contain new information that affects the memory (e.g., timeline changes, new risks, resolved decisions, stakeholder shifts).
3. If yes, update the memory file using the Edit tool — revise the content, update the **Why:** and **How to apply:** sections, and adjust the description in the frontmatter if needed.
4. If a project memory is now stale or resolved (the situation it describes no longer applies), remove it and update `MEMORY.md`.
5. If today's intel reveals a significant new project development not covered by any existing memory, create a new `project_*.md` file and add it to `MEMORY.md`.

Only update when there is substantive new information — do not touch memory files just to confirm they are still correct.

## Step 6b — Update Dashboard

Open `Dashboard.md` and reconcile against (a) today's emails/meetings/voice/attachments, (b) Step 5c's recent-docs sweep output.

### 6b.0 — Source of truth principle
Dashboard is the single source of truth for open actions. Source documents (strategy docs, meeting notes, etc.) may also have `- [ ]` items. The two are linked via the `— [[source]]` wikilink suffix. When marking an item `[x]` in Dashboard, also mark `[x]` in the source doc if present (one-way back-sync). When pruning Dashboard, never delete from sources.

### 6b.1 — Mark items done
Mark `[x]` when today's evidence confirms completion. Sources of evidence:
1. **Manual `[x]`** by the vault owner during the day — already done, no action needed.
2. **Email evidence** — sent email confirms an action was completed; inbound email confirms a request was fulfilled. Mark `[x]` and append a brief evidence note: `[x] Action — [[source]] (done YYYY-MM-DD: sent reply to <Person>)`.
3. **Meeting outcome** — meeting note records "decided X" or "completed Y". Mark `[x]`.

For every `[x]` newly marked here: if the original item has a `— [[source]]` suffix, open the source doc and mark the matching item `[x]` there too. Find by Jaccard similarity > 0.7. This keeps source docs in sync.

### 6b.2 — Themed subtitle structure
Each category callout uses **bold-line themed subtitles** to group related items. Pattern:

```markdown
> [!project] <MyProject> — Strategic
> *Next milestone: ...*
>
> **<Theme A>** *(optional context note)*
> - [ ] item one — [[source]]
> - [ ] item two — [[source]]
>
> **<Theme B>**
> - [ ] item three — [[source]]
> ...
```

**Themes are content-driven, not chronological.** Examples:
- <MyProject>: "PI bridge meetings", "Post strategy meeting YYYY-MM-DD", "Partnership workstream", "General <funder-programme> positioning"
- Lab Operations: "Vendor follow-ups", "Equipment quotes", "Maintenance", "Finance"
- Partnerships: "Active threads", "Awaiting response", "New intros to make"

### 6b.3 — Add new actions
Merge two streams into the categorized callouts:

1. **From today's digest** (emails, meetings, attachments, voice memos) — items in the digest's `## Actions identified today` block.
2. **From Step 5c sweep** — already categorized + themed.

For each new item:
- Run the same dedup check (Jaccard > 0.5 against any existing Dashboard item, both `[ ]` and `[x]`). Skip duplicates.
- Place under the matched themed subtitle. If theme doesn't exist in the target category, add it.
- Format: `- [ ] <action> — [[source]]`. Source for emails: the email-attachment folder if available, else no wikilink (just `(source: email)`). Source for meetings: the meeting note. Source for strategy/inbox/project: the source doc.

### 6b.4 — Empty-subtitle pruning
After all `[x]` items have been moved to "Recently completed" (Step 6b.6 below), scan each category callout. Any **bold-line themed subtitle** with no remaining `- [ ]` items beneath it gets removed entirely (subtitle line + blank line). This keeps subtitles fresh.

### 6b.5 — Add upcoming meetings
For tomorrow's calendar events that need prep, add to "This Week" highlights with `— [[meeting-note-name]]` suffix.

### 6b.6 — Project-based pruning
For each open item, identify its project context and apply the matching rule:

### Pruning rules by project context

Read `98-Context/Projects-Overview.md` for current milestones and rhythms.

**<MyProject>** (milestone-driven):
- Evaluate items against the *current milestone* listed in Projects-Overview, not calendar age.
- After a milestone event (strategy meeting, EB meeting, submission): sweep items that were prep for it — mark done if addressed, retire with `[retired — superseded by YYYY-MM-DD meeting]` if overtaken.
- Strategic positioning items (dean outreach, funder engagement, consortium) carry forward to the next milestone automatically.

**Lab Operations** (ticket-based):
- Vendor-dependent items stay open as long as the ticket/thread is alive — check today's emails for resolution.
- Internal items (task trackers, budgets, access) with no email activity in 14 days: flag with `⏰ no activity since [date]`.
- Equipment decisions with quote expiry: keep the hard deadline visible.

**<peer-network>** (slow burn):
- Quarterly rhythm. Almost nothing to prune. Only retire if direction changes.

**Time-bound deliverables** (newsletter, video, plan — ship-or-miss):
- Past deadline: check if it shipped (sent emails, evidence). If yes → mark `[x]`. If no and window closed → retire with `[retired — deadline passed]`. If no but still actionable → move to next available date.

**External partnerships** (relationship-driven):
- Never silently retire a person follow-up. Check sent emails first. If you replied → mark done. If no reply and >21 days → flag but keep (burning bridges has real cost).

**Administrative** (file sync, forms, system access — one-shot):
- >14 days overdue with no activity → retire with `[retired — overtaken]`.

### Completed items cleanup (universal)

- `[x]` items in the main action sections → move to "Recently completed" (keep the completion date/note).
- `[x]` items in "Recently completed" older than 14 days → delete entirely.

### <MyProject>.md sweep (after milestone events)

After a milestone event, also update `30-Projects/<MyProject>.md`:
- Remove `[x]` items from Next Actions and Open Decisions (they're in the change log).
- Update "Status at a Glance" — phase, next milestone, risk.
- Change log entries older than 60 days → condense into one summary line per month; archive full text to `90-Archive/<MyProject>-changelog/YYYY-MM.md`.

The Dashboard is the single source of truth for open actions.

### Lab-Ops-Dashboard.md update

Also open `30-Projects/Lab-Operations/Lab-Ops-Dashboard.md` and update:

1. **To-Do sections** (Urgent / In Progress / Finance / Upcoming):
   - Mark items `[x]` when today's emails confirm completion.
   - Add new lab ops actions from today's emails (equipment issues, vendor follow-ups, procurement tasks, maintenance items).
   - Apply ticket-based pruning: vendor items stay while thread is alive; internal items with no activity in 14 days get `⏰ no activity since [date]`; quote expiry dates stay visible.
   - Move completed items out of To-Do sections.

2. **Stats row** — update Active POs count, Not Invoiced amount, and Instruments count if finance or equipment emails were processed today.

3. **Active Issues table** — add new issues, update status of existing ones, remove resolved issues.

4. **Budget Health / Contract Status tables** — update if financial emails (finance contacts, invoices, PO changes) were processed.

5. **Sync with main Dashboard** — the main Dashboard's Lab Operations section should contain only the most critical lab ops items (max 5-6) with a link to the full Lab-Ops-Dashboard. Keep them in sync: if an item is marked done on either dashboard, mark it on both.

## Step 7 — Tomorrow's meetings preview

The `===TOMORROW===` block contains the next day's calendar events. For any meeting with known attendees who are stakeholders, note them by wikilink. Flag any meetings that need prep (strategic meetings, external stakeholders, senior contacts).

## Step 8 — Rebuild vault indexes

Regenerate both index files to reflect today's changes:

### 8a — Meetings INDEX.md

Read all `.md` files in `20-Work/Meetings/` (excluding `INDEX.md`). For each file, extract frontmatter: `date`, `title`, `people`. Build a markdown table grouped by month (reverse chronological). Each meeting row: `| date | [[filename|title]] | people |`. Write to `20-Work/Meetings/INDEX.md` with frontmatter `type: index`, `auto_maintained: true`, `last_rebuilt: YYYY-MM-DD`.

### 8b — Stakeholders INDEX.md

Read all `.md` files in `20-Work/Stakeholders/` (excluding `INDEX.md`). For each file, extract frontmatter: `name`, `org`, `relationship`. Find the most recent `**YYYY-MM-DD**` pattern in the file body as last contact date. Build a markdown table sorted by last contact (most recent first). Add a "Stale (30+ days)" section and a "No Context Log" section. Write to `20-Work/Stakeholders/INDEX.md` with frontmatter `type: index`, `auto_maintained: true`, `last_rebuilt: YYYY-MM-DD`.

## Step 8c — Agentic activity recap

Review what Claude did today across all sessions. Sources:

1. **`98-Context/Agentic-Log.md`** — read all session blocks dated today (primary source, written by `/sexit`)
2. **`10-Research/wiki/log.md`** — check for today's date (`YYYY-MM-DD`) entries (paper ingests, radar runs, concept creation, landscape scans)
3. **`10-Research/wiki/index.md`** — read current wiki totals (papers, concepts, groups)
4. **`98-Context/Current-State.md`** — cross-check `## In flight` and `## Recent decisions` for any agentic work not captured above

Compile a concise recap of agentic work: wiki building (papers ingested, concepts created, groups added), research sessions (web research, landscape scans, technology analysis), infrastructure changes (scripts updated, new skills, backup runs), and any other Claude-assisted work completed today.

This recap goes into the daily digest as a `## Agentic Activity` section (after `## Emails`, before `## Actions identified today`).

## Step 9 — Write daily digest to Inbox

Create `00-Inbox/YYYY-MM-DD-5pm-summary.md` using the **unified format below**. Section headings are a **fixed checklist** — required sections always appear (write `✓ none today` if empty), conditional sections (Attachments, Voice Memos) skip the section entirely if N/A, and the title format never deviates.

**Title format:** `# 5pm Summary — Wkd YYYY-MM-DD` (always with weekday abbreviation: Mon/Tue/Wed/Thu/Fri/Sat/Sun).

**Frontmatter:** include `weekday:` field for downstream Dataview queries.

### Inline-formatting rules (mandatory)

These rules came out of the 2026-05-09 audit comparing May 6/7 (good) vs May 8 first-pass (drift). Apply them in every digest.

**Meetings — bullet style.** One bullet per meeting. Format:
```
- **HH:MM–HH:MM Title** (location, optional attendees as wikilinks). One-to-three sentence outcome with [[wikilinks]] for every named person/doc that has a vault file. See [[meeting-note]].
```
Bold leads with the time range and title; location and outcome stay tight; trailing wikilink to the meeting note. Avoid bold-paragraph blocks — the eye loses scannability.

**Emails — bulleted, categorized, italic-subject.** Group emails under bold-line subtitles matching Dashboard categories. Within each bucket, one bullet per thread:
```
- *Subject (HH:MM):* one-line outcome with [[wikilinks]] for every named person + doc.
```
For long threads with multi-step exchange, append the timestamp range: `(HH:MM → HH:MM)`. Italic for subject, bold inside the line for the headline result if it deserves emphasis. Plain text only for people who don't have a vault file.

**Email category subtitles** (use Dashboard category names verbatim):
- `**<MyProject> — Strategic:**`
- `**<peer-network>:**`
- `**Lab Operations:**`
- `**Partnerships / Outreach:**`
- `**Administrative / FYI:**`

If a category has no traffic on a given day, skip its subtitle. If a thread spans two categories, place under the more strategic one.

**Wikilink discipline.**
1. **Every named collaborator who has a stakeholder file** → `[[Firstname-Lastname]]`. Match the filename exactly (hyphen-case ASCII, e.g. `[[Firstname-Lastname]]`). Check `20-Work/Stakeholders/` and `20-Work/External-People/` before deciding.
2. **People with no vault file** → plain text. Do not create redlinks. If they reappear several times, that's a signal to create a stakeholder file in Step 4.
3. **Vault docs** (meeting notes, strategy docs, project files, attachment-folder Synthesis docs) → `[[doc-stem]]`.
4. **External entities and orgs** (vendors, companies, suppliers) → plain text unless they have a dedicated vault note.
5. **Audit at end of digest:** in the QA pass section, count any plain-text named-person mentions and decide whether each deserves a stakeholder file before the next run.

**Length per item.** Aim for one line, ~25 words for routine items. Allow 2–3 sentences for items that genuinely changed something today (a strategic email, a meeting with a decision, a recurring lab-ops issue with new diagnosis). Routine threads get one line, no exceptions.

**Timestamp discipline.** Every email line carries `(HH:MM)` or `(HH:MM → HH:MM)` for multi-step threads. Recovery aid + chronological signal.

<!-- Adapt: this originated from a formatting audit comparing good digests against a drifted one. The principle: use bullet-style + categorized-subtitle throughout; missing wikilinks for known stakeholders are a common drift failure mode. -->

```markdown
---
type: daily-summary
date: YYYY-MM-DD
weekday: Friday
tags: [daily-review]
---

# 5pm Summary — Fri YYYY-MM-DD

## Headlines
[Required. 2–3 punchy lines on what landed today and the lede.]

---

## Meetings
[Required. 1–2 sentences per meeting: who, what, key outcomes. "✓ none today" if no meetings.]

## Emails
[Required. Conversation-level threads — for each thread: who initiated, what arrived, what you replied, what's left open. "✓ no substantive traffic" if quiet.]

## Attachments
[Conditional — skip the section entirely if no attachments processed today. When present: flag level, summary, key intelligence, action items.]

## Voice Memos
[Conditional — skip if no memos. When present: name, duration hint, 1–2 sentence summary.]

## Agentic Activity
[Required. What Claude did across sessions today, grouped: wiki building (papers/concepts/groups counts), research (web/landscape/technology), infrastructure (scripts/skills/backups), other. "✓ none" if quiet.]

---

## Actions identified today
- [ ] <action> — per <Person> (source: meeting/email)
[Required. List as `- [ ]` checkboxes. "✓ none" if no new actions.]

## Stakeholders touched
[Required. One-liner per person with context. "✓ none" if quiet.]

## Tomorrow (Wkd YYYY-MM-DD)
[Required. Calendar events with attendees (wikilinks for known stakeholders) and prep flags. Heading must include the weekday and date of the next day, e.g. "Tomorrow (Sat 2026-05-09)".]

---

## QA pass

**Email-DB completeness (today):**
- Mail.app sent today: N | Archive sent today: N (✓ match / ⚠ mismatch + recovery action)
- Mail.app inbox today: N | Archive inbox today: N (✓ match / ⚠ mismatch + recovery action)
- Sent-mail enumeration listed at `/tmp/5pm_sent_today.txt`; every substantive thread cross-checked against this digest's Emails section.

**Email-DB telemetry (year-to-date):**
- Sent YTD (current calendar year): N
- Inbox YTD (current calendar year): N
- Sent : Inbox ratio: N.NN

**Action reconciliation:**
- New Dashboard `[ ]` items added today: N. Each cross-checked against today's sent-email list. Items already complete via sent emails: M (corrected to `[x]` with evidence note).
- **Existing-Dashboard sweep:** for every `- [ ]` item already in Dashboard.md (not just today's adds), grep `/tmp/5pm_sent_today.txt` for evidence of completion. Mark `[x]` with date + recipient. A common failure: items that were actioned via sent email the same day but not yet marked done.
- **Source-doc back-sync (mandatory):** for every Dashboard `[x]` mark made today, locate the source doc via the `— [[source]]` wikilink suffix and mark the matching item `[x]` there too (Jaccard > 0.7). Common sources: project-folder action lists (`30-Projects/Lab-Operations/Service-Maintenance-Log.md`), strategy docs (`20-Work/Strategy/*.md`), stakeholder context logs.
- **Duplicate detection:** before closing the QA pass, grep Dashboard for repeated action stems (e.g. two rows about the same topic). If found, keep the canonical one (typically the most recent themed-subtitle placement) and remove the older row entirely. Don't leave dead "(Duplicate of...)" markers.
- **Reply-watch (mandatory):** for every strategically important sent email in the last 14 days (you flagged it, or it was sent to a senior funder / institute leadership / dean / external-partner recipient), check the email-archive for a reply. If none, open or update a `## Reply-watch` row on Dashboard with two trigger dates (soft bump = +7 days post-send, hard bump = +14 days, escalation route named). *Sent emails are not finished until they reply or you decide to stop waiting.*

**Coverage gaps (if any):**
- (List anything sent or received that isn't in the Emails section above; patch before closing.)

**Tooling notes:**
- (Anything broken, deferred, or unusual about today's run. Examples: index rebuild deferred; calendar fetch path failed; sent-mail head-truncation incident; voice memos permissions error.)

**Steps marked completed but skipped (legitimate):**
- (E.g. "Step 1c — no voice memos found, skipped"; "Step 8 indexes — deferred to weekly run".)
```

Write in the vault owner's voice: concise, no bullet overload, prose-first, parentheses for asides. The **QA pass section is mandatory** and must appear at the end of every digest. If a QA check passed cleanly with nothing to flag, write "✓ pass" and move on; never delete the heading.

## Step 10 — QA pass

Run after the digest is written, before clearing state. Fix any issues found.

| Check | What to do |
|-------|-----------|
| **Email coverage** | Count substantive emails (inbox + sent). Verify each is covered in digest. Flag misses. |
| **Action reconciliation** | For every new `- [ ]` in Dashboard: check sent emails — if you already replied, mark `[x]`. Verify every digest action also appears in Dashboard. Check sent emails for commitments not yet tracked. |
| **Attachment completeness** | For each `Attachments:` line: verify file saved, markdown conversion exists (DOCX), Synthesis.md exists, surfaced in digest. Capture scope: strategic OR work-relevant (newsletters, reports, meeting prep). |
| **Stakeholder placement** | For any file created/updated today: check org field. People outside your institution → belong in `External-People/`, not `Stakeholders/`. Verify context logs added for all people substantively engaged. |
| **Calendar completeness** | Every calendar event accounted for in digest. Every `#meeting`/`#talk` note matched and written. Frontmatter complete. |
| **Sent email coverage** | Every substantive sent email reflected in digest. Commitments tracked as Dashboard actions. New contacts → stakeholder/external-people file created. |
| **Deduplication** | Compare against the **last 2 daily digests**. Don't re-report threads already covered. Catch-up emails (`[catch-up: YYYY-MM-DD]`) from prior days should be reported even if "late" — they were missed previously. |
| **Wikilink integrity** | New wikilinks today → verify target file exists. Especially after file moves. |
| **Retired items** | Retired items have clear reason tags. No silent deletions. |
| **Pre-archive stranded actions** | Before any inbox file >14d is archived to `90-Archive/Inbox/`: scan for unchecked `- [ ]` items. If any exist, do NOT auto-archive. List them in a "Stranded actions" section in the digest with the source filename. The user must decide: act on them, move to Dashboard, or explicitly retire. Stranded items block archiving. |
| **Source-doc back-sync** | For every Dashboard item newly marked `[x]` today: if the item has a `— [[source]]` wikilink, open the source doc and mark the matching item `[x]` there too (Jaccard > 0.7 match). Prevents re-add loops. |
| **Themed subtitle health** | Each category callout: empty themed subtitles (no `- [ ]` items beneath) get removed. Subtitles with all `[x]` items get removed (the `[x]` items go to Recently completed). |

**The QA pass MUST be written into the digest's `## QA pass` section** (not just printed in the chat). Use the structure defined in Step 9. After the QA section is written, fix any issues the checks surfaced (correct stale Dashboard items, patch missed emails into the Emails section, escalate stranded actions), then clear state. The QA section is the audit trail; without it, the run did not happen as a QA-d run.

The action-reconciliation check is non-negotiable: for every `- [ ]` Dashboard item added today, grep `/tmp/5pm_sent_today.txt` for evidence of completion before leaving the run. Skipping this step is the most common source of stale open items on Dashboard.

## Rules

- Never overwrite existing `## Notes` content in meeting files — append after `---` if content exists.
- Mark Dashboard action items `[x]` when today's evidence confirms they are done.
- If no `#meeting` notes are found today, skip Steps 3–4 and note it in the digest.
- Email body is truncated at 2000 chars in the fetch script (raised from 1000 to handle forwarded emails). Forwarding headers are stripped before truncation.
- Email attachments (PDF, DOCX, XLSX, PPTX, TXT, CSV, MD) are saved to `/tmp/5pm-attachments/` and logged in the `Attachments:` line. Process them in Step 2b.
- Stakeholder cross-reference: see `20-Work/Stakeholders/INDEX.md` for known people.
- Project context: see `30-Projects/<MyProject>.md` and `98-Context/Current-State.md`.

## Checkpointing

After completing each step, record progress:

```bash
bash '<vault>/.claude/hooks/skill-state.sh' step 5pmsummary <STEP_NUMBER>
```

After Step 10 (final), clear state:

```bash
bash '<vault>/.claude/hooks/skill-state.sh' clear 5pmsummary
```
