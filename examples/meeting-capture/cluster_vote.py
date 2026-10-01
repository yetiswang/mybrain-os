"""Cluster vote: name each diarisation cluster by the voice-bank matches inside it.

The sliding voice-bank matcher labels short windows and leaves many of them
`Unknown`. The diariser groups segments by speaker but does not know names.
This script lines the two files up segment by segment and, for every
diarisation cluster, totals the seconds each enrolled name won inside it.

    python cluster_vote.py <diarised.plaud.json> <matched.plaud.json> [--min-share 0.15]

Both files must come from the same transcript (same segments, same order):
copy the diarised file before running `plaudio match`, which rewrites it.

Output: one line per cluster with its talk time and the top names, plus a
suggested `--batch-label` string for clusters where one name has a clear
lead. A suggestion is a hypothesis; check it against the calendar and the
content before applying it.
"""
import argparse
import collections
import json


def segments(path):
    data = json.load(open(path))
    return data if isinstance(data, list) else data["segments"]


def seconds(seg):
    d = seg["end_time"] - seg["start_time"]
    return d / 1000 if d > 1000 else d  # plaud-shaped files may use ms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("diarised")
    ap.add_argument("matched")
    ap.add_argument("--min-share", type=float, default=0.15,
                    help="minimum share of a cluster's talk time the top name must win")
    args = ap.parse_args()

    diar, match = segments(args.diarised), segments(args.matched)
    if len(diar) != len(match):
        raise SystemExit("segment counts differ: the files are not from the same transcript")

    votes = collections.defaultdict(collections.Counter)
    talk = collections.Counter()
    for d, m in zip(diar, match):
        s = seconds(d)
        talk[d["speaker"]] += s
        votes[d["speaker"]][m["speaker"]] += s

    suggestions = []
    for cluster, total in talk.most_common():
        named = [(n, v) for n, v in votes[cluster].most_common() if n != "Unknown"]
        top = ", ".join(f"{n} {v / 60:.1f} min" for n, v in votes[cluster].most_common(4))
        print(f"{cluster}: {total / 60:.1f} min -> {top}")
        if named and named[0][1] / total >= args.min_share and \
                (len(named) == 1 or named[0][1] >= 3 * named[1][1]):
            suggestions.append(f"{cluster}={named[0][0]}")

    if suggestions:
        print("\nsuggested: --batch-label \"" + ",".join(suggestions) + "\"")


if __name__ == "__main__":
    main()
