#!/usr/bin/env python3
"""Myden reel: 1080x1920 30fps, Gyan-Infinet-style edit."""
import os, subprocess, sys, math
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS = 1080, 1920, 30
D = os.path.dirname(os.path.abspath(__file__))
SRC = f"{D}/src"; GFX = f"{D}/gfx"; SEG = f"{D}/seg"; os.makedirs(SEG, exist_ok=True)
UP = "/root/.claude/uploads/d2cf0c7b-5436-57f4-a4e4-4e672c923964"
BK_LOGO = f"{UP}/dc0643c0-image.jpg"
END = 71.6  # total length (VO 68.28 + end card)
YEL = (236, 233, 30); WHITE = (255, 255, 255); GREEN = (60, 240, 60)
FBLACK = "/usr/share/fonts/opentype/inter/InterDisplay-Black.otf"
FBOLD = "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf"

V = lambda n: f"{SRC}/VID-20261117-WA00{n}.mp4"
I = lambda n: f"{SRC}/IMG-20261117-WA00{n}.jpg"
ROSE, CASA = f"{SRC}/rose.mp4", f"{SRC}/casa.mp4"

# (source, src_start, duration, mode, focus_x[0..1])  mode: fill | card | img
SHOTS = [
 (I(31),0,1.45,"img",.5), (ROSE,3.0,1.1,"fill",.5), (ROSE,6.0,1.1,"fill",.5), (CASA,2.4,1.35,"fill",.5),
 (ROSE,9.0,1.25,"fill",.5), (ROSE,12.0,1.25,"fill",.5), (CASA,4.6,1.5,"fill",.5),
 (ROSE,14.3,1.3,"fill",.5), (ROSE,17.0,1.2,"fill",.5), (CASA,6.0,1.35,"fill",.5),
 (V(20),1.0,1.6,"card",.5), (V(20),4.5,1.4,"card",.5), (I(30),0,1.3,"img",.5), (ROSE,25.6,1.45,"fill",.5),
 (V(34),0.0,1.8,"card",.5), (I(29),0,1.7,"img",.5),
 (V(23),0.0,1.5,"card",.5), (V(25),0.3,1.3,"fill",.6), (V(26),1.0,1.4,"card",.5), (V(24),0.2,1.3,"fill",.5),
 (ROSE,8.6,1.1,"fill",.5), (ROSE,11.5,1.1,"fill",.5), (CASA,9.3,1.2,"fill",.5), (CASA,10.6,1.3,"fill",.5),
 (CASA,12.1,1.7,"fill",.5),
 (V(20),8.0,1.2,"card",.5),
 (I(29),0,1.4,"img",.4), (V(35),2.0,1.4,"fill",.5), (V(35),4.0,1.3,"fill",.5), (I(30),0,1.3,"img",.5), (V(35),10.4,1.7,"fill",.5),
 (V(34),2.0,1.5,"card",.5), (I(31),0,1.5,"img",.5), (V(26),5.0,1.6,"card",.5),
 (V(35),12.0,1.4,"fill",.5), (V(25),2.0,1.4,"fill",.6), (V(24),1.2,1.5,"fill",.5), (I(29),0,1.6,"img",.6), (V(34),3.5,1.6,"card",.5),
 (I(31),0,1.8,"img",.5), (V(35),6.0,1.8,"fill",.5),
 (V(23),1.2,1.7,"card",.5), (I(30),0,1.8,"img",.5),
 (V(35),14.0,2.0,"fill",.5), (V(26),6.5,2.0,"card",.5),
 (I(31),0,2.8,"img",.5),
 (I(29),0,3.3,"endbg",.5),
]

GRADE = "eq=contrast=1.07:saturation=1.15:gamma=0.98,unsharp=5:5:0.6"

def card_mask(w, h, r=36):
    m = Image.new("L", (w, h), 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, w-1, h-1), r, fill=255)
    p = f"{GFX}/mask_{w}x{h}.png"; m.save(p); return p

def render_shot(i, s):
    src, ss, dur, mode, fx = s
    out = f"{SEG}/{i:03d}.mp4"
    if os.path.exists(out): return out
    common = ["-t", f"{dur:.3f}", "-r", str(FPS), "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "14", "-pix_fmt", "yuv420p", out]
    n = int(round(dur * FPS))
    if mode == "fill":
        # cover-scale with slight zoom; slow push-in
        vf = (f"fps={FPS},scale={W*1.12:.0f}:{H*1.12:.0f}:force_original_aspect_ratio=increase:flags=lanczos,"
              f"crop={W*1.12:.0f}:{H*1.12:.0f},"
              f"scale=w='trunc({W}*(1.10-0.08*n/{n})/2)*2':h='trunc({H}*(1.10-0.08*n/{n})/2)*2':eval=frame:flags=bicubic,"
              f"crop={W}:{H},{GRADE}")
        # simpler robust push: use zoompan-free crop approach
        vf = (f"fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},"
              f"scale={int(W*1.08)}:{int(H*1.08)}:flags=lanczos,"
              f"crop={W}:{H}:x='({int(W*0.08)})*(0.5+0.5*t/{dur})*{fx*2:.2f}':y='{int(H*0.04)}*(1-t/{dur})+{int(H*0.02)}',{GRADE}")
        cmd = ["ffmpeg", "-v", "error", "-y", "-ss", str(ss), "-i", src, "-vf", vf] + common
    elif mode == "card":
        cw = 1000; ch = 562
        mask = card_mask(cw, ch)
        fc = (f"[0:v]fps={FPS},split[a][b];"
              f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:2,eq=brightness=-0.32:saturation=0.8[bg];"
              f"[b]scale={int(cw*1.06)}:{int(ch*1.06)}:flags=lanczos,crop={cw}:{ch}:x='{int(cw*0.06)}*t/{dur}':y={int(ch*0.03)},{GRADE},format=rgba[fg0];"
              f"[1:v]format=gray,scale={cw}:{ch}[m];[fg0][m]alphamerge[fg];"
              f"[bg][fg]overlay=(W-w)/2:560,format=yuv420p[v]")
        cmd = ["ffmpeg", "-v", "error", "-y", "-ss", str(ss), "-i", src, "-loop", "1", "-i", mask,
               "-filter_complex", fc, "-map", "[v]"] + common
    elif mode in ("img", "endbg"):
        im = Image.open(src).convert("RGB")
        if mode == "endbg":
            im = im.filter(ImageFilter.GaussianBlur(6))
        # Ken Burns via python frames
        sw, sh = im.size
        scale = max(W / sw, H / sh) * 1.12
        big = im.resize((int(sw * scale), int(sh * scale)), Image.LANCZOS)
        bw, bh = big.size
        p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                              "-r", str(FPS), "-i", "-", "-vf", GRADE + (",eq=brightness=-0.25" if mode == "endbg" else "")] + common,
                             stdin=subprocess.PIPE)
        for k in range(n):
            t = k / max(1, n - 1)
            z = 1.0 + 0.10 * t  # push in
            cw_, ch_ = W * bw / (W * z) / (bw / W), 0
            vw, vh = bw / z, bh / z
            # keep aspect W:H
            vw = min(bw, bh * W / H) / z; vh = vw * H / W
            cx = bw * fx + (bw * 0.02) * (t - 0.5); cy = bh * 0.5
            x0 = min(max(0, cx - vw / 2), bw - vw); y0 = min(max(0, cy - vh / 2), bh - vh)
            fr = big.resize((W, H), Image.BICUBIC, box=(x0, y0, x0 + vw, y0 + vh))
            p.stdin.write(fr.tobytes())
        p.stdin.close(); p.wait()
        return out
    subprocess.run(cmd, check=True)
    return out

# ---------------- overlay (text, branding, vignette) ----------------
def font(path, size): return ImageFont.truetype(path, size)

def text_block(lines):
    """lines: list of (text, color, size). returns RGBA image with shadow."""
    rend = []
    for t, c, sz in lines:
        f = font(FBLACK, sz)
        bb = f.getbbox(t)
        rend.append((t, c, f, bb))
    w = max(bb[2] - bb[0] for *_, bb in rend) + 60
    gap = 6
    hs = [f.getbbox("HÅg")[3] - f.getbbox("H")[1] for _, _, f, _ in rend]
    h = sum(hs) + gap * (len(rend) - 1) + 60
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    sh = Image.new("RGBA", (w, h), (0, 0, 0, 0)); ds = ImageDraw.Draw(sh)
    y = 30
    for (t, c, f, bb), hh in zip(rend, hs):
        tw = bb[2] - bb[0]; x = (w - tw) / 2 - bb[0]
        ds.text((x + 3, y + 5 - f.getbbox("H")[1]), t, font=f, fill=(0, 0, 0, 200))
        d.text((x, y - f.getbbox("H")[1]), t, font=f, fill=c + (255,))
        y += hh + gap
    sh = sh.filter(ImageFilter.GaussianBlur(9))
    return Image.alpha_composite(sh, im)

def fit_lines(lines, maxw=980):
    # shrink sizes so the widest line fits maxw
    out = []
    for t, c, sz in lines:
        f = font(FBLACK, sz)
        while f.getlength(t) > maxw and sz > 30:
            sz -= 4; f = font(FBLACK, sz)
        out.append((t, c, sz))
    return out

# captions: (start, end, lines, y_center, kind)
B, S = 118, 70  # big, small sizes
CAPS = [
 (0.05, 1.45, [("KOZHIKODE", YEL, B)], 1300, "pop"),
 (1.6, 4.95, [("HOMEMAKERS'", WHITE, S), ("BIGGEST HEADACHE", YEL, B)], 1300, "pop"),
 (5.25, 8.8, [("WEEKEND", WHITE, B), ("GONE?", YEL, B)], 1300, "pop"),
 (9.0, 12.8, [("HOURS OF", WHITE, S), ("CLEANING", YEL, B)], 1300, "pop"),
 (12.95, 18.5, [("WHOM TO", WHITE, S), ("TRUST?", YEL, B)], 1350, "pop"),
 (18.75, 20.55, [("PROFESSIONAL", WHITE, S + 10), ("SOLUTION", YEL, B)], 1350, "pop"),
 (22.2, 23.8, [("DEEP", WHITE, S + 10), ("CLEANING", YEL, B)], 1350, "pop"),
 (23.9, 27.6, [("TRAINED TEAM", YEL, B - 10), ("+ PRO MACHINES", WHITE, S)], 1350, "pop"),
 (27.7, 30.0, [("KITCHEN TO", WHITE, S), ("BATHROOM", YEL, B)], 1300, "pop"),
 (30.0, 32.3, [("LIKE", WHITE, S + 10), ("NEW", YEL, B + 30)], 1300, "pop"),
 (32.4, 34.0, [("AFFORDABLE", GREEN, B - 6), ("PRICE", WHITE, S + 6)], 1300, "pop"),
 (34.1, 35.2, [("NOT JUST", WHITE, S), ("HOMES", YEL, B)], 1350, "pop"),
 (35.3, 36.6, [("OFFICES", YEL, B)], 1300, "pop"),
 (36.6, 37.7, [("SHOPS", YEL, B)], 1300, "pop"),
 (37.7, 39.7, [("COMMERCIAL", YEL, B), ("SPACES", WHITE, S + 6)], 1300, "pop"),
 (39.7, 42.3, [("ALL TYPES OF", WHITE, S), ("BUSINESSES", YEL, B)], 1300, "pop"),
 (42.45, 44.05, [("VERIFIED", YEL, B), ("STAFF", WHITE, S + 10)], 1350, "pop"),
 (44.1, 46.9, [("SAFE &", WHITE, S + 6), ("SECURE", YEL, B)], 1350, "pop"),
 (47.0, 50.0, [("ACROSS", WHITE, S), ("KERALA", YEL, B + 10)], 1300, "pop"),
 (50.0, 54.4, [("500+", YEL, B + 60), ("WORKERS", WHITE, S + 6)], 360, "count"),
 (54.5, 58.0, [("BE PART OF", WHITE, S), ("MYDEN'S GROWTH", YEL, B - 10)], 1350, "pop"),
 (58.1, 61.5, [("MYDEN", WHITE, S + 20), ("FRANCHISE", YEL, B)], 1350, "pop"),
 (61.6, 65.5, [("LOW", WHITE, S + 10), ("INVESTMENT", GREEN, B)], 1350, "pop"),
 (65.6, 68.25, [("CONTACT", WHITE, S + 10), ("NOW", YEL, B + 20)], 1250, "pop"),
]

def ease_pop(t):  # t in seconds since start -> scale
    if t >= 0.22: return 1.0
    x = t / 0.22
    return 0.55 + 0.55 * math.sin(x * math.pi * 0.62) if x < 1 else 1.0

def make_vignette():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    nx = (xx - W / 2) / (W / 2); ny = (yy - H / 2) / (H / 2)
    r = np.sqrt(nx ** 2 * 1.0 + ny ** 2 * 0.75)
    a = np.clip((r - 0.55) / 0.75, 0, 1) ** 1.6 * 0.78
    top = np.clip(1 - yy / 330, 0, 1) ** 2 * 0.45
    bot = np.clip((yy - H * 0.62) / (H * 0.38), 0, 1) ** 1.5 * 0.55
    alpha = 1 - (1 - a) * (1 - top) * (1 - bot)
    v = np.zeros((H, W, 4), np.uint8); v[..., 3] = (alpha * 255).astype(np.uint8)
    return Image.fromarray(v, "RGBA")

def make_badge():
    bk = Image.open(BK_LOGO).convert("RGB").crop((130, 410, 955, 690))
    bw = 250; bk = bk.resize((bw, int(bk.height * bw / bk.width)), Image.LANCZOS)
    pad = 18
    card = Image.new("RGBA", (bw + pad * 2, bk.height + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(card).rounded_rectangle((0, 0, card.width - 1, card.height - 1), 22, fill=(0, 0, 0, 255))
    card.paste(bk, (pad, pad))
    return card

def make_tab():
    f = font(FBOLD, 30); t = "Business Kerala"
    tw = int(f.getlength(t)) + 40
    tab = Image.new("RGBA", (tw, 64), (0, 0, 0, 0)); d = ImageDraw.Draw(tab)
    d.rounded_rectangle((0, -20, tw, 63), 16, fill=YEL + (255,))
    d.text((20, 13), t, font=f, fill=(0, 0, 0, 255))
    tab = tab.rotate(90, expand=True)
    sh = Image.new("RGBA", (tab.width + 30, tab.height + 30), (0, 0, 0, 0))
    sh.paste((0, 0, 0, 140), (15, 15, 15 + tab.width, 15 + tab.height), tab)
    return tab, sh.filter(ImageFilter.GaussianBlur(10))

def make_logo_card():
    lg = Image.open(f"{GFX}/myden_logo.png").convert("RGB")
    lw = 760; lg = lg.resize((lw, int(lg.height * lw / lg.width)), Image.LANCZOS)
    pad = 50
    c = Image.new("RGBA", (lw + pad * 2, lg.height + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(c).rounded_rectangle((0, 0, c.width - 1, c.height - 1), 40, fill=(255, 255, 255, 255))
    c.paste(lg, (pad, pad))
    sh = Image.new("RGBA", (c.width + 80, c.height + 80), (0, 0, 0, 0))
    sh.paste((0, 0, 0, 160), (40, 50, 40 + c.width, 50 + c.height), c)
    sh = sh.filter(ImageFilter.GaussianBlur(18)); sh.alpha_composite(c, (40, 40))
    return sh

def make_end_card():
    lg = Image.open(f"{GFX}/myden_logo.png").convert("RGB")
    lw = 800; lg = lg.resize((lw, int(lg.height * lw / lg.width)), Image.LANCZOS)
    cw = 920; chh = lg.height + 360
    c = Image.new("RGBA", (cw, chh), (0, 0, 0, 0)); d = ImageDraw.Draw(c)
    d.rounded_rectangle((0, 0, cw - 1, chh - 1), 44, fill=(255, 255, 255, 255))
    c.paste(lg, ((cw - lw) // 2, 50))
    y = lg.height + 90
    f1 = font(FBLACK, 72); t1 = "+91 85267 99997"
    d.text(((cw - f1.getlength(t1)) / 2, y), t1, font=f1, fill=(20, 20, 20, 255))
    f2 = font(FBOLD, 52); t2 = "www.myden.co.in"
    d.rounded_rectangle(((cw - f2.getlength(t2)) / 2 - 30, y + 110, (cw + f2.getlength(t2)) / 2 + 30, y + 190), 40, fill=YEL + (255,))
    d.text(((cw - f2.getlength(t2)) / 2, y + 118), t2, font=f2, fill=(0, 0, 0, 255))
    f3 = font(FBOLD, 34); t3 = "KANNUR  |  CALICUT  |  MALAPPURAM"
    d.text(((cw - f3.getlength(t3)) / 2, y + 215), t3, font=f3, fill=(90, 90, 90, 255))
    return c

def make_button(text, bg, fg):
    f = font(FBLACK, 54); tw = int(f.getlength(text))
    b = Image.new("RGBA", (tw + 120, 110), (0, 0, 0, 0)); d = ImageDraw.Draw(b)
    d.rounded_rectangle((0, 0, b.width - 1, b.height - 1), 24, fill=bg + (255,))
    d.text((60, 22), text, font=f, fill=fg + (255,))
    return b

def paste_scaled(frame, im, cx, cy, s, alpha=1.0):
    if s <= 0.01 or alpha <= 0.01: return
    w, h = max(1, int(im.width * s)), max(1, int(im.height * s))
    r = im.resize((w, h), Image.BICUBIC) if s != 1 else im
    if alpha < 1:
        r = r.copy(); a = r.getchannel("A").point(lambda v: int(v * alpha)); r.putalpha(a)
    frame.alpha_composite(r, (int(cx - w / 2), int(cy - h / 2)))

def build_overlay(path):
    vign = make_vignette(); badge = make_badge(); tab, tabsh = make_tab()
    logo_card = make_logo_card(); end_card = make_end_card()
    follow = make_button("Follow", (40, 90, 255), WHITE)
    contact = make_button("Call Now", YEL, (0, 0, 0))
    base = vign.copy()
    base.alpha_composite(badge, (48, 70))
    tx, ty = 0, 840
    base.alpha_composite(tabsh, (tx - 15, ty - 5)); base.alpha_composite(tab, (tx, ty))
    caps = [(s, e, text_block(fit_lines(l)), y, k, l) for s, e, l, y, k in CAPS]
    count_cache = {}
    n = int(round(END * FPS))
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(FPS),
                          "-i", "-", "-c:v", "qtrle", path], stdin=subprocess.PIPE)
    for k in range(n):
        t = k / FPS
        fr = base.copy()
        for s, e, img, y, kind, lines in caps:
            if s <= t < e:
                dt = t - s
                a = min(1.0, (e - t) / 0.08)  # quick out
                if kind == "count":
                    val = int(min(1, dt / 1.2) ** 0.6 * 500)
                    key = val // 5 * 5
                    if key not in count_cache:
                        count_cache[key] = text_block(fit_lines([(f"{key}+", YEL, B + 60), ("WORKERS", WHITE, S + 6)]))
                    img = count_cache[key]
                paste_scaled(fr, img, W / 2, y, ease_pop(dt), a)
        # logo card around "Myden" in VO
        if 20.55 <= t < 22.15:
            paste_scaled(fr, logo_card, W / 2, 1300, ease_pop(t - 20.55), min(1, (22.15 - t) / 0.1))
        # contact button pulse
        if 65.9 <= t < 68.25:
            s = ease_pop(t - 65.9) * (1 + 0.04 * math.sin((t - 65.9) * 8))
            paste_scaled(fr, contact, W / 2, 1480, s)
        # end card
        if t >= 68.3:
            paste_scaled(fr, end_card, W / 2, 900, ease_pop(t - 68.3))
            if t >= 69.3:
                paste_scaled(fr, follow, W / 2, 1450, ease_pop(t - 69.3) * (1 + 0.04 * math.sin((t - 69.3) * 7)))
        p.stdin.write(fr.tobytes())
    p.stdin.close(); p.wait()

if __name__ == "__main__":
    step = sys.argv[1]
    if step == "shots":
        tot = sum(s[2] for s in SHOTS); print("timeline", round(tot, 2))
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(4) as ex:
            outs = list(ex.map(lambda a: render_shot(*a), enumerate(SHOTS)))
        with open(f"{D}/concat.txt", "w") as f:
            for o in outs: f.write(f"file '{o}'\n")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", f"{D}/concat.txt", "-c", "copy", f"{D}/base.mp4"], check=True)
    elif step == "overlay":
        build_overlay(f"{D}/overlay.mov")
