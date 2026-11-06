---
name: documentary-edit
description: The documentary skill. Turn a script and a recorded voiceover into an edited video. It times the narration, finds and downloads real footage and photos for every line (YouTube, archives, public sources), checks each shot shows what is being said, cuts it to the voice and renders the MP4. Use when the user asks to "create the visuals", edit, or make a video from a script and audio, in a documentary style or any style they ask for.
---

# Documentary edit

You are editing the user's video: their script, their voiceover, real footage. The narration is the clock. The goal is a finished MP4 the user can watch, not a plan or a review page. Pause only for a missing input or an install/permission question.

The helpers live in `.claude/skills/documentary-edit/scripts/` (run them with the Python command found in SETUP.md, from the project root):
- `timing.py`: when each sentence is spoken.
- `fetch.py`: Commons search plus paced, logged downloads (YouTube included).
- `assemble.py`: shot list to MP4, plus frames sheets to check.

They do the mechanics. The editing decisions are yours. Downloads pace themselves, and a render takes a while, so run `fetch.py get`, `fetch.py wait`, `timing.py` and `assemble.py` with a 10-minute command timeout (or in the background and wait for them). Don't kill them early.

## 1. Set up the job
- **Script:** if the user pasted it into the chat, save it word for word as `projects/<name>/script.txt`. `<name>` is a short slug of the topic.
- **Voiceover:** copy the file into `projects/<name>/` and keep its original name and format.
- If either is missing or ambiguous, ask once.
- If the tools haven't been checked in this session, check them first (SETUP.md step 1).
- **Style:** ask nothing unless the user named one. The default is documentary (below). If they asked for a style (news, true crime, hype, calm explainer, vertical short), follow their style for pacing, moves and framing; the sourcing and honesty rules stay the same.
- **Format:** 1920x1080 at 30 fps unless they asked for vertical (1080x1920) or something else.

## 2. Time the narration
`timing.py --voice … --script … --out projects/<name>/timing.json`
- If it says ESTIMATED, there's no usable word timing: faster-whisper is missing or failed, or the script doesn't match the recording. Its NOTE says which. Tell the user that cuts may drift, and offer the fix (the install in SETUP.md, or the right script).
- Never invent timings from word count when the real timing tool is available.

## 3. Plan the shots
Read the whole script first. Mark every change of person, place, year, event, number or mood. Then plan shots in narration order:
- **Pace:** a new picture roughly every 3-6 seconds, cut where a sentence or clause turns. Hold longer when an action is playing out (a race, a speech, an eruption); let it reach its outcome.
- **What it shows:** for each shot write the line, the start/end seconds and what must actually be visible. Be specific: who, where, when, doing what. "Forever Young winning the 2025 Breeders' Cup Classic", not "horse racing".
- **Kind:** video for action and events. A photo when the narration names a specific person, document, place or moment and a real photo of that exists. The right photo beats the wrong video.
- **Variety:** never the same picture twice in a row. A good source can serve several lines from different moments.
- Save it as `projects/<name>/plan.md`. For long scripts plan the whole thing, then source and render in parts (see 7).

## 4. Find and download the footage
Work through the plan. For each shot, in this order:
1. **The user's own files** in the project folder, if they gave any.
2. **Wikimedia Commons:** `fetch.py commons --query "…" --kind image|video` returns candidates with caption, date, author and license. Pick by the caption and date, not the thumbnail alone.
3. **YouTube and other video sites:** use your web search to find the actual event (official channels, news outlets, broadcasters, the original uploader). Then download only the part you need: `fetch.py get --project projects/<name> --id S07 --url URL --start 61 --end 75`. The result gives an `offset`: the file starts that many seconds into the original, so an in-point in that file is (time in the original) - offset. One download covering 1-3 minutes can feed several shots; prefer that to many small downloads. Each id is used once; a new source gets a new id.
4. **Photos from the web:** official sites, news photos, archives. Find the direct image file URL and `fetch.py get` it.

**Download limits.** The script enforces these. Respect what it tells you and never work around it:
- one download at a time; 2 minutes between YouTube downloads and a few seconds between archive or photo downloads (the script waits by itself);
- YouTube: 3 per batch, 10 minutes between batches, 12 per project;
- if a site answers with a block, a bot check or 403/429, that site is paused for the project. No cookies, VPNs, proxies, other downloaders or retries;
- while a batch cools down, keep going with Commons, photos and the edit itself. When there's nothing else left to do, run `fetch.py wait --project projects/<name>` (it sleeps until the next batch opens, up to 10 minutes) and continue. Don't stop and hand back to the user just because of a cooldown.

These limits keep the user's connection out of trouble. They are not a guarantee.

**Check every source before you use it.** Pull a few frames from each downloaded video (`ffmpeg -ss T -i file -frames:v 1 check.jpg`) and look at them. A filename, title or search result is not proof.
- Confirm the person, team, place and year from what is visible (faces, numbers, signs, scoreboards, dates, captions).
- Never present a different event, year, rival or today's location as the thing being narrated. If you use general context footage, it must be honest context ("a racetrack at night"), not a fake of the specific event.
- Note the source URL, the credit and what is in it in `projects/<name>/sources.md`.

## 5. Keep it transformative
This is commentary over real material, edited:
- use short pieces (usually under 7 seconds from any one clip at a time) cut to the narration;
- reframe them: crop to the subject, slow push-ins, mixed with photos and other sources;
- the source's own audio is not used; the narration is the soundtrack;
- don't run someone else's video for long stretches, and don't use music or sound you weren't given.

## 6. Edit and render
Write `projects/<name>/shots.json` (format in `assemble.py --help`). The shots must touch end to start from 0 to the end of the voiceover.
- **Documentary default:** straight cuts, and slow moves on stills ("push", "pull", "left", "right"). Video plays as is ("none") or with a gentle "push". Use "fit" for a photo that must be seen whole.
- **The user's style decides the rest:** faster cuts for hype, longer holds for calm, vertical framing for shorts.
- **Gaps:** never fill one with a text slide, black, or the same shot looped. Find another real angle, a photo, a relevant document or place, or leave it as a reported gap.

Render: `assemble.py --shots projects/<name>/shots.json --voice projects/<name>/<voice file> --out projects/<name>/out/<name>-v1.mp4`
It refuses a shot list with holes, missing files or sources that are too short. Fix and rerun.

## 7. Long scripts
For anything over about 2 minutes, work in parts of about 60-90 seconds of narration: plan, source and check each part, then render the whole edit once at the end. Tell the user briefly where you are after each part ("1:30 of 9:56 covered; YouTube batch 2 cooling down, using archive photos meanwhile"). Carry on without being asked unless a limit or a missing input stops you.

## 8. Check, then deliver
- **Look at the frames sheets** (`…-frames-01.jpg` and on, one frame from every shot) and at a few frames around joins. Wrong subject, a watermark-heavy frame, black, a still that should move: fix it and render a new version (`-v2`). Never overwrite.
- **Confirm the MP4 plays** with picture and sound for the full voiceover length (assemble prints both).
- **Then tell the user, briefly:**
  - the MP4 path, opened for them;
  - how much of it is real footage vs photos;
  - any lines you couldn't cover with real material, with the timecode and what's missing;
  - that the source list with credits is in `sources.md`.
- Be honest about what you checked by eye and what you didn't.
