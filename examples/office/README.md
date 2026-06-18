# Office automation: shared sheets & directory decks

Three scripts for the boring-but-real office surface: a spreadsheet that
several people edit online, and a slide deck that has to stay consistent as
it grows. All pure Python (`openpyxl`, `python-pptx`, `Pillow`), no cloud
APIs — they operate on the locally-synced copies of the files.

| File | What it does |
|------|--------------|
| `xlsx_change_monitor.py` | Snapshot / diff / attributed change-log for a workbook multiple people edit online. Logs who changed what, by row identity. |
| `pptx_card_from_form.py` | Turn a form entry into a new profile card by mirroring a template slide (deep-copy shapes, swap text, toggle pills, clip the photo to a circle). |
| `pptx_stamp_updated.py` | Stamp an "Updated <date>, <time>" tag on a deck's title slide. Idempotent; run on every save. |

## The change-monitor pattern

A shared sheet (OneDrive / SharePoint / Teams / a synced Drive folder) drifts
between the times you touch it, and nothing records who changed what. The
fix is small: keep a **private baseline** of the sheet's contents, and on
demand diff the current file against it. Run it as a three-step ritual around
any edit you make:

```bash
python3 xlsx_change_monitor.py check --author "teammates (online)"   # log others' drift, re-snapshot
# ...make your edit...
python3 xlsx_change_monitor.py check --author "me"                   # log your edit, re-snapshot
```

Anything found *before* you edit was someone else's; anything *after* is
yours. Rows are keyed by a key column (a name or ID) so the log reads
`~ CHANGED Acme Lab: Email a -> b`, not `Sheet1!C5`. The change-log lives
next to the sheet (teammates can read it); the baseline stays private.

Caveat: detection relies on the cloud client having synced others' edits to
local disk. Sync lags a minute or two — wait before `check` if someone just
saved.

## The novel piece: mirroring a slide

`pptx_card_from_form.py` is the part worth reading. python-pptx has no clean
"duplicate slide", but you can deep-copy the XML of individual shapes. So:
add a blank slide on the template's layout, copy every shape from the
template *except* the picture, then edit the text runs in place. The design
(fonts, colours, positions) survives exactly because it's literally the same
XML. The photo is added fresh and clipped to a circle by replacing its
geometry with an `ellipse` preset (`a:prstGeom prst="ellipse"`, keeping
`a:xfrm` first) and removing the outline — locked to a fixed position so
every card aligns.

## Adapting

- `xlsx_change_monitor.py`: set `SHEET`, `KEY_COLS`, and `HEADER_ROW`/`DATA_START`
  for your workbook. The baseline path should sit *outside* the shared folder.
- `pptx_card_from_form.py`: dump your template slide's shape ids
  (`for sh in slide.shapes: print(sh.shape_id, sh.name, sh.text_frame.text)`)
  and fill in `FIELD_SHAPE_IDS` / `PILL_SHAPES`. Tune `PHOTO_L/T/S` to your
  template's photo slot.
- `pptx_stamp_updated.py`: tune the textbox position to your title layout.
