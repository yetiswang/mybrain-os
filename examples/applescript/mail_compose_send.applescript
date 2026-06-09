(*
  Compose and auto-send an email via Apple Mail.

  WARNING: This script actually sends. Use mail_compose.applescript
  for drafts that require human review before sending.

  Built-in safety guard: the script refuses to send to any address
  other than the one hard-coded in the ALLOWED_RECIPIENT constant.
  Update that constant to your own address before use.

  Usage:
    osascript mail_compose_send.applescript <to> <subject> <body> [attachment]

  Arguments:
    to         -- recipient email address (must match ALLOWED_RECIPIENT)
    subject    -- message subject
    body       -- message body text
    attachment -- optional POSIX path to a file attachment

  Adapt:
    - Set ALLOWED_RECIPIENT to your own email address.
    - The safety check is intentionally strict: use mail_compose.applescript
      for any message going to someone other than yourself.
*)

-- mail_compose_send.applescript
-- Composes AND SENDS email via Apple Mail + System Events keystrokes.
-- WARNING: auto-sends. For drafts, use mail_compose.applescript.
-- Usage: osascript mail_compose_send.applescript <to> <subject> <body> [attachment]

-- ADAPT: set this to your own address. The safety guard blocks all other recipients.
property ALLOWED_RECIPIENT : "<your-email>"

on run argv
	if (count of argv) < 3 then
		display dialog "Usage: osascript mail_compose_send.applescript <to> <subject> <body> [attachment]"
		return
	end if

	set toAddress to item 1 of argv
	set subjectText to item 2 of argv
	set bodyText to item 3 of argv

	-- Safety guard: reject any recipient that isn't self
	if toAddress is not ALLOWED_RECIPIENT then
		display dialog "SAFETY: Cannot auto-send to " & toAddress & return & "Only " & ALLOWED_RECIPIENT & " is allowed." buttons {"OK"} default button 1 with icon stop
		return "BLOCKED: " & toAddress
	end if
	
	set attachPath to ""
	if (count of argv) >= 4 then set attachPath to item 4 of argv
	
	-- 1. Create outgoing message
	tell application "Mail"
		set newMsg to make new outgoing message with properties {subject:subjectText, content:"", visible:true}
		tell newMsg
			make new to recipient at end of to recipients with properties {address:toAddress}
		end tell
		activate
	end tell
	
	-- 2. Type body via keystrokes
	tell application "System Events"
		tell process "Mail"
			repeat 30 times
				try
					set frontWindow to first window whose title = subjectText
					exit repeat
				on error
					delay 0.2
				end try
			end repeat
			
			set composeWindow to first window whose title = subjectText
			set frontmost to true
			
			set bodyScrollArea to scroll area 1 of group 1 of group 3 of composeWindow
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
			
			-- Clear existing content (signature)
			keystroke "a" using command down
			delay 0.1
			key code 51
			delay 0.1
			
			-- Type body with formatting markers
			set textLines to my splitByNewline(bodyText)
			repeat with i from 1 to count of textLines
				set currentLine to item i of textLines
				keystroke currentLine
				if i < count of textLines then
					keystroke return
				end if
			end repeat
		end tell
	end tell
	
	-- 4. Wait for keystrokes to finish (scale with body length)
	set bodyLen to length of bodyText
	set typeDelay to bodyLen * 0.002
	if typeDelay < 1 then set typeDelay to 1
	delay typeDelay
	
	-- 5. Add attachment if specified
	if attachPath is not "" then
		tell application "Mail"
			try
				make new attachment at newMsg with properties {file name:attachPath}
			end try
		end tell
	end if
	
	-- 6. Send
	tell application "Mail"
		send newMsg
	end tell
	
	delay 2
	return "Sent: " & subjectText
end run

on splitByNewline(theText)
	set prevTIDs to AppleScript's text item delimiters
	set AppleScript's text item delimiters to "\n"
	set textItems to text items of theText
	set AppleScript's text item delimiters to prevTIDs
	return textItems
end splitByNewline
