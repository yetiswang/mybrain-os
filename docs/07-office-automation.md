# Office automation: shared sheets and directory decks

Not everything a knowledge worker touches is a Markdown note. Some of it is a
spreadsheet five people edit online, or a slide deck that has to stay visually
consistent while it grows one entry at a time. These are the unglamorous
surfaces where manual work quietly accumulates, and they automate well because
the file formats are just zipped XML. No cloud APIs are involved — the scripts
operate on the locally-synced copies, so they work the same whether the file
lives in OneDrive, SharePoint, a Teams library, or a synced Drive folder.

The examples are in [`examples/office/`](../examples/office/).

## Tracking a shared spreadsheet

A workbook that several people edit online drifts between the times you open
it, and nothing tells you who changed what. The pattern that fixes this is
small and general: keep a **private baseline** of the sheet's contents, and
on demand diff the current file against it.

It runs as a three-step ritual around any edit:

1. Diff against the baseline first, and log the drift as *other people's*
   edits (re-snapshot).
2. Make your own edit.
3. Diff again, and log that as *yours* (re-snapshot).

Anything that appears before you edit was someone else's change; anything
after is yours. That temporal split is what lets one diff engine attribute
both sides without any per-user tracking. Rows are keyed by a key column — a
name or an ID — so the log reads `CHANGED <row>: Email a -> b` rather than by
opaque cell coordinates, and the change-log file lives next to the sheet where
collaborators can read it. The baseline stays private and out of the shared
folder.

The one caveat is sync lag: detection only sees what the cloud client has
pulled to local disk. If someone just saved, wait a moment before diffing.

## Generating directory cards

A directory deck — one slide per person, lab, or team — is tedious to extend
by hand and easy to make inconsistent. `python-pptx` has no clean "duplicate
this slide", but it can deep-copy the XML of individual shapes, and that turns
out to be enough.

The trick is to **mirror a template slide** instead of building a layout from
scratch: add a blank slide on the template's layout, deep-copy every shape
from the template except the photo, then replace the text runs in place. The
fonts, colours, and positions survive exactly because the new card is the same
XML. The photo is added fresh and clipped to a circle by swapping its geometry
for an `ellipse` preset and dropping the outline, locked to a fixed position so
every card lines up with the last.

A companion script stamps an idempotent "Updated <date>, <time>" tag on the
title slide, bumped on every save, so the deck (and any PDF rendered from it)
always shows when it last changed.

## Why these belong in the OS

Both patterns are the same move the rest of this system makes: encode a
repeatable ritual so the agent runs it the same way every time, and so the
human record (who changed what; when the deck was last touched) is a
by-product of doing the work, not a separate chore. The spreadsheet monitor in
particular composes with the [hooks and slash commands](03-hooks-and-skills.md)
— it's the kind of step an edit-the-deck command runs automatically before and
after it touches the file.
