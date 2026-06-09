(*
  Reply in-thread via Apple Mail (Exchange or any account).

  Pattern: `reply with opening window`, then paste body via
  System Events clipboard. This preserves the quoted thread
  and triggers the user's signature. Never use `set content` —
  it overwrites the thread and signature.

  Body is read from a temp file so multi-line content works without
  shell escaping. The script leaves a draft open; the user clicks Send.

  Usage:
    osascript mail_reply.applescript <reply_body_file> [sender_filter]

  Arguments:
    reply_body_file -- POSIX path to a plain-text file containing the reply body
    sender_filter   -- optional substring match on sender name (e.g. "Alice")
                       Without filter: targets the most recent inbox message.

  Adapt:
    - The script matches accounts via email address; update the `email addresses`
      contains filter to match your own account address.
*)

-- mail_reply.applescript
-- Opens a reply draft. Reads reply body from file.
-- Usage: osascript mail_reply.applescript <reply_body_file> [sender_filter]
--
-- sender_filter: optional — matches against sender name (e.g. "Alice" or "Bob")
-- Without filter: replies to the most recent inbox message.
-- DRAFT ONLY — user reviews and clicks Send.

on run argv
	if (count of argv) < 1 then
		display dialog "Usage: osascript mail_reply.applescript <reply_body_file> [sender_filter]"
		return
	end if
	
	set bodyFilePath to item 1 of argv
	set senderFilter to ""
	if (count of argv) >= 2 then set senderFilter to item 2 of argv
	
	set replyBody to (do shell script "cat " & quoted form of bodyFilePath)
	
	tell application "Mail"
		-- Find the target message
		set targetMsg to missing value
		
		if senderFilter is not "" then
			-- Fast server-side search with 'whose' filter (no iteration)
			try
				set matchingMsgs to (messages of inbox whose sender contains senderFilter)
				if (count of matchingMsgs) > 0 then
					set targetMsg to item 1 of matchingMsgs
				end if
			end try
		end if
		
		if targetMsg is missing value then
			set targetMsg to message 1 of inbox
		end if
		set originalSubject to subject of targetMsg
		
		-- Create reply (opens reply compose window)
		set replyMsg to reply targetMsg with opening window
		
		-- Give Mail a moment to open the reply window
		activate
		delay 0.5
	end tell
	
	-- Copy reply body to clipboard
	set the clipboard to replyBody
	
	-- UI scripting: focus body, select existing content, paste
	tell application "System Events"
		tell process "Mail"
			set frontmost to true
			delay 0.3
			
			-- Find the reply window (subject starts with "Re:")
			set replyWindow to missing value
			repeat with w in (every window)
				try
					set wTitle to name of w
					if wTitle contains "Re:" and wTitle contains originalSubject then
						set replyWindow to w
						exit repeat
					end if
				end try
			end repeat
			
			if replyWindow is missing value then
				return "ERROR: reply window not found"
			end if
			
			-- Focus the body scroll area
			set bodyScrollArea to scroll area 1 of group 1 of group 3 of replyWindow
			set focused of bodyScrollArea to true
			
			try
				set innerGroup to group 1 of UI element 1 of bodyScrollArea
				set focused of innerGroup to true
			on error
				try
					set innerUI to UI element 1 of bodyScrollArea
					set focused of innerUI to true
				end try
			end try
			
			delay 0.3
			
			-- Paste reply body (cursor already at top, don't select — preserves quoted thread below)
			keystroke "v" using command down
			delay 0.3
			
			-- Add blank line between reply and quoted thread
			keystroke return
			keystroke return
		end tell
	end tell
	
	return "Reply draft ready: " & originalSubject
end run
