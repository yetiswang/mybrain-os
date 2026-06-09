#!/usr/bin/env python3.13
"""
transcribe_plaud.py — Local transcription + diarisation for Plaud (and other) audio.

Pipeline:
  STEP A — ASR via mlx-whisper (MLX-accelerated, ~6x realtime on Apple Silicon)
           with initial prompt (stakeholder vocabulary) + hallucination-silence
           threshold (prevents the "Yeah" loop on quiet tails).
  STEP B — Diarisation via pyannote-audio 3.1 directly (torch backend on MPS
           when available). No whisperx wrapper.
  STEP C — Merge speaker labels onto ASR segments by max-overlap.
  STEP D — Emit JSON in Plaud-compatible shape so /plaud-ingest can swap in.

Usage:
  transcribe_plaud.py <audio> [--out-dir DIR] [--language en]
                       [--num-speakers N] [--min-speakers N --max-speakers N]
                       [--vocab-file FILE] [--hf-token-file FILE] [--model MODEL]
                       [--skip-diarize]

Vocab default: plaud-vocab.example.txt alongside this script (one term per line).
               Override with --vocab-file or PLAUD_VOCAB env var.
HF token default: ~/.huggingface/token.
"""
from __future__ import annotations

import argparse, json, pathlib, subprocess, sys, time


def load_vocab(vocab_file):
    if not vocab_file.exists():
        return ""
    terms = [line.strip() for line in vocab_file.read_text().splitlines() if line.strip()]
    return ", ".join(terms) + "."


def run_mlx_whisper(audio, out_dir, language, vocab_prompt, model):
    cmd = [
        "mlx_whisper", str(audio),
        "--model", model,
        "--language", language,
        "--output-format", "json",
        "--output-dir", str(out_dir),
        "--condition-on-previous-text", "False",
        "--hallucination-silence-threshold", "2.0",
    ]
    if vocab_prompt:
        cmd += ["--initial-prompt", vocab_prompt]
    t0 = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.time() - t0
    if result.returncode != 0:
        sys.stderr.write(f"mlx_whisper failed (exit {result.returncode}):\n{result.stderr}\n")
        sys.exit(1)
    out_file = out_dir / f"{audio.stem}.json"
    if not out_file.exists():
        sys.exit(f"mlx_whisper completed but no output at {out_file}")
    with open(out_file) as f:
        data = json.load(f)
    return data.get("segments", []), elapsed


def run_diarization(audio, hf_token, num_speakers, min_speakers, max_speakers):
    from pyannote.audio import Pipeline
    import torch

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        token=hf_token,
    )
    if torch.backends.mps.is_available():
        pipeline.to(torch.device("mps"))

    kwargs = {}
    if num_speakers is not None:
        kwargs["num_speakers"] = num_speakers
    else:
        if min_speakers is not None:
            kwargs["min_speakers"] = min_speakers
        if max_speakers is not None:
            kwargs["max_speakers"] = max_speakers

    # Bypass both torchcodec AND torchaudio backend issues by:
    #   (1) ffmpeg-convert MP3 -> 16 kHz mono WAV in a temp file
    #   (2) loading with soundfile (always available)
    #   (3) wrapping as torch.Tensor and passing dict to pyannote pipeline
    # Why: pyannote-audio 4.x defaults to torchcodec (libavutil 56/57, ffmpeg 4/5);
    # Homebrew has ffmpeg 8 (libavutil 60+). torchaudio 2.8+ no longer bundles
    # audio backends. soundfile is the lightweight, reliable replacement.
    import tempfile
    import soundfile as sf
    import torch
    wav_path = pathlib.Path(tempfile.mktemp(suffix=".wav"))
    conv = subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(audio), "-ac", "1", "-ar", "16000", str(wav_path)
    ], capture_output=True, text=True)
    if conv.returncode != 0:
        sys.exit(f"ffmpeg pre-convert failed: {conv.stderr}")
    samples, sample_rate = sf.read(str(wav_path))
    waveform = torch.from_numpy(samples).float()
    if waveform.ndim == 1:
        waveform = waveform.unsqueeze(0)  # (1, n_samples) mono
    t0 = time.time()
    diary = pipeline({"waveform": waveform, "sample_rate": sample_rate}, **kwargs)
    elapsed = time.time() - t0
    wav_path.unlink(missing_ok=True)
    turns = [(turn.start, turn.end, speaker)
             for turn, _, speaker in diary.speaker_diarization.itertracks(yield_label=True)]
    return turns, elapsed


# Common Plaud/Whisper ASR mishearings -> correct spellings, applied post-ASR.
# Add your own entries here as new failure modes are observed.
# Format: ("wrong", "right") — plain string replacement, case-sensitive.
NAME_CORRECTIONS: list[tuple[str, str]] = [
    # Examples — replace with corrections relevant to your recurring meetings:
    # ("Rebecka", "Rebecca"),
    # ("characterization", "characterisation"),
]


def apply_corrections(text):
    """Apply NAME_CORRECTIONS to a piece of text."""
    for wrong, right in NAME_CORRECTIONS:
        text = text.replace(wrong, right)
    return text


def merge_speakers(asr_segments, diary_turns):
    out = []
    for seg in asr_segments:
        s_start = float(seg.get("start", 0))
        s_end = float(seg.get("end", s_start))
        best_speaker = None
        best_overlap = 0.0
        for d_start, d_end, speaker in diary_turns:
            overlap = max(0.0, min(s_end, d_end) - max(s_start, d_start))
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = speaker
        out.append({
            "content": apply_corrections((seg.get("text") or "").strip()),
            "start_time": int(s_start * 1000),
            "end_time": int(s_end * 1000),
            "speaker": best_speaker or "Unknown",
            "original_speaker": best_speaker or "Unknown",
            "embeddingKey": None,
        })
    return out


def main():
    p = argparse.ArgumentParser(description="Local Plaud-compatible transcription + diarisation.")
    p.add_argument("audio", type=pathlib.Path)
    p.add_argument("--out-dir", type=pathlib.Path, default=pathlib.Path("."))
    p.add_argument("--language", default="en")
    p.add_argument("--num-speakers", type=int, default=None)
    p.add_argument("--min-speakers", type=int, default=None)
    p.add_argument("--max-speakers", type=int, default=None)
    p.add_argument("--vocab-file", type=pathlib.Path,
                   default=pathlib.Path(__file__).parent / "plaud-vocab.example.txt")
    p.add_argument("--hf-token-file", type=pathlib.Path,
                   default=pathlib.Path.home() / ".huggingface/token")
    p.add_argument("--model", default="mlx-community/whisper-large-v3-mlx")
    p.add_argument("--skip-diarize", action="store_true")
    args = p.parse_args()

    if not args.audio.exists():
        sys.exit(f"audio not found: {args.audio}")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    vocab_prompt = load_vocab(args.vocab_file)
    if vocab_prompt:
        print(f"[{time.strftime('%H:%M:%S')}] Loaded {vocab_prompt.count(',') + 1} vocab terms")

    print(f"[{time.strftime('%H:%M:%S')}] STEP A - mlx-whisper ASR on {args.audio.name}")
    asr_segments, asr_time = run_mlx_whisper(args.audio, args.out_dir, args.language,
                                              vocab_prompt, args.model)
    print(f"  ok {len(asr_segments)} segments in {asr_time:.1f}s")

    if args.skip_diarize:
        merged = [{
            "content": apply_corrections((s.get("text") or "").strip()),
            "start_time": int(float(s.get("start", 0)) * 1000),
            "end_time": int(float(s.get("end", 0)) * 1000),
            "speaker": "Speaker 1",
            "original_speaker": "Speaker 1",
            "embeddingKey": None,
        } for s in asr_segments]
        diary_time = 0.0
        n_speakers = 1
    else:
        if not args.hf_token_file.exists():
            sys.exit(f"HF token not found at {args.hf_token_file}; pass --skip-diarize.")
        hf_token = args.hf_token_file.read_text().strip()

        print(f"[{time.strftime('%H:%M:%S')}] STEP B - pyannote-audio 3.1 diarisation")
        diary_turns, diary_time = run_diarization(args.audio, hf_token,
                                                   args.num_speakers,
                                                   args.min_speakers,
                                                   args.max_speakers)
        n_speakers = len({s for _, _, s in diary_turns})
        print(f"  ok {len(diary_turns)} turns, {n_speakers} speakers in {diary_time:.1f}s")

        print(f"[{time.strftime('%H:%M:%S')}] STEP C - merge")
        merged = merge_speakers(asr_segments, diary_turns)

    out_json = args.out_dir / f"{args.audio.stem}.plaud.json"
    meta = {
        "asr_time_s": round(asr_time, 2),
        "diarize_time_s": None if args.skip_diarize else round(diary_time, 2),
        "total_time_s": round(asr_time + diary_time, 2),
        "n_speakers": n_speakers,
        "language": args.language,
        "model": args.model,
        "source": str(args.audio),
        "produced_by": "transcribe_plaud.py",
    }
    with open(out_json, "w") as f:
        json.dump({"meta": meta, "segments": merged}, f, indent=2)
    print(f"  ok wrote {out_json}")
    print(f"\nTotal pipeline: {meta['total_time_s']}s")


if __name__ == "__main__":
    main()
