# Documentary Starter: setup

**For you:** extract the ZIP, then open the **Documentary Starter** folder in Claude Desktop: Code tab, "this computer", "Open folder", and trust the workspace. Tell Claude to follow SETUP.md, and say yes when it asks to install things. Then paste your script, give it your voiceover file, and ask it to create the visuals.

---

## For Claude
1. Detect the OS. Then check each tool with its version command:

   | Tool | What it's for | Check |
   |---|---|---|
   | Python 3.9+ | runs the helper scripts | `python3 --version`, `python --version` or `py -3 --version` (use whichever works from now on) |
   | FFmpeg + ffprobe | reads the voiceover; cuts and renders the video | `ffmpeg -version`, `ffprobe -version` |
   | yt-dlp | downloads clips from YouTube and other video sites | `yt-dlp --version` |
   | Deno | lets yt-dlp read YouTube pages (yt-dlp needs a JavaScript runtime for YouTube) | `deno --version` |
   | faster-whisper (Python) | times the narration from the recording | `<python> -c "import faster_whisper"` |

2. List what's missing and the exact commands, and ask once. Install only what's missing, don't change security settings, and don't install anything else.
   - **Windows:** run each missing one with `--accept-source-agreements --accept-package-agreements` so winget doesn't stop on a prompt:
     - `winget install -e --id Python.Python.3.12`
     - `winget install -e --id Gyan.FFmpeg`
     - `winget install -e --id yt-dlp.yt-dlp`
     - `winget install -e --id DenoLand.Deno`
     - then `<python> -m pip install --user faster-whisper`
   - **macOS:** `brew install python ffmpeg yt-dlp deno`, then `python3 -m pip install --user faster-whisper`. If pip refuses with "externally managed environment", add `--break-system-packages`.
   - **No package manager:** give the official download pages (python.org, ffmpeg.org, github.com/yt-dlp/yt-dlp, deno.com) and wait.

   If a tool still isn't found after installing, the PATH changed. The user fully quits Claude Desktop (not just this chat), opens it again in the same folder, and says "continue setup". Re-check every version before moving on. faster-whisper downloads a small speech model (about 150 MB) the first time it runs.

3. There is no practice project. If the request mentions one, just confirm setup is done. Then tell the user, in one or two lines: paste your script here, give me the path to your voiceover, and ask me to create the visuals. To get the path: on Windows, right-click the file and choose "Copy as path"; on Mac, right-click, hold Option, and choose "Copy as Pathname".

The editing itself is the **documentary-edit** skill (`.claude/skills/documentary-edit/SKILL.md`).
