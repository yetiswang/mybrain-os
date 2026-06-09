(*
  On-demand email search via Apple Mail.

  Searches your inbox by sender and/or subject keyword and returns
  full message bodies. Useful for looking up a specific thread before
  writing a reply or drafting a follow-up.

  Uses `whose` for server-side filtering (~1.5s on Exchange/IMAP).
  Returns up to 10 matches; cap is adjustable via matchCap.

  Usage:
    osascript fetch_email.applescript "sender_query" "subject_query" [hours_back]

  Examples:
    osascript fetch_email.applescript "alice" ""           # by sender
    osascript fetch_email.applescript "" "Q3 report"       # by subject
    osascript fetch_email.applescript "alice" "Q3" 48      # both, 48-hour window

  Adapt:
    - Replace <your-email> in the account filter with your actual address.
    - Adjust matchCap (default 10) if you want more results.
*)

-- fetch_email.applescript
-- On-demand email lookup from your inbox
-- Searches by sender and/or subject, returns full body
-- Usage: osascript fetch_email.applescript "sender_query" "subject_query" [hours_back]
-- Examples:
--   osascript fetch_email.applescript "alice" ""           # by sender
--   osascript fetch_email.applescript "" "Q3 report"       # by subject
--   osascript fetch_email.applescript "alice" "Q3" 48      # both

on run argv
	if (count of argv) < 2 then
		return "Usage: osascript fetch_email.applescript \"sender\" \"subject\" [hours_back]"
	end if

	set senderQuery to item 1 of argv
	set subjectQuery to item 2 of argv

	-- Default lookback: 24 hours
	set hoursBack to 24
	if (count of argv) >= 3 then
		try
			set hoursBack to (item 3 of argv) as integer
		end try
	end if

	set cutoff to (current date) - (hoursBack * hours)
	set senderLower to do shell script "echo " & quoted form of senderQuery & " | tr '[:upper:]' '[:lower:]'"
	set subjectLower to do shell script "echo " & quoted form of subjectQuery & " | tr '[:upper:]' '[:lower:]'"

	set output to ""
	set matchCount to 0
	set matchCap to 10

	try
		with timeout of 60 seconds
			tell application "Mail"
				repeat with acct in accounts
					if email addresses of acct contains "<your-email>" then
						repeat with mb in every mailbox of acct
							if name of mb is "Inbox" then
								set recentMsgs to (every message of mb whose date received >= cutoff)
								repeat with msg in recentMsgs
									if matchCount >= matchCap then exit repeat

									set msgSubject to subject of msg
									set msgSender to sender of msg
									set msgDate to date received of msg
									set msgRead to read status of msg

									-- Match sender and/or subject (case-insensitive)
									set msgSenderLower to do shell script "echo " & quoted form of (msgSender as string) & " | tr '[:upper:]' '[:lower:]' 2>/dev/null || echo ''"
									set msgSubjectLower to do shell script "echo " & quoted form of (msgSubject as string) & " | tr '[:upper:]' '[:lower:]' 2>/dev/null || echo ''"

									set senderMatch to (senderLower is "" or msgSenderLower contains senderLower)
									set subjectMatch to (subjectLower is "" or msgSubjectLower contains subjectLower)

									if senderMatch and subjectMatch then
										-- Get full body (no truncation)
										set msgContent to ""
										try
											set msgContent to content of msg
											-- Strip forwarding headers
											try
												set stripScript to "echo " & quoted form of msgContent & " | sed -E '/^(Inviato da|Da:|A:|Oggetto:|Sent:|Date:|Verzonden:|Aan:|Onderwerp:)/d' | sed '/^$/N;/^\\n$/d'"
												set msgContent to do shell script stripScript
											end try
										end try

										-- List attachments (names only)
										set attLine to ""
										try
											set attList to every mail attachment of msg
											if (count of attList) > 0 then
												set attNames to {}
												repeat with att in attList
													set end of attNames to name of att
												end repeat
												set AppleScript's text item delimiters to ", "
												set attLine to attNames as string
												set AppleScript's text item delimiters to ""
											end if
										end try

										set output to output & "---MSG---" & linefeed
										set output to output & "Date: " & msgDate & linefeed
										set output to output & "From: " & msgSender & linefeed
										set output to output & "Subject: " & msgSubject & linefeed
										set output to output & "Read: " & msgRead & linefeed
										if attLine is not "" then
											set output to output & "Attachments: " & attLine & linefeed
										end if
										set output to output & "Body:" & linefeed & msgContent & linefeed
										set matchCount to matchCount + 1
									end if
								end repeat
							end if
						end repeat
					end if
				end repeat
			end tell
		end timeout
	on error errMsg
		set output to output & "ERROR: " & errMsg & linefeed
	end try

	if matchCount is 0 then
		return "No emails found matching sender=\"" & senderQuery & "\" subject=\"" & subjectQuery & "\" in the last " & hoursBack & " hours."
	end if

	return "Found " & matchCount & " email(s):" & linefeed & output
end run
