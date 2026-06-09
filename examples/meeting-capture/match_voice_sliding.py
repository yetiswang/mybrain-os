#!/usr/bin/env python3
"""
match_voice_sliding.py — Voice-bank-first sliding-window speaker labelling.

Re-labels the JSON produced by transcribe_plaud.py using a voice bank of
enrolled speaker embeddings. Bypasses pyannote's cluster-then-merge failure
on meetings with 4+ close-voice speakers by doing per-window cosine matching
against the enrolled profiles instead.

Algorithm:
  1. Slide a 2s window (1s hop) across the audio.
  2. Embed each window via pyannote/wespeaker-voxceleb-resnet34-LM (the same
     model used during enrolment — dim-compatible).
  3. Cosine-match each window against the averaged per-name bank embeddings.
  4. Coalesce same-label runs.
  5. For each transcript segment, assign the run that covers the most overlap.

Unmatched windows (cosine < threshold) stay "Unknown".

Usage:
  match_voice_sliding.py <audio> <transcript.plaud.json>
                         [--profiles FILE] [--threshold 0.55] [--report]
                         [--out FILE]

Profiles default: ~/.local/share/plaud/voice-profiles.json
                  (override with PLAUD_PROFILES env var)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import sys
import warnings

DEFAULT_THRESHOLD = 0.55
DEFAULT_WINDOW_S = 2.0
DEFAULT_HOP_S = 1.0


# ---------------------------------------------------------------------------
# Vector helpers (no numpy dependency)
# ---------------------------------------------------------------------------

def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def average_by_name(profiles: list[dict]) -> dict[str, list[float]]:
    """Average all embeddings under each name.

    Multiple samples per name are intentional — averaging builds a more robust
    mean embedding than a single enrolment would.
    """
    by_name: dict[str, list[list[float]]] = {}
    for p in profiles:
        name = p.get("name", "")
        emb = p.get("embedding", [])
        if name and emb:
            by_name.setdefault(name, []).append(emb)
    out: dict[str, list[float]] = {}
    for name, embs in by_name.items():
        dim = len(embs[0])
        s = [0.0] * dim
        for e in embs:
            for i, v in enumerate(e):
                s[i] += v
        n = len(embs)
        out[name] = [v / n for v in s]
    return out


def coalesce_runs(
    window_labels: list[tuple[float, float, str]],
) -> list[tuple[float, float, str]]:
    """Merge consecutive same-label windows into (start, end, label) runs."""
    if not window_labels:
        return []
    runs = []
    cs, ce, cl = window_labels[0]
    for s, e, l in window_labels[1:]:
        if l == cl:
            ce = e
        else:
            runs.append((cs, ce, cl))
            cs, ce, cl = s, e, l
    runs.append((cs, ce, cl))
    return runs


def assign_speaker_to_segment(
    seg: dict, runs: list[tuple[float, float, str]]
) -> str:
    """Pick the run that covers the most of [seg.start_time, seg.end_time] (ms)."""
    s_start = seg["start_time"] / 1000.0
    s_end = seg["end_time"] / 1000.0
    best_overlap = 0.0
    best_label: str | None = None
    for rs, re_, rl in runs:
        if re_ < s_start or rs > s_end:
            continue
        ovl = min(re_, s_end) - max(rs, s_start)
        if ovl > best_overlap:
            best_overlap = ovl
            best_label = rl
    return best_label or "Unknown"


# ---------------------------------------------------------------------------
# HF token resolution
# ---------------------------------------------------------------------------

def _get_hf_token() -> str | None:
    tok = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    if tok:
        return tok.strip()
    p = pathlib.Path.home() / ".huggingface" / "token"
    if p.exists():
        return p.read_text().strip() or None
    return None


# ---------------------------------------------------------------------------
# Sliding-window matching
# ---------------------------------------------------------------------------

def sliding_match(
    audio_path: pathlib.Path,
    means: dict[str, list[float]],
    threshold: float,
    window_s: float = DEFAULT_WINDOW_S,
    hop_s: float = DEFAULT_HOP_S,
) -> tuple[list[tuple[float, float, str]], dict]:
    """Slide across audio, cosine-match each window. Returns (window_labels, stats)."""
    if not means:
        return [], {"note": "voice bank empty"}

    hf_token = _get_hf_token()
    from pyannote.audio import Model, Inference

    warnings.filterwarnings("ignore")
    try:
        model = Model.from_pretrained(
            "pyannote/wespeaker-voxceleb-resnet34-LM", token=hf_token
        )
    except Exception as e:
        raise RuntimeError(
            "Failed to load pyannote/wespeaker-voxceleb-resnet34-LM. "
            "If this is a 403/GatedRepoError, accept the model terms at "
            "https://huggingface.co/pyannote/wespeaker-voxceleb-resnet34-LM "
            "with the same HF account whose token is in ~/.huggingface/token "
            "or HF_TOKEN. Original error: " + str(e)
        ) from e

    try:
        import torch
        if torch.backends.mps.is_available():
            model.to(torch.device("mps"))
    except Exception:
        pass

    inf = Inference(model, window="sliding", duration=window_s, step=hop_s)
    sliding = inf(str(audio_path))

    bank_dim = len(next(iter(means.values())))
    window_labels: list[tuple[float, float, str]] = []
    n_matched = 0
    first_window_dim: int | None = None

    for chunk, emb in zip(sliding.sliding_window, sliding.data):
        emb_list = (
            [float(x) for x in emb.flatten().tolist()]
            if hasattr(emb, "flatten")
            else list(emb)
        )
        if first_window_dim is None:
            first_window_dim = len(emb_list)
            if first_window_dim != bank_dim:
                raise RuntimeError(
                    f"Voice bank / embedding dim mismatch: bank={bank_dim}-dim, "
                    f"current model emits {first_window_dim}-dim. "
                    f"Re-enrol speakers with enroll_speaker.py under the current "
                    f"pyannote version to rebuild a compatible bank."
                )
        best_name = None
        best_cos = -1.0
        for name, mean in means.items():
            c = cosine(emb_list, mean)
            if c > best_cos:
                best_cos = c
                best_name = name
        if best_cos >= threshold:
            window_labels.append((chunk.start, chunk.end, best_name))
            n_matched += 1
        else:
            window_labels.append((chunk.start, chunk.end, "Unknown"))

    stats = {
        "n_windows": len(window_labels),
        "n_matched": n_matched,
        "match_rate": round(n_matched / len(window_labels), 3) if window_labels else 0,
    }
    return window_labels, stats


# ---------------------------------------------------------------------------
# Profiles I/O (legacy plaud-voice-profiles.json schema)
# ---------------------------------------------------------------------------

def load_profiles(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text())
    # Support both {"profiles": [...]} and plain list
    if isinstance(raw, dict):
        return raw.get("profiles", [])
    return raw


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def default_profiles_path() -> pathlib.Path:
    env = os.environ.get("PLAUD_PROFILES")
    if env:
        return pathlib.Path(env).expanduser()
    return pathlib.Path.home() / ".local/share/plaud/voice-profiles.json"


def main() -> None:
    p = argparse.ArgumentParser(
        description="Relabel a transcribe_plaud.py JSON using a voice bank."
    )
    p.add_argument("audio", type=pathlib.Path, help="Original audio file")
    p.add_argument("transcript", type=pathlib.Path,
                   help="JSON produced by transcribe_plaud.py")
    p.add_argument("--profiles", type=pathlib.Path,
                   default=None,
                   help="Voice-profiles JSON (default: $PLAUD_PROFILES or "
                        "~/.local/share/plaud/voice-profiles.json)")
    p.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                   help=f"Cosine similarity threshold (default: {DEFAULT_THRESHOLD})")
    p.add_argument("--out", type=pathlib.Path, default=None,
                   help="Output JSON path (default: <transcript stem>.relabelled.json)")
    p.add_argument("--report", action="store_true",
                   help="Print per-segment label changes to stdout")
    args = p.parse_args()

    if not args.audio.exists():
        sys.exit(f"audio not found: {args.audio}")
    if not args.transcript.exists():
        sys.exit(f"transcript not found: {args.transcript}")

    profiles_path = args.profiles or default_profiles_path()
    profiles = load_profiles(profiles_path)
    if not profiles:
        sys.exit(
            f"No voice profiles found at {profiles_path}.\n"
            "Run enroll_speaker.py first, or set --profiles / PLAUD_PROFILES."
        )

    means = average_by_name(profiles)
    enrolled = sorted(means.keys())
    print(f"Voice bank: {len(profiles)} samples, {len(enrolled)} people: "
          f"{', '.join(enrolled)}")

    data = json.loads(args.transcript.read_text())
    segments = data.get("segments", [])
    print(f"Transcript: {len(segments)} segments from {args.transcript.name}")

    print(f"Running sliding match (threshold={args.threshold}) ...")
    window_labels, stats = sliding_match(
        args.audio, means, threshold=args.threshold
    )
    runs = coalesce_runs(window_labels)
    print(f"  {stats['n_windows']} windows, {stats['n_matched']} matched "
          f"({stats['match_rate']:.1%}), {len(runs)} runs")

    n_relabelled = 0
    for seg in segments:
        new_label = assign_speaker_to_segment(seg, runs)
        old_label = seg["speaker"]
        if "original_speaker" not in seg:
            seg["original_speaker"] = old_label
        if old_label != new_label:
            n_relabelled += 1
            if args.report:
                t = seg["start_time"] / 1000
                print(f"  [{t:.1f}s] {old_label} -> {new_label}: "
                      f"{seg['content'][:60]!r}")
        seg["speaker"] = new_label

    out_path = args.out or args.transcript.with_suffix("").with_suffix(
        ".relabelled.json"
    )
    data["segments"] = segments
    data.setdefault("meta", {})["sliding_match"] = stats
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"\n{n_relabelled}/{len(segments)} segments relabelled -> {out_path}")


if __name__ == "__main__":
    main()
