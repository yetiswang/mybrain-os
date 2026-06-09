# Meeting capture

Audio in, structured meeting notes out. No cloud calls after the first model download. Runs locally on Apple Silicon. The goal is meeting notes that capture not just what was said but who said it, and how it fits into the rest of your work. Speaker identity is what most transcription pipelines drop. This one keeps it.

## The signal hierarchy

Three sources, ranked:

1. **Apple Note tagged `#meeting`**: your own framing, written during the meeting. This is the primary signal: it tells you what you were paying attention to, what felt significant in the moment.
2. **Plaud transcript + AI summary**: verbatim dialogue and a machine reading. Useful for things you missed or skimmed past.
3. **Calendar invitee list**: ground truth for who was actually in the room.

The insight comes from the gap between your framing and the machine's reading. When they diverge, that gap is worth examining.

## The pipeline

1. List today's recordings via the Plaud cloud API. Plaud timestamps are UTC; convert to local time before matching anything.
2. Download each audio file to `/tmp`.
3. Transcribe locally with mlx-whisper. Pass a vocabulary initial-prompt with stakeholder names and technical terms so the model spells them correctly.
4. Diarise with pyannote-audio 3.1 to segment who spoke when.
5. Re-label speakers using the voice-first sliding matcher (per-window cosine match against the voice bank). This step runs after pyannote because pyannote's default clustering merges similar voices when four or more speakers are present.
6. Optional: cross-check against the Plaud cloud transcript. If you manually labelled speakers in the Plaud app, those labels are ground truth and override the local result.
7. Time-match the recording to an Apple Calendar event within a 15-minute window. Pull the invitee list.
8. Reconcile any Unknown speakers via the name-verification ladder: calendar invitees first, then the stakeholder index, then the email archive, then ask.
9. Write the meeting note with four sections: Yuyang's framing, Discussion, Power dynamics and insights, Actions.
10. Push actionable items to the Dashboard with a back-link to the meeting note.
11. Ingest into the searchable SQLite + FTS5 corpus (see `examples/mcp-servers/plaud-db/`).

## The voice-first matcher

pyannote's default clustering works well at two or three speakers. At four or more, it starts merging acoustically similar voices into one cluster. Two colleagues who sound alike end up labeled as one speaker, and the error is invisible in the output. The voice-first sliding matcher in `examples/meeting-capture/match_voice_sliding.py` works at the window level instead. It slides a two-second window across the diarised output and runs a cosine similarity check against every enrolled voice in the bank. If a window matches above the threshold, it gets that label. If nothing clears the threshold, it stays Unknown. No window is forced into the wrong cluster. The result is conservative: accurate labels where confidence is high, explicit gaps where it is not.

## The voice bank

Enrol each recurring meeting attendee once with a clean 15 to 60 second audio sample. The `enroll_speaker.py` script extracts a speaker embedding and writes it to `plaud-voice-profiles.json`. After 10 to 15 enrolments, most of your recurring meetings label correctly without any manual intervention. The bank lives outside any repo. It is synced to a private archive folder for backup, and iCloud plus a nightly git commit push it off-machine. Do not commit the JSON to a public repo: the embeddings are biometric data. One practical note: `enroll_speaker.py` records the source audio file path in the saved profile JSON. If you ever share the JSON, scrub that field first.

## Local-only

Once enrolled, audio does not leave the machine. mlx-whisper, pyannote, and the matcher all run locally. The SQLite store is local. The only cloud touchpoint is the initial Plaud sync, which is the recorder's own storage layer. If you transfer audio over USB instead, the pipeline is entirely offline.

## Adapting

See `examples/meeting-capture/README.md` for setup instructions. The pipeline is not Plaud-specific: point `transcribe_plaud.py` at any `.m4a`, `.wav`, or `.mp3` file and it works the same way. The voice-first matcher works on any audio with pyannote-quality diarisation. The signal hierarchy (your framing first, machine reading second, calendar as ground truth) applies regardless of which recorder you use.
