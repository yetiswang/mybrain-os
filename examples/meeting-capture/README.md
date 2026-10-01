# Meeting capture

The scripts that lived here in v0.1 (`transcribe_plaud.py`, `enroll_speaker.py`, `match_voice_sliding.py`) are retired. The pipeline is now the **[plaudio](https://github.com/yetiswang/plaudio)** package. The method is in [`docs/05-meeting-capture.md`](../../docs/05-meeting-capture.md).

## Files

| File | What it does |
|------|--------------|
| `plaud-vocab.example.txt` | Template vocabulary file for the transcription prompt. Replace with your names, organisations and acronyms. |
| `cluster_vote.py` | Gives each diarisation cluster the enrolled name that won most of its matched seconds. |

## One recording, end to end

```bash
plaudio transcribe meeting.ogg --model mlx-community/whisper-large-v3-turbo \
  --vocab plaud-vocab.txt --language en --out out/
plaudio diarise meeting.ogg out/meeting.json --out out/ --min-speakers 3 --max-speakers 7
cp out/meeting.plaud.json out/meeting.diar.plaud.json        # match overwrites unmatched clusters
plaudio match meeting.ogg out/meeting.plaud.json --threshold 0.55 --report
python cluster_vote.py out/meeting.diar.plaud.json out/meeting.plaud.json
plaudio label meeting.ogg out/meeting.diar.plaud.json \
  --batch-label "SPEAKER_03=Alice Smith,SPEAKER_05=Bob Jones"  # from the vote + the ladder
plaudio db ingest out/meeting.diar.plaud.json --meeting-id <id> --date YYYY-MM-DD --title "..."
```

Run one recording at a time; both models are memory-heavy.
