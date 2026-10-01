# Meeting capture

Audio in, structured meeting notes out. No cloud calls after the first model download. Runs locally on Apple Silicon. The goal is meeting notes that capture not just what was said but who said it, and how it fits into the rest of your work. Speaker identity is what most transcription pipelines drop. This one keeps it.

The tooling now lives in its own package, **[plaudio](https://github.com/yetiswang/plaudio)** (AGPL-3.0). The three loose scripts that shipped here in v0.1 were retired in favour of it. This doc covers the method around the tool: how a recording becomes a meeting note.

## The signal hierarchy

Three sources, ranked:

1. **Apple Note tagged `#meeting`**: your own framing, written during the meeting. This is the primary signal: it tells you what you were paying attention to, what felt significant in the moment.
2. **Transcript + machine reading**: verbatim dialogue, attributed to speakers. Useful for things you missed or skimmed past.
3. **Calendar invitee list**: ground truth for who was actually in the room.

The insight comes from the gap between your framing and the machine's reading. When they diverge, that gap is worth examining.

## The pipeline

1. List the day's recordings. Plaud timestamps are UTC; convert to local time before matching anything.
2. Download each audio file, and keep a copy in a persistent archive folder as well as a scratch folder. A scratch folder that dies with a reboot has cost a two-and-a-half-hour transcript.
3. `plaudio transcribe <audio> --vocab <wordlist>`: mlx-whisper with a vocabulary prompt of names and technical terms. For anything over an hour, use the turbo model (`--model mlx-community/whisper-large-v3-turbo`). On a 16 GB machine the full large-v3 model took two and a half hours on a two-hour file and filled swap until the machine restarted; turbo did the same file in under five minutes.
4. `plaudio diarise <audio> <stem>.json`: pyannote segments who spoke when and writes `<stem>.plaud.json` with `SPEAKER_NN` clusters. Pass `--min-speakers` / `--max-speakers` from the invitee count.
5. Copy the diarised file, then `plaudio match <audio> <stem>.plaud.json --threshold 0.55`: the voice-bank matcher (below). Keep the copy, because match overwrites unmatched clusters with `Unknown`.
6. Resolve the remaining speakers with the ladder (below).
7. Time-match the recording to a calendar event within 15 minutes and pull the invitee list.
8. Write the meeting note: Your framing, Discussion, Power dynamics and insights, Actions.
9. Push actionable items to the Dashboard with a back-link to the meeting note.
10. `plaudio db ingest`: the verbatim transcript goes into a searchable SQLite + FTS5 corpus, never into the vault. The vault keeps the synthesised note only (see `examples/mcp-servers/plaud-db/`).

Run recordings one after another, not in parallel. Transcription and diarisation are both memory-heavy, and two at once is how the machine restarted.

## The voice-first matcher

pyannote's default clustering works well at two or three speakers. At four or more, it starts merging acoustically similar voices into one cluster. Two colleagues who sound alike end up labelled as one speaker, and the error is invisible in the output. The matcher works at the window level instead: it slides a two-second window across the audio and runs a cosine similarity check against every enrolled voice. Above the threshold, the window gets that label. Below it, the window stays `Unknown`. No window is forced into the wrong cluster.

The sliding match alone is conservative and leaves gaps: in a two-hour meeting it can leave half the time `Unknown`. The step that closes most of that gap is a **cluster vote**: for each pyannote cluster, add up the seconds each enrolled name won inside it, and give the cluster to the clear majority. The diariser is good at "these segments are one person"; the voice bank is good at "this is who that person is". Combined, they resolve far more than either alone.

## The speaker-resolution ladder

Cheapest rung first. Each rung labels what it can and hands the rest down.

1. **Manual labels in the recorder's app**, if you made any. These are ground truth and override everything.
2. **Voice bank**: the sliding match plus the cluster vote.
3. **Pitch split** (`plaudio gender`): when two unenrolled attendees of different gender share an open slot, split the clusters by median pitch relative to the meeting's own lowest-pitched cluster. Absolute thresholds do not survive different microphones; a relative baseline does.
4. **Calendar inference**: subtract the names already resolved from the invitee list. One open cluster and one unresolved invitee is a direct assignment.
5. **Content**: someone says "the page I built", "my file", or introduces themselves. Use it, but say in the note that the label came from content, not voice.
6. **Ask**: `plaudio label <audio> <file> --enrol --candidates "<invitees>"` plays each open cluster's cleanest stretch and offers the invitees as numbered choices.

The ladder is convergent. Every name settled at rungs 3 to 6 gets enrolled, so the same person matches automatically at rung 2 next time.

In a talk or seminar format (a room of presenters who introduce themselves), skip the ladder: attribute by self-introduction and say so in the note.

## The voice bank

Enrol each recurring attendee once with a clean 15 to 60 second sample: `plaudio enrol <audio> --name "..." --start <s> --end <e>`. Several samples per name are fine; the matcher averages them. After 10 to 15 enrolments, most recurring meetings label without manual work. The bank lives outside any repo and is backed up privately. Do not commit it to a public repo: the embeddings are biometric data.

## Local-only

Once enrolled, audio does not leave the machine. Transcription, diarisation and matching all run locally. The corpus is local. The only cloud touchpoint is the recorder's own sync. If you transfer audio over USB instead, the pipeline is entirely offline.

## Adapting

Install plaudio and run `plaudio doctor` to check the environment. The method is not Plaud-specific: any `.m4a`, `.wav`, `.mp3` or `.ogg` works. The signal hierarchy (your framing first, machine reading second, calendar as ground truth) applies whichever recorder you use. `examples/meeting-capture/` keeps the vocabulary template and a short command sequence.
