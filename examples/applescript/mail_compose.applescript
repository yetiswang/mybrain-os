(*
  Compose a new message in Apple Mail without sending.

  Supports rich-text formatting markers ([B]bold[/B], [I]italic[/I]),
  inline image paste, and file attachments. Body is typed via System Events
  keystrokes. The user reviews and clicks Send.

  Usage:
    osascript mail_compose.applescript <to> <subject> <body> [keep_sig] [attach_path] [inline_img_path]

  Arguments:
    to              -- recipient email address
    subject         -- message subject
    body            -- plain or formatted body text
    keep_sig        -- "true" to preserve signature, anything else clears it
    attach_path     -- optional POSIX path to a file attachment
    inline_img_path -- optional POSIX path to a PNG to paste inline

  Adapt:
    - No default recipient baked in; always pass the address explicitly.
    - Sending account is Mail's default; change in Mail preferences if needed.
*)

-- mail_compose.applescript
-- Full-featured: body first, then attachment at bottom
-- Usage: osascript mail_compose.applescript <to> <subject> <body> [keep_sig] [attach_path] [inline_img_path]

on run argv
	if (count of argv) < 3 then
		display dialog "Usage: osascript mail_compose.applescript <to> <subject> <body> [keep_sig] [attach_path] [inline_img_path]"
		return
	end if
	
	set toAddress to item 1 of argv
	set subjectText to item 2 of argv
	set bodyText to item 3 of argv
	
	set keepSig to false
	if (count of argv) >= 4 then set keepSig to (item 4 of argv = "true")
	
	set attachPath to ""
	if (count of argv) >= 5 then set attachPath to item 5 of argv
	
	set inlineImgPath to ""
	if (count of argv) >= 6 then set inlineImgPath to item 6 of argv
	
	-- 1. Create outgoing message (no attachment yet)
	tell application "Mail"
		set newMsg to make new outgoing message with properties {subject:subjectText, content:"", visible:true}
		tell newMsg
			make new to recipient at end of to recipients with properties {address:toAddress}
		end tell
		activate
	end tell
	
	-- 2. Copy inline image to clipboard if specified
	if inlineImgPath is not "" then
		do shell script "osascript -e 'set the clipboard to (read (POSIX file \"" & inlineImgPath & "\") as «class PNGf»)'"
	end if
	
	-- 3. UI scripting — type body FIRST
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
			
			if not keepSig then
				keystroke "a" using command down
				delay 0.1
				key code 51
				delay 0.1
			end if
			
		-- Type body text with rich formatting and inline image support
		my typeFormattedText(bodyText, inlineImgPath)
		end tell
	end tell
	
	-- 4. NOW add attachment AFTER body is typed
	if attachPath is not "" then
		tell application "Mail"
			try
				make new attachment at newMsg with properties {file name:attachPath}
			on error errMsg
				log "Attachment error: " & errMsg
			end try
		end tell
	end if
	
	return "Email composed successfully."
end run

on splitByNewline(theText)
	set prevTIDs to AppleScript's text item delimiters
	set AppleScript's text item delimiters to "\n"
	set textItems to text items of theText
	set AppleScript's text item delimiters to prevTIDs
	return textItems
end splitByNewline

-- Rich text typing with [B]bold[/B] and [I]italic[/I] markers
on typeFormattedText(theText, inlineImgPath)
	tell application "System Events"
		tell process "Mail"
			-- Parse full body text into formatted segments
			set segments to my parseFormatting(theText)
			
			set currentBold to false
			set currentItalic to false
			
			repeat with seg in segments
				set segText to theText of seg
				set segBold to isBold of seg
				set segItalic to isItalic of seg
				
				-- Toggle bold if state changed
				if segBold is not equal to currentBold then
					keystroke "b" using command down
					delay 0.05
					set currentBold to segBold
				end if
				
				-- Toggle italic if state changed
				if segItalic is not equal to currentItalic then
					keystroke "i" using command down
					delay 0.05
					set currentItalic to segItalic
				end if
				
				-- Type the segment text (handle newlines + [IMG])
				if segText is equal to "[IMG]" and inlineImgPath is not "" then
					keystroke "v" using command down
					delay 0.3
					keystroke return
				else if length of segText > 0 then
					my typeWithNewlines(segText)
				end if
			end repeat
			
			-- Ensure formatting is turned off at end
			if currentBold then
				keystroke "b" using command down
			end if
			if currentItalic then
				keystroke "i" using command down
			end if
		end tell
	end tell
end typeFormattedText

-- Type text, converting \n to keystroke return
on typeWithNewlines(theText)
	tell application "System Events"
		tell process "Mail"
			set linesList to my splitByNewline(theText)
			repeat with i from 1 to count of linesList
				set currentLine to item i of linesList
				if length of currentLine > 0 then
					keystroke currentLine
				end if
				if i < count of linesList then
					keystroke return
				end if
			end repeat
		end tell
	end tell
end typeWithNewlines

-- Parse [B]...[/B] and [I]...[/I] markers into list of {theText, isBold, isItalic} records
on parseFormatting(theText)
	-- Pass 1: handle [B]...[/B]
	set segs1 to my splitByMarker(theText, "[B]", "[/B]", "bold", false, false)
	
	-- Pass 2: handle [I]...[/I] within each segment
	set finalSegs to {}
	repeat with seg in segs1
		set subSegs to my splitByMarker(theText of seg, "[I]", "[/I]", "italic", isBold of seg, isItalic of seg)
		repeat with sub in subSegs
			if length of (theText of sub) > 0 then
				copy sub to end of finalSegs
			end if
		end repeat
	end repeat
	
	return finalSegs
end parseFormatting

-- Split text on openMarker/closeMarker, producing record list with formatting props
on splitByMarker(theText, openMarker, closeMarker, propName, inBold, inItalic)
	set segments to {}
	set prevTIDs to AppleScript's text item delimiters
	
	-- Split on open marker
	set AppleScript's text item delimiters to openMarker
	set openParts to text items of theText
	
	if (count of openParts) < 1 then
		set AppleScript's text item delimiters to prevTIDs
		return {{theText:theText, isBold:inBold, isItalic:inItalic}}
	end if
	
	-- First part: no marker formatting (inherits parent state)
	if length of (item 1 of openParts) > 0 then
		set end of segments to {theText:(item 1 of openParts), isBold:inBold, isItalic:inItalic}
	end if
	
	-- Remaining parts: start with formatted text
	repeat with i from 2 to count of openParts
		set part to item i of openParts
		
		-- Split on close marker
		set AppleScript's text item delimiters to closeMarker
		set closeParts to text items of part
		
		-- First sub-part: formatting ON for this marker
		if (count of closeParts) > 0 and length of (item 1 of closeParts) > 0 then
			set newSeg to {theText:(item 1 of closeParts), isBold:inBold, isItalic:inItalic}
			if propName = "bold" then
				set isBold of newSeg to true
			else
				set isItalic of newSeg to true
			end if
			set end of segments to newSeg
		end if
		
		-- Second sub-part: formatting OFF (back to parent state)
		if (count of closeParts) >= 2 and length of (item 2 of closeParts) > 0 then
			set end of segments to {theText:(item 2 of closeParts), isBold:inBold, isItalic:inItalic}
		end if
		
		-- Third+ sub-parts: more close markers? Unlikely but handle
		repeat with j from 3 to count of closeParts
			set AppleScript's text item delimiters to openMarker
			set nestedParts to text items of (item j of closeParts)
			if (count of nestedParts) > 0 and length of (item 1 of nestedParts) > 0 then
				-- This text would have formatting OFF already
				set end of segments to {theText:(item 1 of nestedParts), isBold:inBold, isItalic:inItalic}
			end if
		end repeat
	end repeat
	
	set AppleScript's text item delimiters to prevTIDs
	return segments
end splitByMarker
