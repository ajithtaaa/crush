"""Render the edit: picture from a shot list, cut to the narration, with the voiceover underneath.

  python assemble.py --shots projects/NAME/shots.json --voice projects/NAME/voice.mp3 --out projects/NAME/out/edit-v1.mp4
shots.json (paths relative to the shots.json folder):
  {"size": "1920x1080", "fps": 30,
   "shots": [{"start": 0.0, "end": 4.2, "file": "sources/S01.mp4", "in": 12.0, "move": "push", "what": "geyser erupting, 1980s"},
             {"start": 4.2, "end": 8.6, "file": "sources/S02.jpg", "move": "pull", "what": "visitors on the boardwalk"}]}
  start/end: seconds on the narration. Shots must touch end to start from 0 to the end of the voiceover (no gaps, no overlaps).
  in: where to start inside a video source (seconds). move: none | push | pull | left | right (a slow camera move; stills
  should almost always move). Optional "fit": "fill" (default, crop to fill the frame) or "fit" (whole picture, blurred sides).
Writes the MP4 plus <out>-frames-01.jpg, -02, ... (one frame from the middle of every shot, 30 per sheet) to look at
before calling the edit done.
Source audio is not used: the narration is the soundtrack. Nothing is uploaded.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

IMAGES = (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp")   # convert a GIF to PNG/MP4 first


def probe_duration(p):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                         capture_output=True, text=True).stdout.strip()
    return float(out) if out and out != "N/A" else None


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode:
        sys.exit("ffmpeg failed:\n" + " ".join(cmd) + "\n" + p.stderr[-1500:])


def move_filter(move, n, w, h, fps):
    """zoompan on a 2x frame: smooth slow moves. n = frames in the shot."""
    n = max(n, 2)
    z = {"push": f"1+0.10*on/{n - 1}", "pull": f"1.10-0.10*on/{n - 1}", "left": "1.08", "right": "1.08"}.get(move)
    if not z:
        return None
    x = {"left": f"(iw-iw/zoom)*(1-on/{n - 1})", "right": f"(iw-iw/zoom)*on/{n - 1}"}.get(move, "iw/2-(iw/zoom/2)")
    return f"zoompan=z='{z}':x='{x}':y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps={fps}"


def frame_filter(fit, w, h):
    if fit == "fit":
        return (f"split[a][b];[a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=30:3,eq=brightness=-0.08[bg];"
                f"[b]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2")
    return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shots", required=True); ap.add_argument("--voice", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    spec = json.loads(Path(a.shots).read_text(encoding="utf-8-sig"))
    base = Path(a.shots).resolve().parent
    W, H = (int(x) for x in spec.get("size", "1920x1080").lower().split("x"))
    FPS = int(spec.get("fps", 30))
    shots = spec["shots"]
    vdur = probe_duration(a.voice)
    if not vdur:
        sys.exit("Could not read the voiceover duration.")
    # ---- checks before rendering
    errs = []
    if abs(shots[0]["start"]) > 0.05:
        errs.append(f"first shot starts at {shots[0]['start']} s, not 0")
    for p, q in zip(shots, shots[1:]):
        if abs(p["end"] - q["start"]) > 0.05:
            errs.append(f"gap/overlap between {p['end']} and {q['start']} s")
    if shots[-1]["end"] < vdur - 0.5 / FPS:
        errs.append(f"last shot ends at {shots[-1]['end']} s but the voiceover runs {vdur:.2f} s")
    for i, s in enumerate(shots):
        f = base / s["file"]
        if not f.exists():
            errs.append(f"shot {i + 1}: missing file {s['file']}"); continue
        if s["end"] - s["start"] < 0.3:
            errs.append(f"shot {i + 1}: shorter than 0.3 s")
        if f.suffix.lower() not in IMAGES:
            d = probe_duration(f)
            need = s.get("in", 0) + (s["end"] - s["start"])
            if d is not None and need > d + 0.05:
                errs.append(f"shot {i + 1}: needs {need:.2f} s of {s['file']} but it is {d:.2f} s long")
    if errs:
        sys.exit("Fix the shot list first:\n- " + "\n- ".join(errs))
    # ---- render each shot to the same format, frame-exact against the narration clock
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="docedit-"))
    try:
        segs, mids = [], []
        end_frame = round(min(shots[-1]["end"], vdur) * FPS)
        for i, s in enumerate(shots):
            f0 = round(s["start"] * FPS)
            f1 = end_frame if i == len(shots) - 1 else round(s["end"] * FPS)
            n = f1 - f0
            if n <= 0:
                continue
            f = base / s["file"]
            img = f.suffix.lower() in IMAGES
            mv = move_filter(s.get("move", "push" if img else "none"), n, W, H, FPS)
            fit = frame_filter(s.get("fit", "fill"), W * 2 if mv else W, H * 2 if mv else H)
            pre = "" if img else f"fps={FPS},"          # video: our frame rate first, so moves run at the same speed
            post = "" if img else ",tpad=stop_mode=clone:stop_duration=10"   # a short video stream cannot shift later shots
            chain = pre + fit + (("," + mv) if mv else "") + f",fps={FPS},setsar=1,format=yuv420p" + post
            seg = tmp / f"s{i:04d}.mp4"
            src = (["-loop", "1", "-i", str(f)] if img else ["-ss", f"{s.get('in', 0):.3f}", "-i", str(f)])
            run(["ffmpeg", "-v", "error", "-y"] + src + ["-filter_complex", f"[0:v]{chain}[v]", "-map", "[v]", "-an",
                 "-frames:v", str(n), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-r", str(FPS), str(seg)])
            segs.append(seg); mids.append((f0 + n / 2) / FPS)
        lst = tmp / "list.txt"
        quote = lambda p: p.as_posix().replace("'", "'\\''")   # concat list quoting for paths with apostrophes
        lst.write_text("".join(f"file '{quote(p)}'\n" for p in segs), encoding="utf-8")
        pic = tmp / "picture.mp4"
        run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(pic)])
        run(["ffmpeg", "-v", "error", "-y", "-i", str(pic), "-i", str(a.voice), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
             "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)])
        # ---- frames to look at
        for k, t in enumerate(mids):
            run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(out), "-frames:v", "1", "-vf", "scale=480:-2",
                 str(tmp / f"m{k:04d}.jpg")])
        sheets = []
        for c in range(0, len(mids), 30):           # sheets of up to 30 shots, readable at a glance
            part = list(range(c, min(c + 30, len(mids))))
            for j, k in enumerate(part):
                shutil.copyfile(tmp / f"m{k:04d}.jpg", tmp / f"p{j:04d}.jpg")
            cols = min(6, len(part))
            rows = -(-len(part) // cols)
            sheet = out.with_name(f"{out.stem}-frames-{c // 30 + 1:02d}.jpg")
            run(["ffmpeg", "-v", "error", "-y", "-framerate", "1", "-i", str(tmp / "p%04d.jpg"), "-vf", f"tile={cols}x{rows}",
                 "-frames:v", "1", str(sheet)])
            for j in range(len(part)):
                (tmp / f"p{j:04d}.jpg").unlink()
            sheets.append(str(sheet))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    d = probe_duration(out)
    print(json.dumps(dict(ok=True, mp4=str(out), seconds=round(d or 0, 2), voice_seconds=round(vdur, 2), shots=len(segs),
                          frames_sheets=sheets)))


if __name__ == "__main__":
    main()
