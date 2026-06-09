(*
  Fetch one day of inbox emails, calendar events, and Apple Notes.

  Fetches inbox messages from your configured account with smart lookback:
  - Weekdays: from yesterday 17:00 (catches post-5pm arrivals)
  - Monday: from Friday 17:00 (covers the weekend gap)

  Output is structured blocks for LLM consumption:
    ===EMAILS===    inbox messages, auto-filtered, capped at 40
    ===CALENDAR===  today's events via EventKit Swift binary
    ===NOTES===     Apple Notes modified today with #meeting or #talk prefix
    ===TOMORROW===  next day's calendar events

  Calendar events are fetched via a companion Swift binary (fetch_calendar.swift)
  to avoid AppleScript bridge timeouts on Exchange-backed calendars.

  Usage:
    osascript fetch_day.applescript

  Adapt:
    - Replace <your-email> in the account filter with your actual address.
    - Update the swiftScript path to point to your fetch_calendar.swift location.
    - Adjust skipPatterns and skipSubjectPatterns for your newsletter/auto-mail signatures.
*)

-- fetch_day.applescript
-- Fetches inbox emails + calendar events for today
-- Email lookback: yesterday 17:00 on weekdays, Friday 17:00 on Mondays
-- Output blocks: ===EMAILS===, ===CALENDAR===, ===NOTES===, ===TOMORROW===
-- Usage: osascript /path/to/fetch_day.applescript

set startOfDay to current date
set hours of startOfDay to 0
set minutes of startOfDay to 0
set seconds of startOfDay to 0
set endOfDay to startOfDay + (23 * hours + 59 * minutes + 59)

set startOfTomorrow to startOfDay + (1 * days)
set endOfTomorrow to startOfTomorrow + (23 * hours + 59 * minutes + 59)

-- Email lookback: on weekdays, start from yesterday at 17:00 to catch emails
-- that arrived after the previous day's 5pm summary. On Monday, reach back to
-- Friday 17:00 to cover the full weekend gap.
set todayWeekday to weekday of (current date)
if todayWeekday is Monday then
	set emailLookback to startOfDay - (55 * hours) -- Friday 17:00
else
	set emailLookback to startOfDay - (7 * hours) -- yesterday 17:00
end if

-- ===== EMAILS =====
-- Filters out newsletters/automated mail and caps at 40 messages to keep output manageable.
-- Automated sender patterns to skip (lowercase match):
-- Add institution-specific automated senders here (e.g. "insite@<institution-tld>")
set skipPatterns to {"no-reply", "noreply", "mailer-daemon", "newsletter", "notification@", "notifications@", "alert@", "alerts@", "do-not-reply", "donotreply"}
-- Additional subject patterns that indicate bulk/automated mail:
set skipSubjectPatterns to {"unsubscribe", "nieuwsbrief", "webinar", "lecture series", "mailing list"}

set emailOutput to "===EMAILS===" & linefeed
set emailCount to 0
set emailCap to 40

-- Wait for Mail to finish syncing (check message count stabilises)
try
  tell application "Mail"
    check for new mail
  end tell
  delay 8
end try

try
  with timeout of 60 seconds
    tell application "Mail"
      repeat with acct in accounts
        if email addresses of acct contains "<your-email>" then
          repeat with mb in every mailbox of acct
            if name of mb is "Inbox" then
              set recentMsgs to (every message of mb whose date received >= emailLookback)
              repeat with msg in recentMsgs
                if emailCount >= emailCap then exit repeat

                set msgSubject to subject of msg
                set msgSender to sender of msg
                set msgDate to date received of msg
                set msgRead to read status of msg

                -- Filter: skip automated/newsletter senders and subjects
                set senderLower to do shell script "echo " & quoted form of (msgSender as string) & " | tr '[:upper:]' '[:lower:]' 2>/dev/null || echo ''"
                set subjectLower to do shell script "echo " & quoted form of (msgSubject as string) & " | tr '[:upper:]' '[:lower:]' 2>/dev/null || echo ''"
                set shouldSkip to false
                repeat with pat in skipPatterns
                  if senderLower contains pat then
                    set shouldSkip to true
                    exit repeat
                  end if
                end repeat
                if not shouldSkip then
                  repeat with pat in skipSubjectPatterns
                    if subjectLower contains pat then
                      set shouldSkip to true
                      exit repeat
                    end if
                  end repeat
                end if
                if shouldSkip then
                  -- still count skipped to detect if inbox is flooded
                else
                  set msgContent to ""
                  try
                    set msgContent to content of msg
                    -- Strip common forwarding headers that eat the truncation budget
                    -- (Outlook iOS "Inviato da", "Da:", "A:", "Oggetto:", "Sent:", "From:", "To:", "Subject:" blocks before the real body)
                    try
                      set stripScript to "echo " & quoted form of msgContent & " | sed -E '/^(Inviato da|Da:|A:|Oggetto:|Sent:|Date:|Verzonden:|Aan:|Onderwerp:)/d' | sed '/^$/N;/^\\n$/d'"
                      set msgContent to do shell script stripScript
                    end try
                    if length of msgContent > 2000 then
                      set msgContent to text 1 thru 2000 of msgContent & "..."
                    end if
                  end try
                  -- ===== ATTACHMENTS =====
                  set attLine to ""
                  set attDir to "/tmp/5pm-attachments/"
                  try
                    do shell script "mkdir -p " & quoted form of attDir
                    set attList to every mail attachment of msg
                    if (count of attList) > 0 then
                      set attNames to {}
                      repeat with att in attList
                        set attName to name of att
                        -- Only save document types (PDF, DOCX, XLSX, PPTX, TXT, CSV, MD)
                        set attLower to do shell script "echo " & quoted form of attName & " | tr '[:upper:]' '[:lower:]'"
                        set shouldSave to false
                        repeat with ext in {".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".csv", ".md", ".doc", ".xls", ".tex", ".html"}
                          if attLower ends with ext then
                            set shouldSave to true
                            exit repeat
                          end if
                        end repeat
                        if shouldSave then
                          try
                            set savePath to attDir & attName
                            save att in POSIX file savePath
                            set end of attNames to attName
                          end try
                        else
                          -- Log name but don't save (images, .ics, etc)
                          set end of attNames to attName & " [not saved]"
                        end if
                      end repeat
                      set AppleScript's text item delimiters to ", "
                      set attLine to attNames as string
                      set AppleScript's text item delimiters to ""
                    end if
                  end try

                  set emailOutput to emailOutput & "---MSG---" & linefeed
                  set emailOutput to emailOutput & "Date: " & msgDate & linefeed
                  set emailOutput to emailOutput & "From: " & msgSender & linefeed
                  set emailOutput to emailOutput & "Subject: " & msgSubject & linefeed
                  set emailOutput to emailOutput & "Read: " & msgRead & linefeed
                  if attLine is not "" then
                    set emailOutput to emailOutput & "Attachments: " & attLine & linefeed
                  end if
                  set emailOutput to emailOutput & "Body: " & msgContent & linefeed
                  set emailCount to emailCount + 1
                end if
              end repeat
            end if
          end repeat
        end if
      end repeat
    end tell
  end timeout
on error errMsg
  set emailOutput to emailOutput & "ERROR: Mail timed out or failed — " & errMsg & linefeed
end try

-- ===== CALENDAR (today) =====
-- Uses Swift/EventKit to avoid AppleScript bridge timeouts on Exchange calendars
-- ADAPT: update this path to wherever you placed fetch_calendar.swift
set swiftScript to (POSIX path of (path to home folder)) & "path/to/fetch_calendar.swift"
set calOutput to ""
try
  set calOutput to do shell script "swift " & quoted form of swiftScript & " today 2>/dev/null"
on error errMsg
  set calOutput to "===CALENDAR===" & linefeed & "ERROR: calendar fetch failed — " & errMsg
end try
set calOutput to calOutput & linefeed

-- ===== APPLE NOTES =====
set notesOutput to "===NOTES===" & linefeed

try
  with timeout of 30 seconds
    tell application "Notes"
      repeat with n in every note
        if modification date of n >= startOfDay then
          set nName to name of n
          if nName starts with "#meeting" or nName starts with "#talk" then
            set nBody to ""
            try
              set nBody to body of n
            end try
            set notesOutput to notesOutput & "---NOTE---" & linefeed
            set notesOutput to notesOutput & "Title: " & nName & linefeed
            set notesOutput to notesOutput & "Modified: " & (modification date of n) & linefeed
            set notesOutput to notesOutput & "Body: " & nBody & linefeed
          end if
        end if
      end repeat
    end tell
  end timeout
on error errMsg
  set notesOutput to notesOutput & "ERROR: Notes timed out or failed — " & errMsg & linefeed
end try

-- ===== TOMORROW'S CALENDAR =====
-- Uses Swift/EventKit to avoid AppleScript bridge timeouts on Exchange calendars
set tomorrowCalOutput to ""
try
  set tomorrowCalOutput to do shell script "swift " & quoted form of swiftScript & " tomorrow 2>/dev/null"
on error errMsg
  set tomorrowCalOutput to "===TOMORROW===" & linefeed & "ERROR: calendar fetch failed — " & errMsg
end try
set tomorrowCalOutput to tomorrowCalOutput & linefeed

return emailOutput & linefeed & calOutput & linefeed & notesOutput & linefeed & tomorrowCalOutput
