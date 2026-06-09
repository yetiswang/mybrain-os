#!/usr/bin/env python3.13
"""
enroll_speaker.py — Enrol a stakeholder voice profile from a recording.

Reuses pyannote-audio 3.1's diarization-with-embedding output:
  - Run diarisation on the audio (or audio segment)
  - Pick the SPEAKER_NN cluster that overlaps the [--start, --end] window most
  - Save its mean embedding under the given name

No separate embedding model needed — DiarizeOutput.speaker_embeddings already
provides per-speaker mean embeddings. Cuts one gated-model dependency.

Usage:
  enroll_speaker.py <audio> --name "Alice Smith" --start 12.5 --end 45.0
                    [--notes "context"]

Profiles stored at:
  ~/.local/share/plaud/voice-profiles.json
  (override with PLAUD_PROFILES env var)
"""
from __future__ import annotations

import argparse, datetime, json, os, pathlib, subprocess, sys, tempfile


_env_profiles = os.environ.get("PLAUD_PROFILES")
PROFILES_PATH = (
    pathlib.Path(_env_profiles).expanduser()
    if _env_profiles
    else pathlib.Path.home() / ".local/share/plaud/voice-profiles.json"
)


def run_diarization_with_embeddings(audio_path, hf_token):
    """Run pyannote-3.1 diarisation and return (annotation_iter, embeddings_dict)."""
    from pyannote.audio import Pipeline
    import torch
    import soundfile as sf

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        token=hf_token,
    )
    if torch.backends.mps.is_available():
        pipeline.to(torch.device("mps"))

    # Convert audio to 16 kHz mono WAV first (see transcribe_plaud.py for why).
    wav_path = pathlib.Path(tempfile.mktemp(suffix=".wav"))
    conv = subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(audio_path), "-ac", "1", "-ar", "16000", str(wav_path)
    ], capture_output=True, text=True)
    if conv.returncode != 0:
        sys.exit(f"ffmpeg pre-convert failed: {conv.stderr}")
    samples, sample_rate = sf.read(str(wav_path))
    waveform = torch.from_numpy(samples).float()
    if waveform.ndim == 1:
        waveform = waveform.unsqueeze(0)
    diary = pipeline({"waveform": waveform, "sample_rate": sample_rate},
                     return_embeddings=True)
    wav_path.unlink(missing_ok=True)
    return diary


def best_speaker_for_window(diary, start_s, end_s):
    """Pick the SPEAKER_NN label with maximum cumulative overlap in [start, end]."""
    if start_s is None or end_s is None:
        # No window given: pick the most-talkative speaker
        totals = {}
        for turn, _, sp in diary.speaker_diarization.itertracks(yield_label=True):
            totals[sp] = totals.get(sp, 0.0) + (turn.end - turn.start)
        if not totals:
            return None
        return max(totals.items(), key=lambda kv: kv[1])[0]
    totals = {}
    for turn, _, sp in diary.speaker_diarization.itertracks(yield_label=True):
        ov = max(0.0, min(turn.end, end_s) - max(turn.start, start_s))
        if ov > 0:
            totals[sp] = totals.get(sp, 0.0) + ov
    if not totals:
        return None
    return max(totals.items(), key=lambda kv: kv[1])[0]


def load_profiles():
    if PROFILES_PATH.exists():
        return json.loads(PROFILES_PATH.read_text())
    return {"version": 1, "profiles": []}


def save_profiles(db):
    PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILES_PATH.write_text(json.dumps(db, indent=2))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("audio", type=pathlib.Path)
    p.add_argument("--name", required=True)
    p.add_argument("--start", type=float, default=None)
    p.add_argument("--end", type=float, default=None)
    p.add_argument("--notes", default="")
    p.add_argument("--hf-token-file", type=pathlib.Path,
                   default=pathlib.Path.home() / ".huggingface/token")
    p.add_argument("--replace", action="store_true",
                   help="Replace all existing samples for this name")
    args = p.parse_args()

    if not args.audio.exists():
        sys.exit(f"audio not found: {args.audio}")
    if not args.hf_token_file.exists():
        sys.exit(f"HF token not found at {args.hf_token_file}")
    hf_token = args.hf_token_file.read_text().strip()

    print(f"Running diarisation with embeddings on {args.audio.name} ...")
    diary = run_diarization_with_embeddings(args.audio, hf_token)
    n_speakers = len({s for _, _, s in diary.speaker_diarization.itertracks(yield_label=True)})
    print(f"  found {n_speakers} speaker(s)")

    target_label = best_speaker_for_window(diary, args.start, args.end)
    if target_label is None:
        sys.exit("No speaker found overlapping the requested window")
    print(f"  matched window to {target_label}")

    # diary.speaker_embeddings is a numpy array, shape (n_speakers, embedding_dim)
    # Speaker labels (SPEAKER_00, SPEAKER_01, ...) index into it.
    embeddings = diary.speaker_embeddings
    if embeddings is None:
        sys.exit("pyannote did not return speaker_embeddings; check return_embeddings=True")
    # Map SPEAKER_NN label -> index
    speaker_labels = sorted({s for _, _, s in diary.speaker_diarization.itertracks(yield_label=True)})
    idx = speaker_labels.index(target_label)
    vec = [float(x) for x in embeddings[idx].flatten().tolist()]
    print(f"  embedding dim={len(vec)}")

    db = load_profiles()
    if args.replace:
        db["profiles"] = [pr for pr in db["profiles"] if pr["name"] != args.name]
    db["profiles"].append({
        "name": args.name,
        "embedding": vec,
        "model": "pyannote/speaker-diarization-3.1 (DiarizeOutput.speaker_embeddings)",
        "enrolled_from": str(args.audio),
        "enrolled_at": datetime.datetime.utcnow().isoformat() + "Z",
        "start_s": args.start,
        "end_s": args.end,
        "matched_speaker_label": target_label,
        "n_speakers_in_audio": n_speakers,
        "notes": args.notes,
    })
    save_profiles(db)

    names = sorted({pr["name"] for pr in db["profiles"]})
    print(f"  saved -> {PROFILES_PATH}")
    print(f"\nProfile DB: {len(db['profiles'])} samples across {len(names)} people")
    print(f"Enrolled people: {', '.join(names)}")


if __name__ == "__main__":
    main()
