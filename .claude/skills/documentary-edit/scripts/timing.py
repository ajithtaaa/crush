"""Time the narration: when each sentence of the voiceover is spoken.

  python timing.py --voice projects/NAME/voice.mp3 --script projects/NAME/script.txt --out projects/NAME/timing.json
With faster-whisper installed (optional, see SETUP.md) the times come from the actual recording, word by word, and are mapped
onto the script's sentences. Without it the sentences are spread over the recording by length; the file then says
"estimated": true and every cut must be checked by ear or against the waveform before it is trusted.
Output: {"duration": s, "estimated": bool, "sentences": [{"i", "text", "start", "end"}], "words": [{"w", "start", "end"}]}
"""
import argparse
import json
import os
import re
import subprocess
from difflib import SequenceMatcher
from pathlib import Path


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


ABBREV = {"mr", "mrs", "ms", "dr", "st", "jr", "sr", "vs", "etc", "mt", "inc", "co", "ltd", "u.s", "u.k", "e.g", "i.e",
          "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec", "gen", "col", "sgt", "lt", "prof"}
END = re.compile(r"^(.*?)([.!?]+)([\"'”’)\]]*)$")
STARTS = re.compile(r"^[\"'“‘(\[]*[A-Z0-9]")


def sentences(text):
    """Split narration into sentences. A sentence ends on . ! ? (plus closing quotes/brackets) when the next word starts a new
    sentence (capital letter or digit), and not on Dr. / U.S. / Jan. / initials."""
    toks = re.sub(r"\s+", " ", text).strip().split(" ")
    out, cur = [], []
    for i, tok in enumerate(toks):
        cur.append(tok)
        m = END.match(tok)
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        if not m or (nxt is not None and not STARTS.match(nxt)):
            continue
        word = m.group(1).lower().lstrip("\"'“‘(")
        if m.group(2) == "." and (word in ABBREV or re.fullmatch(r"[a-z]", word)):
            continue   # Dr. / U.S. / J. : not a sentence end
        out.append(" ".join(cur)); cur = []
    if cur:
        out.append(" ".join(cur))
    return [s for s in out if s.strip()]


def norm(w):
    return re.sub(r"[^a-z0-9]", "", w.lower())


def whisper_words(voice):
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    from faster_whisper import WhisperModel  # optional dependency
    model = WhisperModel("base", device="cpu", compute_type="int8", cpu_threads=4)   # multilingual
    segs, _ = model.transcribe(str(voice), word_timestamps=True, vad_filter=True)
    return [dict(w=w.word.strip(), start=round(w.start, 3), end=round(w.end, 3)) for s in segs for w in (s.words or [])]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--voice", required=True); ap.add_argument("--script", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    dur = duration(a.voice)
    sents = sentences(Path(a.script).read_text(encoding="utf-8-sig"))
    note = ""
    try:
        words = whisper_words(a.voice)
    except Exception as e:  # noqa: BLE001  (not installed, model download failed, missing runtime DLL: fall back)
        words, note = [], f"faster-whisper unavailable ({type(e).__name__}: {str(e)[:120]})"
    lens = [max(1, len(s)) for s in sents]
    starts = [None] * len(sents)
    matched = 0.0
    if words:
        sw = [(i, norm(w)) for i, s in enumerate(sents) for w in s.split() if norm(w)]
        hw = [norm(w["w"]) for w in words]
        sm = SequenceMatcher(None, [x[1] for x in sw], hw, autojunk=False)
        for blk in sm.get_matching_blocks():
            for k in range(blk.size):
                si = sw[blk.a + k][0]
                if starts[si] is None:
                    starts[si] = words[blk.b + k]["start"]
        matched = sum(b.size for b in sm.get_matching_blocks()) / max(1, len(sw))
        if matched < 0.5:
            note = f"only {matched:.0%} of the script matched the recording (wrong file, another language, or a rewrite)"
            starts = [None] * len(sents)
    estimated = all(x is None for x in starts)
    if estimated:
        starts[0] = 0.0
    starts[0] = 0.0 if starts[0] is None or starts[0] < 1.5 else starts[0]
    i = 0
    while i < len(sents):                     # spread runs of untimed sentences over their gap by length
        if starts[i] is None:
            j = i
            while j < len(sents) and starts[j] is None:
                j += 1
            t0, t1 = starts[i - 1], (starts[j] if j < len(sents) else dur)
            span = sum(lens[i - 1:j])
            acc = t0
            for k in range(i, j):
                acc += (t1 - t0) * lens[k - 1] / span
                starts[k] = round(acc, 3)
            i = j
        i += 1
    for k in range(1, len(starts)):           # keep them in order
        starts[k] = max(starts[k], starts[k - 1] + 0.2)
    res = dict(duration=round(dur, 3), estimated=estimated, matched=round(matched, 3), note=note, sentences=[], words=words)
    for i, s in enumerate(sents):
        end = starts[i + 1] if i + 1 < len(sents) else dur
        res["sentences"].append(dict(i=i, text=s, start=round(starts[i], 3), end=round(max(end, starts[i] + 0.2), 3)))
    Path(a.out).write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    how = "ESTIMATED by length" if estimated else f"timed from the recording, {matched:.0%} of words matched"
    print(f"{len(sents)} sentences over {dur:.1f} s ({how}) -> {a.out}")
    if note:
        print("NOTE: " + note)


if __name__ == "__main__":
    main()
