# /goodmorning — Morning briefing

Your daily morning ritual.

## Vault & paths

- Vault: `<vault>`
- Dashboard: `Dashboard.md` (vault root — full path: `<vault>/Dashboard.md`)
- Projects: `30-Projects/<MyProject>.md`
- Stakeholders: `20-Work/Stakeholders/` — filename: `Firstname-Lastname.md`
- Meetings: `20-Work/Meetings/` — for cross-referencing existing meeting notes

## Step 1 — Fetch today's calendar

Run the Swift EventKit fetcher twice — once for today, once for tomorrow:

```bash
swift <watcher-dir>/scripts/fetch_calendar.swift today
```

```bash
swift <watcher-dir>/scripts/fetch_calendar.swift tomorrow
```

Run both commands and capture the output.

**Today output** starts with `===CALENDAR===`. **Tomorrow output** starts with `===TOMORROW===`. Events are preceded by `---EVT---`.

Each event has fields on separate lines:
- `Calendar: <name>` (calendar name, e.g. "Work", "Personal")
- `Summary: <title>` (event title)
- `Start: <datetime>`
- `End: <datetime>` (today events only)
- `Location: <location>` (may be empty)
- `Attendees: <Name1> <email1>; <Name2> <email2>` (semicolon-separated; may be empty)

Parse: Summary → meeting title, Start → time, Location → location, Attendees → attendee names (extract the name part before `<`).

Note: TOMORROW events include only Calendar, Summary, Start, Location, and Attendees — no End field.

## Step 2 — Read vault data

Read these files in parallel:

1. `<vault>/Dashboard.md` — extract all open `- [ ]` items (not checked `[x]`). Group by section heading.
2. `<vault>/30-Projects/<MyProject>.md` — extract: Status at a Glance table, Open Decisions (`- [ ]` only), Next Actions — Urgent, and any `⚠` risk lines.

## Step 3 — Look up stakeholder context for each meeting

For each attendee name found in today's calendar events:

1. Fuzzy-match the name against files in `20-Work/Stakeholders/`. Use first or last name. Filenames are hyphen-case ASCII (e.g. `Firstname-Lastname.md`).
2. If a file exists, read the `## Context` section (first 2–3 sentences) and the most recent `## Context Log` entry (last dated bullet).
3. If no file exists, note "no vault record".

Also check `20-Work/Meetings/` for any existing meeting note for today (file starting with today's date) — if found, note that a file already exists.

## Step 4 — Present morning briefing

Output the briefing in this order:

---

### Good morning — YYYY-MM-DD

#### Meetings today

**If no events today:** output `No meetings today.` and skip the Apple Notes offer entirely (jump straight to Priority actions).

**If events exist** (sorted by start time):
- **HH:MM — [Title]** · [Location if any]
  - Attendees: [names as wikilinks if in vault, plain text if not]
  - Context: [1 sentence per known attendee from their Context file]
  - Existing note: yes `[[YYYY-MM-DD-slug]]` / no

#### Priority actions

Show the top open `- [ ]` items from Dashboard.md, grouped by section. Limit to the first 3 sections with open items, max 5 items per section. Add a line at the end: "X more open items not shown" — count of open `- [ ]` items in Dashboard.md beyond what is displayed above (i.e., items in sections 4+ or beyond the 5-item cap per section).

Highlight with ⚠ any action flagged as urgent in <MyProject>.md.

#### Project progress & key risks

From `30-Projects/<MyProject>.md`:
- **Phase:** [value from Status at a Glance]
- **Next milestone:** [value from Status at a Glance]
- **Open decisions:** [count] open, listing each `- [ ]` item in one line
- **Key risks:** any line containing ⚠ or "risk" in the Status table or Open Decisions

Write this in prose, 3–5 sentences max. Not a full list dump — synthesise the strategic picture.

---

## Step 5 — Offer Apple Notes pre-population

After the briefing, ask:

> "Shall I pre-populate Apple Notes for today's meetings? Here's what I'd create:"

For each meeting today, show a one-line preview:

```
[Title] — YYYY-MM-DD HH:MM
[Name]: [1-sentence context] | [Name]: [1-sentence context]
```

Wait for the user's response before proceeding.

## Step 6 — Create Apple Notes (on confirmation)

If the user confirms with any affirmative response ("yes", "sure", "ok", "go ahead", "do it", etc.):

Each note is minimal — just a title and short stakeholder context. The vault owner fills in their own notes during the meeting. The `/5pmsummary` skill picks up these notes later and formats them into vault meeting notes.

For each meeting:
1. Write the note body to `/tmp/gm_note_<n>.txt` using the Write tool. The body is plain text, minimal:

```
[Meeting Title] — YYYY-MM-DD HH:MM
[Location if any]

[Name]: [1-sentence stakeholder context from vault]
[Name]: [1-sentence context or "no vault record"]
```

No sections, no formatting, no blank templates. Just the title line and context lines.

2. After writing all body files, generate a single AppleScript to `/tmp/good_morning_create_notes.applescript` following the template pattern from `<watcher-dir>/scripts/create_notes_template.applescript`.
3. Run it:

```bash
open -a Notes && sleep 2 && \
osascript /tmp/good_morning_create_notes.applescript
```

4. If the script succeeds: "Created [N] notes in Apple Notes." If osascript returns an error, report the error message and paste the note bodies as plain text for manual entry.

If the user declines, skip Step 6 and close the briefing.

## Rules

- Never modify Dashboard.md or any vault file during the morning briefing — read only.
- Do not create meeting vault notes during `/goodmorning` — that is done by `/5pmsummary` after the meeting.
- If Calendar returns no events today, say so clearly and skip the Apple Notes offer.
- If a stakeholder has no vault record, note it but do not create a placeholder — wait until after the meeting (5pmsummary does this).
- The briefing should be scannable in under 2 minutes. Keep each section tight.
- Stakeholder context comes solely from vault files in `20-Work/Stakeholders/` — do not rely on any external reference files.
