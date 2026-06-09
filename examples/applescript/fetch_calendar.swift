#!/usr/bin/env swift
// fetch_calendar.swift
// Uses EventKit to query calendar events, bypassing AppleScript bridge timeouts.
//
// EventKit (Swift) is faster and more reliable than AppleScript for modern
// Exchange-backed calendars. Returns structured blocks for LLM consumption,
// with local-time timestamps and attendee email addresses.
//
// Output format:
//   ===CALENDAR=== or ===TOMORROW===
//   Anchor: now is <weekday date time tz>  (authoritative timestamp)
//   ---EVT---
//   Calendar: <calendar name>
//   Summary: <event title>
//   Start: <EEE yyyy-MM-dd HH:mm zzz>
//   End:   <EEE yyyy-MM-dd HH:mm zzz>
//   Location: <location or blank>
//   Attendees: Name <email>; Name <email>
//
// Usage:
//   swift fetch_calendar.swift today|tomorrow
//
// Prerequisites:
//   Grant Calendar access in System Settings -> Privacy & Security -> Calendars.
//   macOS 14+: prompts for "full access"; older macOS: standard event access.
//
// Adapt:
//   - Filter by calendar name (evt.calendar?.title) to exclude unwanted calendars.
//   - Adjust fmt.dateFormat for your preferred output style.

import EventKit
import Foundation

let args = CommandLine.arguments
guard args.count >= 2, args[1] == "today" || args[1] == "tomorrow" else {
    print("Usage: fetch_calendar.swift today|tomorrow")
    exit(1)
}

let isTomorrow = args[1] == "tomorrow"
let header = isTomorrow ? "===TOMORROW===" : "===CALENDAR==="

let store = EKEventStore()
let sema = DispatchSemaphore(value: 0)
var accessGranted = false

if #available(macOS 14.0, *) {
    store.requestFullAccessToEvents { granted, _ in
        accessGranted = granted
        sema.signal()
    }
} else {
    store.requestAccess(to: .event) { granted, _ in
        accessGranted = granted
        sema.signal()
    }
}
sema.wait()

guard accessGranted else {
    print("\(header)")
    print("ERROR: Calendar access denied. Grant access in System Settings → Privacy → Calendars.")
    exit(1)
}

// Build date range
let cal = Calendar.current
var startComponents = cal.dateComponents([.year, .month, .day], from: Date())
if isTomorrow {
    startComponents.day! += 1
}
startComponents.hour = 0
startComponents.minute = 0
startComponents.second = 0

guard let startDate = cal.date(from: startComponents) else {
    print("\(header)")
    print("ERROR: Could not compute start date")
    exit(1)
}
let endDate = cal.date(byAdding: .day, value: 1, to: startDate)!
    .addingTimeInterval(-1)  // 23:59:59

let predicate = store.predicateForEvents(withStart: startDate, end: endDate, calendars: nil)
let events = store.events(matching: predicate)
    .sorted { $0.startDate < $1.startDate }

// Local-time formatter: weekday + ISO date + HH:mm + tz abbrev (e.g. "Wed 2026-04-29 10:30 CEST")
let fmt = DateFormatter()
fmt.dateFormat = "EEE yyyy-MM-dd HH:mm zzz"
fmt.timeZone = TimeZone.current
fmt.locale = Locale(identifier: "en_US_POSIX")

let anchorFmt = DateFormatter()
anchorFmt.dateFormat = "EEEE yyyy-MM-dd HH:mm zzz"
anchorFmt.timeZone = TimeZone.current
anchorFmt.locale = Locale(identifier: "en_US_POSIX")

var output = header + "\n"
output += "Anchor: now is \(anchorFmt.string(from: Date())) (local time, authoritative)\n"

for evt in events {
    guard !evt.isAllDay || evt.title != nil else { continue }
    let evtTitle = evt.title ?? "(no title)"
    let evtStart = fmt.string(from: evt.startDate)
    let evtEnd = fmt.string(from: evt.endDate)
    let evtLocation = evt.location ?? ""
    let calName = evt.calendar?.title ?? ""

    output += "---EVT---\n"
    output += "Calendar: \(calName)\n"
    output += "Summary: \(evtTitle)\n"
    output += "Start: \(evtStart)\n"
    output += "End: \(evtEnd)\n"
    output += "Location: \(evtLocation)\n"

    var attParts: [String] = []
    if let attendees = evt.attendees {
        for att in attendees {
            let name = att.name ?? ""
            // EKParticipant URL is e.g. mailto:user@example.com
            let email = att.url.absoluteString.replacingOccurrences(of: "mailto:", with: "")
            attParts.append("\(name) <\(email)>")
        }
    }
    output += "Attendees: \(attParts.joined(separator: "; "))\n"
}

print(output, terminator: "")
