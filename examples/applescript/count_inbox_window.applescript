-- Ground-truth count for the 5pm fetch plausibility guard.
-- Usage: osascript count_inbox_window.applescript <hours>
-- Counts Inbox messages received since (today 00:00 minus <hours>), the same
-- window the fetch script reports in its ===META=== block.
-- Adapt: replace the address with your own account's address.
on run argv
	set lb to 7
	if (count of argv) > 0 then set lb to (item 1 of argv) as integer
	set d to (current date)
	set hours of d to 0
	set minutes of d to 0
	set seconds of d to 0
	set sinceDate to d - (lb * hours)
	tell application "Mail"
		repeat with acct in accounts
			if email addresses of acct contains "you@example.org" then
				repeat with mb in every mailbox of acct
					if name of mb is "Inbox" then return (count of (every message of mb whose date received ≥ sinceDate))
				end repeat
			end if
		end repeat
	end tell
	return 0
end run
