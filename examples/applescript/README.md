# AppleScript & EventKit — macOS-native rituals

These scripts make Claude Code feel native on macOS by reaching
into Apple Mail, Calendar, and Notes via AppleScript and EventKit.

## Files

| File | What it does |
|------|--------------|
| `mail_compose.applescript` | Compose a new message (no send). Supports `[B]bold[/B]`, `[I]italic[/I]`, inline image paste, and file attachments. |
| `mail_reply.applescript` | Reply in-thread, preserving quoted text and signature. Reads body from a temp file to avoid escaping issues. |
| `mail_compose_send.applescript` | Compose and auto-send. Has a built-in safety guard: rejects any recipient other than `ALLOWED_RECIPIENT`. |
| `fetch_day.applescript` | Fetch one day of Inbox (smart lookback) + Calendar + Apple Notes + tomorrow's calendar. Main input for a daily briefing workflow. |
| `fetch_email.applescript` | On-demand search by sender and/or subject. Returns full bodies. Useful for looking up a thread before replying. |
| `fetch_calendar.swift` | EventKit Swift binary — today's or tomorrow's calendar events with attendees. Faster and more reliable than AppleScript for Exchange. |
| `create_notes_template.applescript` | Pattern template for creating Apple Notes entries. An agent fills and runs a generated version per session. |

## The key patterns

1. **Always filter with `whose` before iterating.** Apple Mail's
   `whose` clause runs server-side (Exchange/IMAP) in ~1.5s.
   Iterating a large mailbox without `whose` is minutes-slow.

2. **Reply via `reply with opening window` + clipboard paste.**
   Never use `set content` — it nukes the quoted thread and
   skips the user's signature.

3. **For Calendar, EventKit Swift is faster than AppleScript.**
   AppleScript Calendar reads are flaky on modern macOS; Swift
   + EventKit is solid and exposes attendee email addresses cleanly.

4. **Use file I/O for multi-line Apple Notes bodies.**
   Write body content to `/tmp/note_<n>.txt` and read via
   `read POSIX file` — avoids shell-escaping apostrophes and quotes.

## Adapting

Most defaults (your email address, your account name, Swift binary paths)
have been replaced with `<your-email>`, `<account-name>`, and similar
placeholders. Edit each file to add yours back before use.

For `mail_compose_send.applescript`, set the `ALLOWED_RECIPIENT` property
at the top of the file to your own address.

For `fetch_day.applescript` and `fetch_calendar.swift`, grant Calendar
access in System Settings → Privacy & Security → Calendars.
