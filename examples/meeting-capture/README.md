# Meeting capture: local-only Plaud → vault pipeline

Audio in, structured meeting notes out. No cloud calls. Runs
entirely on Apple Silicon.

## Stack

- **[Plaud Note Pro](https://plaud.ai)**: physical recorder (or any
  device that exports `.m4a`).
- **[mlx-whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper)**: ASR, ~6× realtime on M-series.
- **[pyannote-audio 3.1](https://github.com/pyannote/pyannote-audio)**: diarisation.
- **Voice-first sliding matcher (this repo)**: bypasses pyannote's
  4+ similar-voice cluster merger by doing per-window cosine
  matching against an enrolled voice bank.

## Files

| File | What it does |
|------|--------------|
| `transcribe_plaud.py` | mlx-whisper ASR with vocab initial-prompt + pyannote diarisation. Produces JSON. |
| `enroll_speaker.py` | Enrol a recurring speaker from a ~15-60s clean sample. Stores embedding in `plaud-voice-profiles.json`. |
| `match_voice_sliding.py` | Per-window cosine matching against the voice bank. Run on the JSON from `transcribe_plaud.py` to relabel speakers. |
| `plaud-vocab.example.txt` | Template vocab file. Replace with your names + organisations + acronyms. |

## The novel piece

`match_voice_sliding.py` is the part worth reading. pyannote's
default clustering merges similar voices when ≥4 close-voice
speakers are in a meeting. The sliding matcher uses 2-second
windows with per-window cosine matching against the enrolled
voice bank, sidestepping the merge entirely. Unmatched windows
stay `Unknown`.

## Adapting

1. Run `enroll_speaker.py` once per recurring meeting attendee.
2. After ~10-15 enrolments your voice bank handles most of your
   recurring meetings automatically.
3. The pipeline is generic. Point `transcribe_plaud.py` at any
   `.m4a`/`.wav`/`.mp3`, not just Plaud audio.
