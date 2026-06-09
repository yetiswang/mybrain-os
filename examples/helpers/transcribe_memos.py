#!/usr/bin/env python3.13
"""
transcribe_memos.py — Find today's Voice Memos and return their transcripts.

Priority:
  1. Apple's built-in transcript (from JSON sidecar or .transcript file) — instant, no model
  2. mlx-whisper (Apple Silicon optimized) — fallback if Apple transcript not yet generated

Usage:
    python3 transcribe_memos.py [--days N] [--force] [--language zh|en|auto]

Output: JSON array to stdout, progress to stderr.

Requires Full Disk Access for Terminal in:
    System Settings > Privacy & Security > Full Disk Access
"""

import os
import sys
import json
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime, timedelta

RECORDINGS_DIR = Path.home() / "Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings"
DB_PATH = Path.home() / "Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings/CloudRecordings.db"
STATE_FILE = Path(os.environ.get(
    "VOICE_MEMOS_STATE",
    str(Path.home() / ".local/share/voice-memos-state.json"),
))


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {"processed": {}}
    return {"processed": {}}


def save_state(state):
    tmp = STATE_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(STATE_FILE)


def check_access():
    if not RECORDINGS_DIR.exists():
        print(
            "[ERROR] Cannot access Voice Memos directory.\n"
            "[ERROR] Grant Full Disk Access to your terminal:\n"
            "[ERROR] System Settings > Privacy & Security > Full Disk Access",
            file=sys.stderr,
        )
        sys.exit(1)


def find_memos(days=1):
    """Find .m4a files modified within N days."""
    cutoff = datetime.now() - timedelta(days=days)
    memos = []

    for f in sorted(RECORDINGS_DIR.glob("**/*.m4a")):
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        if mtime < cutoff:
            continue

        # Try to get human-readable name from companion JSON sidecar
        sidecar = f.with_suffix(".json")
        name = f.stem
        if sidecar.exists():
            try:
                meta = json.loads(sidecar.read_text())
                name = meta.get("customLabel") or meta.get("name") or f.stem
            except Exception:
                pass

        memos.append({"path": str(f), "name": name, "mtime": mtime.isoformat()})

    return memos


def get_apple_transcript_from_sidecar(audio_path: Path):
    """Try to read Apple's transcript from companion files."""
    # Option 1: .transcript file alongside the .m4a
    transcript_file = audio_path.with_suffix(".transcript")
    if transcript_file.exists():
        try:
            data = json.loads(transcript_file.read_text())
            segments = data.get("transcript", {}).get("segments", [])
            if segments:
                return " ".join(s.get("substring", "") for s in segments).strip()
            text = data.get("transcribedString", "")
            if text:
                return text.strip()
        except Exception:
            pass

    # Option 2: transcript embedded in JSON sidecar
    sidecar = audio_path.with_suffix(".json")
    if sidecar.exists():
        try:
            meta = json.loads(sidecar.read_text())
            text = meta.get("transcript", "") or meta.get("transcribedString", "")
            if text:
                return text.strip()
        except Exception:
            pass

    return None


def get_apple_transcript_from_db(audio_path: Path):
    """Try to read Apple's transcript from VoiceMemos SQLite database."""
    if not DB_PATH.exists():
        return None
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        filename = audio_path.name
        for query in [
            "SELECT ZTRANSCRIPT FROM ZCLOUDRECORDING WHERE ZPATH LIKE ?",
            "SELECT ZTRANSCRIBEDSTRING FROM ZCLOUDRECORDING WHERE ZPATH LIKE ?",
        ]:
            try:
                cursor.execute(query, (f"%{filename}%",))
                row = cursor.fetchone()
                if row and row[0]:
                    conn.close()
                    return str(row[0]).strip()
            except sqlite3.OperationalError:
                continue
        conn.close()
    except Exception:
        pass
    return None


MLX_MODEL = "mlx-community/whisper-small-mlx"
_mlx_model_cache = None

# Post-processing dictionary for known proper nouns that whisper-small consistently
# misrecognises. Case-insensitive matching, longest-match-first replacement.
# Populate with the names, institution names, and technical terms that appear in
# your recordings. Add entries as new errors surface in transcription reviews.
#
# Format: "whisper_output": "Correct Spelling"
# Longer keys are matched first (automatic, by sort key).
PROPER_NOUN_CORRECTIONS = {
    # Example entries — replace with your own:
    # "john smyth": "John Smith",
    # "my company nm": "MyCompany NM",
}


def postprocess_transcript(text: str) -> str:
    """Apply proper noun corrections to raw whisper transcript."""
    import re
    corrections_applied = []
    for wrong, right in sorted(PROPER_NOUN_CORRECTIONS.items(), key=lambda x: -len(x[0])):
        pattern = re.compile(re.escape(wrong), re.IGNORECASE)
        if pattern.search(text):
            text = pattern.sub(right, text)
            corrections_applied.append(f"{wrong} -> {right}")
    if corrections_applied:
        joined = ", ".join(corrections_applied)
        print(f"[postprocess] {len(corrections_applied)} corrections: {joined}", file=sys.stderr)
    return text


def transcribe_with_mlx(audio_path: str, language: str = "auto"):
    """Transcribe using mlx-whisper (Apple Silicon optimized, on-device, no tokens)."""
    global _mlx_model_cache
    try:
        import mlx_whisper
    except ImportError:
        print("[ERROR] mlx-whisper not installed. Run: pip install mlx-whisper", file=sys.stderr)
        sys.exit(1)

    lang = None if language == "auto" else language
    result = mlx_whisper.transcribe(audio_path, path_or_hf_repo=MLX_MODEL, language=lang)
    detected = result.get("language", "?")
    text = result.get("text", "").strip()
    text = postprocess_transcript(text)
    print(f"[mlx] language={detected} | length={len(text)} chars", file=sys.stderr)
    return text


def main():
    parser = argparse.ArgumentParser(description="Transcribe Apple Voice Memos")
    parser.add_argument("--days", type=int, default=1, help="Days back to scan (default: 1)")
    parser.add_argument("--force", action="store_true", help="Re-process already processed memos")
    parser.add_argument(
        "--language",
        default="auto",
        help="Language hint for whisper fallback: zh, en, auto (default: auto)",
    )
    args = parser.parse_args()

    check_access()

    state = load_state()
    memos = find_memos(days=args.days)

    if not memos:
        print(f"[info] No voice memos found in the last {args.days} day(s).", file=sys.stderr)
        print("[]")
        return

    results = []
    for memo in memos:
        memo_id = memo["path"]

        if not args.force and memo_id in state["processed"]:
            print(f"[skip] Already processed: {memo['name']}", file=sys.stderr)
            continue

        print(f"[memo] {memo['name']} ({memo['mtime'][:16]})", file=sys.stderr)
        audio_path = Path(memo["path"])

        transcript = get_apple_transcript_from_sidecar(audio_path)
        source = "apple"

        if not transcript:
            transcript = get_apple_transcript_from_db(audio_path)

        if not transcript:
            print(f"[mlx-whisper] No sidecar transcript, transcribing with mlx-whisper...", file=sys.stderr)
            transcript = transcribe_with_mlx(str(audio_path), language=args.language)
            source = "mlx-whisper"

        print(f"[done] Source: {source} | Length: {len(transcript)} chars", file=sys.stderr)

        result = {
            "name": memo["name"],
            "mtime": memo["mtime"],
            "path": memo["path"],
            "source": source,
            "transcript": transcript,
        }
        results.append(result)

        state["processed"][memo_id] = {
            "name": memo["name"],
            "mtime": memo["mtime"],
            "transcribed_at": datetime.now().isoformat(),
            "source": source,
        }

    save_state(state)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
