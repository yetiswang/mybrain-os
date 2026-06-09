(*
  Template for creating Apple Notes entries via AppleScript.

  This file is a pattern template, not a runnable script. An agent fills
  it per session: it writes body content to /tmp/note_<n>.txt files, then
  generates and runs an AppleScript that reads those files and creates the
  corresponding Apple Notes entries.

  Using file I/O (read POSIX file) rather than string interpolation avoids
  escaping issues with apostrophes, quotes, and special characters in note bodies.

  Adapt:
    - Change "iCloud" to your Notes account name if different.
    - Change "Notes" folder name to your target folder.
    - Adjust the /tmp/note_<n>.txt naming convention to taste.
*)

-- create_notes_template.applescript
-- TEMPLATE ONLY — not run directly.
-- An agent generates a filled version per session and runs it.
--
-- Pattern: for each note, body content is written to /tmp/note_<n>.txt,
-- then this generated script reads those files and creates Apple Notes.
--
-- Generated script example (for 2 meetings):
--
-- tell application "Notes"
--   tell account "iCloud"
--     set note1Body to (read POSIX file "/tmp/gm_note_1.txt")
--     -- "Notes" is the default iCloud folder name; change if your account uses a different name
--     make new note at folder "Notes" with properties {name:"[Meeting] Title 1", body:note1Body}
--     set note2Body to (read POSIX file "/tmp/gm_note_2.txt")
--     -- "Notes" is the default iCloud folder name; change if your account uses a different name
--     make new note at folder "Notes" with properties {name:"[Meeting] Title 2", body:note2Body}
--   end tell
-- end tell
--
-- Claude fills this pattern during Step 6 of the skill execution.
-- Body files are written by the Write tool — no escaping needed (file I/O, not string interpolation).
-- Notes land in the default iCloud Notes folder.
