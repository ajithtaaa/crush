"""Find and download footage for a documentary edit, one file at a time, with a project ledger.

  python fetch.py commons --query "old faithful eruption" --kind video|image [--limit 8]
      Search Wikimedia Commons. Prints candidates (title, caption, date, author, license, page, url) as JSON. Downloads nothing.
  python fetch.py get --project projects/NAME --id S03 --url URL [--start 61 --end 75]
      Download one source into projects/NAME/sources/. YouTube and other video pages go through yt-dlp; with --start/--end only
      that part (plus 1 s each side) is downloaded, and the result says where the file starts in the original ("offset"):
      in-points for that file are (time in the original video) - offset. Direct image/video file URLs are fetched over HTTPS.
  python fetch.py wait --project projects/NAME
      Sleep until the next YouTube download is allowed (at most 10 minutes). Run it while nothing else needs doing.
  python fetch.py status --project projects/NAME
      What was downloaded, what failed, which sites are paused, how many YouTube downloads are left.

Run get and wait with a 10-minute command timeout (or in the background); a get can wait 2 minutes before it starts.

Pacing (protects the user's connection and IP; it does not guarantee a site will never refuse):
- one download at a time (a lock file holding the process id);
- YouTube: 120 s between attempts, batches of 3, 10 minutes between batches, 12 per project. Failed and interrupted
  attempts count. Other sites (archives, photos): 6 s between attempts;
- on HTTP 403 / 429, "confirm you're not a bot", sign-in or captcha the site is paused for this project. No cookies, no proxies,
  no other downloader, no retry of a URL that failed.
"""
import argparse
import html
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

AGENT = "DocumentaryStarter/3.0 (documentary editing tool)"
GAP = {"youtube": 120}     # seconds between attempts on one site
GAP_OTHER = 6              # archives, stock and photo sites: a short polite gap
YT_BATCH, YT_BATCH_GAP, YT_MAX = 3, 600, 12
YTDLP_TIMEOUT = 420        # wait (<=120 s) + download stay under a 10-minute command timeout
FILE_MAX = 320 * 1024 * 1024
FILE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".mp4", ".webm", ".mov", ".ogv", ".m4v")
BLOCK_WORDS = ("http error 403", "http error 429", "too many requests", "confirm you", "not a bot", "sign in to confirm",
               "captcha", "unusual traffic")


def ssl_ctx():
    try:
        import certifi  # python.org Python on macOS often has no system certificates
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def open_url(url, timeout):
    return urlopen(Request(url, headers={"User-Agent": AGENT}), timeout=timeout, context=ssl_ctx())


def site(url):
    h = (urlsplit(url).hostname or "").lower()
    if h.endswith(("youtube.com", "youtu.be", "googlevideo.com")):
        return "youtube"
    return h[4:] if h.startswith("www.") else h


def plain(v):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", v or "")).replace("\xa0", " ")).strip()


# ---------------------------------------------------------------- Commons search
def commons(query, kind, limit):
    params = dict(action="query", generator="search", gsrnamespace=6, gsrlimit=max(limit * 2, 10), format="json",
                  gsrsearch=f"filetype:{'bitmap' if kind == 'image' else 'video'} {query}", prop="imageinfo",
                  iiprop="url|size|mime|extmetadata")
    with open_url("https://commons.wikimedia.org/w/api.php?" + urlencode(params), 20) as r:
        res = json.load(r)
    out = []
    for p in sorted(res.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0)):
        info = (p.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        f = lambda k: plain(meta.get(k, {}).get("value", ""))
        if not info.get("mime", "").startswith(kind + "/") or info.get("mime") == "image/gif":
            continue
        out.append(dict(title=p["title"], caption=f("ImageDescription")[:500], date=f("DateTimeOriginal")[:40],
                        author=f("Artist")[:200], license=f("LicenseShortName"), page=info.get("descriptionurl"),
                        url=info.get("url"), size_mb=round(info.get("size", 0) / 1e6, 1)))
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------- ledger + lock
def pid_alive(pid):
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class Ledger:
    def __init__(self, project):
        self.dir = Path(project) / "sources"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "ledger.json"
        self.lock = self.dir / ".download.lock"
        self.load()

    def load(self):
        self.data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {"attempts": [], "paused": {}}

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def attempts(self, s):
        return [a for a in self.data["attempts"] if a["site"] == s]

    def acquire(self):
        if self.lock.exists():
            try:
                pid = int(self.lock.read_text().split()[0])
            except (ValueError, IndexError, OSError):
                pid = -1
            if pid_alive(pid):
                sys.exit("Another download is running in this project. Wait for it to finish (or run `fetch.py status`).")
            self.lock.unlink(missing_ok=True)
        try:
            with self.lock.open("x") as f:
                f.write(f"{os.getpid()} {time.time()}")
        except FileExistsError:
            sys.exit("Another download just started in this project. Wait for it to finish.")
        self.load()                       # read the ledger only once we hold the lock
        for a in self.data["attempts"]:   # an attempt still 'pending' was killed mid-download: it counts, and it ended now
            if a["outcome"] == "pending":
                a.update(outcome="interrupted", ended=time.time())
        self.save()

    def release(self):
        self.lock.unlink(missing_ok=True)


def youtube_wait(led):
    """Seconds until the next YouTube attempt is allowed, or a reason it never is."""
    done = led.attempts("youtube")
    if "youtube" in led.data["paused"]:
        return None, f"YouTube is paused for this project: {led.data['paused']['youtube']}"
    if len(done) >= YT_MAX:
        return None, f"YouTube limit for this project reached ({YT_MAX})."
    if not done:
        return 0, ""
    gap = YT_BATCH_GAP if len(done) % YT_BATCH == 0 else GAP["youtube"]
    return max(0.0, gap - (time.time() - done[-1]["ended"])), ""


# ---------------------------------------------------------------- download
def ytdlp(url, out_stem, start, end):
    cmd = ["yt-dlp", "--ignore-config", "--no-playlist", "--retries", "0", "--fragment-retries", "0",
           "--extractor-retries", "0", "--socket-timeout", "20", "--concurrent-fragments", "1", "--limit-rate", "4M",
           "--write-info-json", "--merge-output-format", "mp4", "-f", "bv*[height<=1080]+ba/b[height<=1080]/b",
           "-o", str(out_stem) + ".%(ext)s"]
    if start is not None:
        cmd += ["--download-sections", f"*{max(0.0, start - 1):.2f}-{end + 1:.2f}", "--force-keyframes-at-cuts"]
    cmd += ["--", url]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=YTDLP_TIMEOUT)
        return p.returncode, (p.stdout + "\n" + p.stderr)
    except subprocess.TimeoutExpired:
        return 1, f"yt-dlp took longer than {YTDLP_TIMEOUT} s; try a shorter --start/--end section"


def direct(url, path):
    with open_url(url, 30) as r, open(path, "wb") as f:
        left = FILE_MAX
        while chunk := r.read(1 << 17):
            left -= len(chunk)
            if left < 0:
                raise ValueError("file is larger than 320 MB; pick a smaller source")
            f.write(chunk)


def media_files(led, sid):
    return sorted(p for p in led.dir.glob(sid + ".*") if p.suffix.lower() not in (".json", ".part", ".ytdl", ".tmp"))


def get(a):
    if (a.start is None) != (a.end is None) or (a.start is not None and a.end <= a.start):
        sys.exit("--start and --end go together, and --end must be after --start.")
    led = Ledger(a.project)
    led.acquire()
    rec = None
    try:
        s = site(a.url)
        if s in led.data["paused"]:
            sys.exit(f"{s} is paused for this project: {led.data['paused'][s]}. Use other sources or the user's own files.")
        if any(x["url"] == a.url and x["outcome"] != "ok" for x in led.data["attempts"]):
            sys.exit("This URL already failed in this project. Do not retry it; pick another source.")
        if any(x["id"] == a.id for x in led.data["attempts"]) or media_files(led, a.id):
            sys.exit(f"The id {a.id} is already used in this project. Pick a new id.")
        is_file = Path(urlsplit(a.url).path).suffix.lower() in FILE_EXT and s != "youtube"
        if s == "youtube":
            wait, why = youtube_wait(led)
            if wait is None:
                sys.exit(why + " Use other sources or ask the user for files.")
            if wait > GAP["youtube"]:
                sys.exit(f"The YouTube batch of {YT_BATCH} is done; the next one opens in {int(wait)} s. Keep editing with "
                         "other sources, then run `fetch.py wait` before the next YouTube download.")
        else:
            done = led.attempts(s)
            wait = max(0.0, GAP_OTHER - (time.time() - done[-1]["ended"])) if done else 0
        if wait > 0:
            print(f"waiting {int(wait)} s before the next {s} download (pacing)", flush=True)
            time.sleep(wait)
        if not is_file and not shutil.which("yt-dlp"):
            sys.exit("yt-dlp is not installed (see SETUP.md). Use direct file URLs or the user's own files.")
        rec = dict(id=a.id, url=a.url, site=s, started=time.time(), start=a.start, end=a.end, outcome="pending")
        led.data["attempts"].append(rec)
        led.save()                                     # counted before the request, in case this process is killed
        stem = led.dir / a.id
        try:
            if is_file:
                target = stem.with_suffix(Path(urlsplit(a.url).path).suffix.lower())
                direct(a.url, target)
                rec.update(outcome="ok", file=target.name, method="https", offset=0.0)
            else:
                code, log = ytdlp(a.url, stem, a.start, a.end)
                files = media_files(led, a.id)
                if code == 0 and files:
                    rec.update(outcome="ok", file=files[-1].name, method="yt-dlp",
                               offset=round(max(0.0, a.start - 1), 2) if a.start is not None else 0.0)
                else:
                    blocked = next((w for w in BLOCK_WORDS if w in log.lower()), None)
                    rec.update(outcome="blocked" if blocked else "failed", error=log.strip()[-600:])
                    if blocked:
                        led.data["paused"][s] = f"stopped on '{blocked}' at {time.strftime('%H:%M')}"
        except Exception as e:  # noqa: BLE001  (any network error ends the attempt; the ledger records it)
            msg = str(e)
            blocked = any(w in msg.lower() for w in ("403", "429"))
            rec.update(outcome="blocked" if blocked else "failed", error=msg[-600:])
            if blocked:
                led.data["paused"][s] = f"stopped on '{msg[:60]}' at {time.strftime('%H:%M')}"
        if rec["outcome"] != "ok":
            for p in led.dir.glob(a.id + ".*"):         # no half-downloaded leftovers under this id
                p.unlink(missing_ok=True)
        rec["ended"] = time.time()
        led.save()
    finally:
        led.release()
    if rec["outcome"] == "ok":
        print(json.dumps(dict(ok=True, file=str(led.dir / rec["file"]), site=rec["site"], offset=rec["offset"],
                              note="in-points for this file = time in the original - offset" if rec["offset"] else "")))
    else:
        print(json.dumps(dict(ok=False, outcome=rec["outcome"], site=rec["site"], error=rec.get("error", "")[-300:],
                              paused=led.data["paused"].get(rec["site"]))))
        sys.exit(2)


def wait_cmd(a):
    led = Ledger(a.project)
    w, why = youtube_wait(led)
    if w is None:
        sys.exit(why)
    if w > 0:
        print(f"waiting {int(w)} s for the next YouTube download", flush=True)
        time.sleep(w)
    print("ready: the next YouTube download can start")


def status(a):
    led = Ledger(a.project)
    yt = led.attempts("youtube")
    w, why = youtube_wait(led)
    print(json.dumps(dict(attempts=[{k: x.get(k) for k in ("id", "site", "outcome", "file", "offset", "url")} for x in led.data["attempts"]],
                          paused=led.data["paused"], youtube_used=len(yt), youtube_left_this_project=YT_MAX - len(yt),
                          next_youtube_in_seconds=None if w is None else int(w), youtube_note=why), indent=1, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("commons"); c.add_argument("--query", required=True)
    c.add_argument("--kind", choices=("image", "video"), default="image"); c.add_argument("--limit", type=int, default=8)
    g = sub.add_parser("get"); g.add_argument("--project", required=True); g.add_argument("--id", required=True)
    g.add_argument("--url", required=True); g.add_argument("--start", type=float); g.add_argument("--end", type=float)
    for name in ("status", "wait"):
        sub.add_parser(name).add_argument("--project", required=True)
    a = ap.parse_args()
    if a.cmd == "commons":
        print(json.dumps(commons(a.query, a.kind, a.limit), indent=1, ensure_ascii=False))
    elif a.cmd == "get":
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", a.id):
            sys.exit("--id: letters, digits, - and _ only")
        get(a)
    elif a.cmd == "wait":
        wait_cmd(a)
    else:
        status(a)


if __name__ == "__main__":
    main()
