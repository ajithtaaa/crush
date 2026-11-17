#!/usr/bin/env python3
"""Synth upbeat music bed + whoosh SFX at caption hits."""
import numpy as np, wave, os, importlib.util
D = os.path.dirname(os.path.abspath(__file__))
SR = 44100; DUR = 71.6; BPM = 118; beat = 60 / BPM
N = int(SR * DUR); rng = np.random.default_rng(7)
mus = np.zeros((N, 2)); sfx = np.zeros((N, 2))

def add(buf, x, t, pan=0.0, g=1.0):
    i = int(t * SR); j = min(N, i + len(x))
    if i >= N: return
    seg = x[: j - i] * g
    buf[i:j, 0] += seg * (1 - max(0, pan)); buf[i:j, 1] += seg * (1 + min(0, pan))

def env(n, a=0.002, d=0.2):
    t = np.arange(n) / SR
    return np.minimum(1, t / a) * np.exp(-t / d)

def kick():
    n = int(0.35 * SR); t = np.arange(n) / SR
    f = 50 + 110 * np.exp(-t * 30)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.001, 0.12) * 0.9

def clap():
    n = int(0.25 * SR); x = rng.standard_normal(n)
    x = np.convolve(x, [1, -0.9], "same")
    e = env(n, 0.001, 0.06)
    return x * e * 0.25

def hat(open_=False):
    n = int((0.18 if open_ else 0.05) * SR); x = rng.standard_normal(n)
    x = np.diff(np.concatenate([[0], x]))
    return x * env(n, 0.0005, 0.06 if open_ else 0.015) * 0.12

def tone(freq, dur, kind="pluck", g=0.2):
    n = int(dur * SR); t = np.arange(n) / SR
    if kind == "pluck":
        x = (np.sign(np.sin(2 * np.pi * freq * t)) * 0.3 + np.sin(2 * np.pi * freq * t)) * env(n, 0.003, 0.18)
    elif kind == "bass":
        x = np.tanh(2 * np.sin(2 * np.pi * freq * t)) * env(n, 0.004, 0.25)
    else:  # pad
        x = sum(np.sin(2 * np.pi * freq * m * t + m) / m for m in (1, 2, 3)) * np.minimum(1, t / 0.3) * np.minimum(1, (dur - t) / 0.3)
    return x * g

midi = lambda m: 440 * 2 ** ((m - 69) / 12)
# I - V - vi - IV in C (C, G, Am, F)
chords = [(48, [60, 64, 67, 72]), (43, [59, 62, 67, 71]), (45, [60, 64, 69, 72]), (41, [60, 65, 69, 72])]
bars = int(DUR / (4 * beat)) + 1
for b in range(bars):
    t0 = b * 4 * beat
    root, notes = chords[b % 4]
    intro = b < 1
    add(mus, tone(midi(root + 12), 4 * beat, "pad", 0.05), t0)
    for st in range(16):  # 16th steps
        t = t0 + st * beat / 4
        if t >= DUR: break
        if st % 4 == 0 and not intro: add(mus, kick(), t)
        if st in (4, 12) and not intro: add(mus, clap(), t)
        if st % 2 == 0: add(mus, hat(st % 8 == 6), t, pan=0.3)
        if st % 2 == 0 and not intro:
            add(mus, tone(midi(root), beat / 2, "bass", 0.22), t)
        if st % 2 == 0:
            arp = notes[(st // 2) % 4]
            add(mus, tone(midi(arp + 12), beat / 2, "pluck", 0.07), t, pan=-0.25 if st % 4 else 0.25)
# fade out at end
fade = np.ones(N); fs = int((DUR - 2.0) * SR); fade[fs:] = np.linspace(1, 0, N - fs); mus *= fade[:, None]

# whoosh SFX at caption starts
spec = importlib.util.spec_from_file_location("b", f"{D}/build.py"); b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
def whoosh():
    n = int(0.35 * SR); x = rng.standard_normal(n); t = np.arange(n) / SR
    # sweeping lowpass via cumulative averaging with varying coefficient
    y = np.zeros(n); a = 0.0
    for i in range(n):
        k = 0.02 + 0.5 * (i / n) ** 2
        a += k * (x[i] - a); y[i] = a
    e = np.sin(np.pi * np.clip(t / 0.35, 0, 1)) ** 2
    return y * e * 0.6
w = whoosh()
for s, e, *_ in b.CAPS:
    add(sfx, w, max(0, s - 0.18), pan=rng.uniform(-0.4, 0.4), g=0.5)
for t in (20.4, 65.8, 68.15):
    add(sfx, w, t, g=0.7)

def save(path, x):
    x = x / (np.abs(x).max() + 1e-9) * 0.9
    with wave.open(path, "wb") as f:
        f.setnchannels(2); f.setsampwidth(2); f.setframerate(SR)
        f.writeframes((x * 32767).astype("<i2").tobytes())
save(f"{D}/music.wav", mus); save(f"{D}/sfx.wav", sfx)
print("ok")
