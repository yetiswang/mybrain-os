Read recent diary entries, meeting notes, and the project file, then synthesise patterns and write a reflective note. Memory consolidation (dedup, pruning, date conversion, MEMORY.md housekeeping) is handled by official auto-dream — this skill focuses on cross-domain synthesis only.

## Steps

1. Read `me_patterns.md` and `work_patterns.md` from `~/.claude/projects/<project-memory-dir>/memory/`

<!-- Adapt: replace the path above with your own Claude Code project memory directory. -->

2. Use the Glob tool to find diary entries in `40-Life/Hypomnemata/` with filenames starting `YYYY-MM-DD` from the past 7 days. Read each one.

3. Use the Glob tool to find meeting notes in `20-Work/Meetings/` with filenames starting `YYYY-MM-DD` from the past 7 days. Read each one.

4. Read `30-Projects/<MyProject>.md`.

4b. Read `10-Research/My-readings/Management Reading Path.md` for the structured reading plan. Scan `10-Research/My-readings/My Books.md` for categories: Leadership & Strategy, Philosophy, Psychology & Wellbeing, Productivity & Self-Help, Economics, Geopolitics. For any book that seems relevant to the week's patterns, read its note from `10-Research/My-readings/Books/<Title>.md` to draw on key ideas and frameworks.

5. **Synthesis task** — read across diary, meetings, and project file:
   - Identify patterns in decisions, emotional tone, energy, and recurring themes
   - Update `me_patterns.md` (personal/emotional observations) and `work_patterns.md` (strategic/professional observations) with new observations, preserving prior entries
   - Write a synthesis note (structure below). No em-dashes.
   - List any CLAUDE.md promotion candidates in the report only — never write to CLAUDE.md

   **Synthesis note structure** (6-10 paragraphs total):

   **Part 1 — Pattern recognition** (2-3 paragraphs): What happened this week, connecting work themes to personal patterns. Name the sharpest observation. Surface what is repeating.

   **Part 2 — Strategic advisory** (3-5 paragraphs): This is the honest counsel section. Be direct, not gentle.
   - **Career and project strategy:** Where is the vault owner being naive, over-optimistic, or emotionally driven in professional decisions? Where is there confusion between momentum and progress, or between being busy and being effective? Point out blind spots in stakeholder management, political positioning, or resource allocation. Name the risk honestly.
   - **Personal life and wellbeing:** Where is an emotional pattern (excitement-tension cycle, over-eager pacing, avoidance disguised as delegation) about to cause a bad decision? Where is rationalization happening instead of reflection?
   - **Book references:** Connect observations to specific books from `10-Research/My-readings/Books/` or `10-Research/My-readings/Management Reading Path.md`. Reference frameworks, ideas, or warnings from books in the library that are relevant to this week's patterns. If a book note exists with key ideas, draw from it. If a book is unread but its topic is directly relevant, recommend it with a specific reason. Use wikilinks: `[[Book Title]]`.
   - **Philosophy and deeper patterns:** Draw on broader philosophical ideas (Stoicism, Drucker, systems thinking, whatever fits) to reframe a situation that may be seen too narrowly.
   - Be honest about where decisions look emotion-driven rather than strategy-driven. The tone is that of a trusted advisor who will not flatter. If something looks like it will go wrong, say so and say why.

   **Part 3 — Forward-looking question** (1 paragraph): Close with one question worth sitting with for the week. Make it specific to what was observed, not generic.

6. Write updated `me_patterns.md` and/or `work_patterns.md` back using the Edit tool. Personal, emotional, identity, and parenting observations go to `me_patterns.md`. Strategic, decision-making, communication, and stakeholder observations go to `work_patterns.md`.

7. **Sync project memory files.** Read all `project_*.md` files in the memory directory. Cross-check each against the current state of vault project files (`30-Projects/<MyProject>.md`, meeting notes from the past week, diary entries). Update any project memory that is stale, partially resolved, or missing context from the week's events. Remove memories that are fully resolved. Create new project memories if the week surfaced significant developments not yet captured. Update `MEMORY.md` index accordingly.

8. Write the synthesis note to `40-Life/Reflections/YYYY-MM-DD-reflect.md` (use today's date).

9. Report: whether patterns were updated, whether project memories were synced (list changes), whether synthesis was written, any CLAUDE.md candidates to review.
