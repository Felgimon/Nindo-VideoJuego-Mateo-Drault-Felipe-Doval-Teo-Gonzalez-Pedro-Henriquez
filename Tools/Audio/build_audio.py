"""Genera todo el audio de Nindō en Nindo/Assets/Nindo/Audio.

    python3 Tools/Audio/build_audio.py [--only sfx|amb|music] [--key nombre]

* Efectos (Sfx/<clave>_<n>.wav): mezcla de sonidos CC0 de Kenney (impactos, pasos, interfaz)
  con capas sintetizadas (acero, silbidos, campanas, magia) para que todo tenga la misma
  identidad sonora.  La clave es la que usa el código: Game.Audio.Play("clave").
* Ambientes (Ambience/<clave>.ogg): loops de ~40 s 100% sintetizados (grillos, viento,
  agua, bambú, shishi-odoshi...).
* Música (Music/<clave>.ogg): temas CC0 de OpenGameArt (ver CREDITS.md), normalizados en
  sonoridad y convertidos a OGG.

Las fuentes descargadas se guardan en Tools/Audio/.cache (no se versionan).
Después: python3 Tools/Unity/generate_assets.py (registra los clips en NindoContent).
"""
import os, sys, glob, json, zipfile, subprocess, argparse
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dsp import *  # noqa

REPO = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(REPO, "Nindo", "Assets", "Nindo", "Audio")
CACHE = os.path.join(HERE, ".cache")

KENNEY = {
    "impact": "https://kenney.nl/media/pages/assets/impact-sounds/87b4ddecda-1677589768/kenney_impact-sounds.zip",
    "rpg": "https://kenney.nl/media/pages/assets/rpg-audio/8e99002d76-1677590336/kenney_rpg-audio.zip",
    "interface": "https://kenney.nl/media/pages/assets/interface-sounds/fa43c1dd4d-1677589452/kenney_interface-sounds.zip",
}

# clave -> (archivo, autor, página). Todas CC0.
MUSIC = {
    "menu": ("https://opengameart.org/sites/default/files/orientalsomber_0.ogg", "Tozan", "https://opengameart.org/content/oriental-somber"),
    "explore_home": ("https://opengameart.org/sites/default/files/tyhosigarden3_0.ogg", "Tozan", "https://opengameart.org/content/tyhosi-garden-3"),
    "explore_forest": ("https://opengameart.org/sites/default/files/lapsykoto_0.ogg", "Tozan", "https://opengameart.org/content/lapsy-koto"),
    "explore_garden": ("https://opengameart.org/sites/default/files/asianoriental1_0.ogg", "Tozan", "https://opengameart.org/content/asianoriental1"),
    "explore_dojo": ("https://opengameart.org/sites/default/files/japnkoto_0.ogg", "Tozan", "https://opengameart.org/content/rpjian"),
    "explore_mountain": ("https://opengameart.org/sites/default/files/orient8_0.ogg", "Tozan", "https://opengameart.org/content/oriental8"),
    "explore_lake": ("https://opengameart.org/sites/default/files/hot_spring_town_1.ogg", "Kistol", "https://opengameart.org/content/hot-springs-town"),
    "combat": ("https://opengameart.org/sites/default/files/BeepBox-Song_0.wav", "Pepsidog", "https://opengameart.org/content/looping-japanese-fight-track"),
    "boss": ("https://opengameart.org/sites/default/files/boss_koto_0.mp3", "G_P", "https://opengameart.org/content/bosskoto"),
    "boss_final": ("https://opengameart.org/sites/default/files/Great%20Boss_0.ogg", "Spring Spring", "https://opengameart.org/content/great-boss"),
    "gameover": ("https://opengameart.org/sites/default/files/Death%20of%20a%20Ninja%20%28Game%20Over%29.mp3", "Joth", "https://opengameart.org/content/death-of-a-ninja-game-over"),
    "ending": ("https://opengameart.org/sites/default/files/The_fallen_samurai.mp3", "Pro Sensory", "https://opengameart.org/content/the-last-samurai"),
}
# sonoridad objetivo (LUFS): la exploración más suave que el combate
LOUDNESS = {"combat": -15, "boss": -14, "boss_final": -14, "gameover": -16, "ending": -16}


def fetch(url, name):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, name)
    if not os.path.exists(p):
        print("  descargando", url)
        subprocess.run(["curl", "-sSL", "--max-time", "300", "-o", p, url], check=True)
    return p


_kenney = {}


def kenney(name):
    """Ruta a un .ogg de Kenney por nombre de archivo (sin extensión)."""
    if not _kenney:
        for pack, url in KENNEY.items():
            z = fetch(url, f"kenney_{pack}.zip")
            d = os.path.join(CACHE, f"kenney_{pack}")
            if not os.path.isdir(d):
                zipfile.ZipFile(z).extractall(d)
            for f in glob.glob(os.path.join(d, "**", "*.ogg"), recursive=True):
                _kenney[os.path.splitext(os.path.basename(f))[0]] = f
    return load(_kenney[name])


def K(name, gain=1.0):
    x = kenney(name)
    return x / (np.max(np.abs(x)) + 1e-9) * gain


# ============================================================================ EFECTOS
SFX = {}


def sfx(key, n=1):
    def deco(fn):
        SFX[key] = (fn, n)
        return fn
    return deco


def slash_noise(seed, dur=0.09, lo=3000, hi=11000):
    return filt(noise(dur, seed), lo, hi) * env_exp(dur, dur * 0.25, 0.001)


@sfx("swing", 4)
def _swing(i):
    d = 0.26 + 0.03 * i
    f = [1.0, 1.15, 0.9, 1.05][i]
    w = whoosh(d, 700 * f, 3200 * f, peak_t=0.35, q=1.6, seed=10 + i)
    air = whoosh(d * 0.8, 2500, 6000, peak_t=0.3, q=2.0, seed=20 + i)
    return mix((w, 0, 1.0), (air, 0.01, 0.35))


@sfx("enemy_swing", 3)
def _eswing(i):
    d = 0.32
    w = whoosh(d, 450, 1900, peak_t=0.4, q=1.4, seed=30 + i)
    return w


@sfx("enemy_swing_heavy", 2)
def _eswing_h(i):
    d = 0.55
    w = whoosh(d, 220, 1100, peak_t=0.5, q=1.1, seed=40 + i)
    rum = filt(noise(d, 45 + i), 40, 180) * env_ar(d, d * 0.5)
    return mix((w, 0, 1.0), (rum, 0, 0.8))


@sfx("hit", 4)
def _hit(i):
    body = K(["impactPunch_medium_000", "impactPunch_medium_001", "impactPunch_medium_002", "impactPunch_medium_003"][i])
    cut = slash_noise(50 + i, 0.08)
    ring = metal(2400 + 300 * i, 0.25, 0.06, seed=55 + i) * 0.25
    return mix((body, 0, 1.0), (cut, 0, 0.55), (ring, 0, 0.5))


@sfx("hit_heavy", 3)
def _hit_h(i):
    body = K(["impactPunch_heavy_000", "impactPunch_heavy_001", "impactPunch_heavy_002"][i])
    low = thump(110, 45, 0.35, 0.12, seed=60 + i)
    cut = slash_noise(62 + i, 0.12, 2000, 9000)
    return mix((body, 0, 1.0), (low, 0, 0.9), (cut, 0, 0.5))


@sfx("clang", 4)
def _clang(i):
    k = K(["impactMetal_medium_000", "impactMetal_medium_001", "impactMetal_medium_002", "impactMetal_medium_003"][i])
    ring = metal(1500 + 180 * i, 0.6, 0.18, seed=70 + i)
    return mix((k, 0, 0.9), (ring, 0, 0.45))


@sfx("parry", 3)
def _parry(i):
    k = K(["impactMetal_light_000", "impactMetal_light_001", "impactMetal_light_002"][i])
    ring = metal(2200 + 250 * i, 0.9, 0.28, seed=80 + i)
    spark = filt(noise(0.05, 85 + i), 5000, 14000) * env_exp(0.05, 0.01)
    return reverb(mix((k, 0, 0.8), (ring, 0, 0.6), (spark, 0, 0.4)), 0.18, 1.0, 0.25)


@sfx("parry_perfect")
def _parry_perfect(i):
    k = K("impactMetal_heavy_001", 0.8)
    ring = metal(1760, 2.2, 0.8, seed=90, bright=1.3)
    ring2 = metal(2637, 2.2, 0.6, seed=91)
    sub = thump(90, 40, 0.6, 0.25, seed=92)
    shim = filt(noise(1.2, 93), 6000, 14000) * env_exp(1.2, 0.3)
    x = mix((k, 0, 0.8), (ring, 0, 0.55), (ring2, 0, 0.35), (sub, 0, 0.9), (shim, 0, 0.12))
    return reverb(x, 0.35, 2.4, 0.7)


@sfx("parry_ready")
def _parry_ready(i):
    ping = partials(3150, [1, 2.0, 2.76], [1, 0.3, 0.2], [0.12, 0.06, 0.05], 0.25, 95)
    return mix((K("metalClick", 0.5), 0, 0.6), (ping, 0.005, 0.5))


@sfx("perfect_dodge")
def _pdodge(i):
    d = 0.6
    rev = whoosh(d, 600, 5000, peak_t=0.85, q=1.2, seed=100)
    gl = osc(glide(900, 2400, d, 2.0), d) * env_points(d, [(0, 0), (0.5, 0.3), (0.6, 0)])
    shim = filt(noise(0.7, 101), 7000, 15000) * env_exp(0.7, 0.18)
    return reverb(mix((rev, 0, 1.0), (gl, 0, 0.25), (shim, 0.5, 0.4)), 0.3, 1.5, 0.4)


@sfx("dash", 2)
def _dash(i):
    d = 0.24
    return mix((whoosh(d, 400, 2400, 0.25, 1.2, seed=110 + i), 0, 1.0), (K(["cloth1", "cloth2"][i], 0.6), 0, 1.0))


@sfx("alert")
def _alert(i):
    a = pluck(880, 0.6, 1.3, 0.4, seed=120)
    b = pluck(932, 0.6, 1.3, 0.4, seed=121)
    sw = whoosh(0.25, 800, 3000, 0.9, 1.5, seed=122)
    return reverb(mix((sw, 0, 0.4), (a, 0.18, 0.8), (b, 0.26, 0.8)), 0.25, 1.2, 0.3)


@sfx("danger")
def _danger(i):
    # aviso de ataque imparable (危): golpe grave metálico + campana disonante + latigazo
    d = 1.3
    rev = whoosh(0.45, 300, 4000, 0.95, 1.0, seed=130)
    b1 = bell(146.8, d, 0.7, 1.4, seed=131)
    b2 = bell(155.6, d, 0.6, 1.2, seed=132)
    sub = thump(80, 38, 0.8, 0.35, seed=133)
    x = mix((rev, 0, 0.6), (b1, 0.42, 0.7), (b2, 0.42, 0.5), (sub, 0.42, 1.0))
    return reverb(distort(x, 1.6), 0.3, 2.0, 0.6)


@sfx("exhausted")
def _exhausted(i):
    k = K("impactPlate_heavy_002", 0.9)
    gl = osc(glide(620, 280, 0.9, 0.7), 0.9) * env_exp(0.9, 0.35) * 0.4
    ring = metal(900, 1.0, 0.35, seed=140)
    return reverb(mix((k, 0, 1.0), (ring, 0, 0.35), (gl, 0.02, 0.6)), 0.25, 1.5, 0.45)


@sfx("posture_break")
def _posture(i):
    k = K("impactPlate_heavy_000", 1.0)
    g = K("impactGlass_heavy_001", 0.5)
    sub = thump(100, 40, 0.5, 0.2, seed=150)
    return reverb(mix((k, 0, 1.0), (g, 0, 0.5), (sub, 0, 1.0)), 0.25, 1.4, 0.4)


@sfx("kill")
def _kill(i):
    shing = sweep(noise(0.35, 160), 3000, 9000, q=2.5) * env_exp(0.35, 0.09)
    ring = metal(3000, 1.0, 0.35, seed=161)
    sub = thump(70, 35, 0.6, 0.25, seed=162)
    body = K("impactPunch_heavy_003", 0.8)
    return reverb(mix((shing, 0, 0.8), (ring, 0, 0.35), (body, 0.02, 0.8), (sub, 0.02, 1.0)), 0.3, 1.8, 0.55)


@sfx("death")
def _death(i):
    d = 3.0
    sub = thump(60, 28, 1.2, 0.5, seed=170)
    b = bell(98, d, 1.6, 0.6, seed=171)
    swell = filt(noise(1.0, 172), 200, 2000) * env_points(1.0, [(0, 0), (0.95, 1), (1.0, 0)]) ** 2
    return reverb(mix((swell, 0, 0.5), (sub, 1.0, 1.0), (b, 1.0, 0.6)), 0.4, 3.0, 1.0)


@sfx("slam")
def _slam(i):
    sub = thump(90, 30, 1.0, 0.35, seed=180)
    crack = filt(noise(0.4, 181), 80, 600) * env_exp(0.4, 0.12)
    debris = mix((K("impactMining_001", 0.6), 0.05, 1), (K("impactMining_003", 0.5), 0.14, 1), (K("impactWood_heavy_002", 0.5), 0.09, 1))
    rumble = filt(noise(1.4, 182), 25, 120) * env_exp(1.4, 0.45)
    return reverb(distort(mix((sub, 0, 1.0), (crack, 0, 0.9), (debris, 0, 0.6), (rumble, 0, 0.8)), 1.4), 0.25, 1.8, 0.6)


@sfx("wave")
def _wave(i):
    d = 1.1
    w = whoosh(d, 200, 3500, 0.35, 0.9, seed=190, curve=lambda t: 200 + 3300 * np.sin(np.pi * min(1, t * 1.2)))
    rum = filt(noise(d, 191), 30, 150) * env_ar(d, 0.15)
    return reverb(mix((w, 0, 1.0), (rum, 0, 0.9)), 0.25, 1.6, 0.5)


@sfx("teleport")
def _teleport(i):
    poof = filt(noise(0.5, 200), 500, 4000) * env_exp(0.5, 0.08)
    rev = whoosh(0.35, 3000, 600, 0.9, 1.3, seed=201)
    shim = sweep(noise(0.6, 202), 4000, 10000, q=3) * env_exp(0.6, 0.2)
    return reverb(mix((rev, 0, 0.6), (poof, 0.3, 1.0), (shim, 0.3, 0.35)), 0.35, 1.6, 0.45)


@sfx("summon")
def _summon(i):
    d = 1.4
    tones = sum(osc(glide(f, f * 1.5, d, 1.5), d, "saw") for f in (110, 116.5, 164.8))
    tones = sweep(tones, 300, 2500, mode="low") * env_points(d, [(0, 0), (1.1, 1), (1.4, 0)])
    hiss = filt(noise(d, 210), 2000, 8000) * env_points(d, [(0, 0), (1.2, 0.6), (1.4, 0)])
    return reverb(mix((tones, 0, 0.5), (hiss, 0, 0.3)), 0.4, 2.0, 0.6)


@sfx("boss_roar")
def _roar(i):
    d = 1.8
    f = glide(85, 62, d, 0.6) * (1 + 0.03 * osc(5.5, d))
    src = osc(f, d, "saw") * (1 + 0.6 * osc(31, d, "square"))
    src = src + 0.6 * filt(noise(d, 220), 100, 3000)
    v = peak(peak(peak(src, 520, 120, 6), 1100, 200, 4), 2600, 400, 2)
    v = filt(v, 60, 5000) * env_points(d, [(0, 0), (0.15, 1), (1.2, 0.8), (1.8, 0)])
    return reverb(distort(v, 3.0), 0.35, 2.2, 0.7)


@sfx("boss_defeat")
def _boss_defeat(i):
    sub = thump(70, 25, 1.5, 0.6, seed=230)
    b = bell(130.8, 6.0, 3.0, 0.9, seed=231)
    shim = filt(noise(3.0, 232), 5000, 12000) * env_exp(3.0, 0.9)
    return reverb(mix((sub, 0, 1.0), (b, 0.05, 0.8), (shim, 0.1, 0.12)), 0.35, 3.5, 1.4)


@sfx("rage_on")
def _rage(i):
    d = 1.1
    fire = filt(noise(d, 240), 200, 5000) * (0.6 + 0.4 * np.abs(filt(noise(d, 241), None, 20)) * 4) * env_ar(d, 0.25)
    tone = distort(osc(glide(110, 220, d, 0.5), d, "saw"), 2) * env_ar(d, 0.3) * 0.4
    tone = filt(tone, None, 1800)
    taiko = thump(140, 60, 0.6, 0.2, seed=242)
    return reverb(mix((taiko, 0, 1.0), (fire, 0, 0.7), (tone, 0, 0.6)), 0.3, 1.5, 0.5)


@sfx("ability_charge")
def _charge(i):
    d = 0.7
    x = sum(osc(glide(f, f * 2, d, 1.8), d) / (k + 1) for k, f in enumerate((440, 660, 880)))
    x = x * env_points(d, [(0, 0), (0.6, 1), (0.7, 0)])
    hiss = sweep(noise(d, 250), 1000, 8000, q=2) * env_points(d, [(0, 0), (0.65, 0.8), (0.7, 0)])
    return mix((x, 0, 0.4), (hiss, 0, 0.6))


@sfx("ability_wind")
def _wind(i):
    d = 0.9
    w = whoosh(d, 300, 7000, 0.3, 1.3, seed=260)
    whistle = osc(glide(1800, 700, d, 0.5), d) * env_points(d, [(0, 0), (0.12, 1), (d, 0)]) ** 2
    cut = slash_noise(261, 0.2, 2500, 12000)
    return reverb(mix((w, 0, 1.0), (whistle, 0, 0.18), (cut, 0.05, 0.6)), 0.3, 1.5, 0.45)


@sfx("ability_whirl")
def _whirl(i):
    d = 1.0
    x = noise(d, 270)
    y = sweep(x, 500, 2500, q=1.2, curve=lambda t: 900 + 700 * np.sin(2 * np.pi * 5 * t))
    am = 0.5 + 0.5 * np.abs(np.sin(np.pi * 5.5 * t_axis(d)))
    return reverb(y * am * env_ar(d, 0.1, 1.2), 0.25, 1.2, 0.35)


@sfx("checkpoint")
def _checkpoint(i):
    b = bell(523.3, 3.5, 1.4, 0.7, seed=280)
    b2 = bell(784, 3.0, 1.0, 0.5, seed=281)
    return reverb(mix((b, 0, 0.8), (b2, 0.35, 0.4)), 0.35, 3.0, 1.0)


@sfx("seal")
def _seal(i):
    notes = [587.3, 698.5, 784, 880, 1174.7]   # escala in (D)
    parts = [(bell(f, 2.5, 1.1, 0.6, seed=290 + k), 0.11 * k, 0.6) for k, f in enumerate(notes)]
    shim = filt(noise(2.5, 299), 6000, 14000) * env_ar(2.5, 0.4)
    return reverb(mix(*parts, (shim, 0, 0.08)), 0.4, 3.0, 1.0)


@sfx("portal")
def _portal(i):
    d = 1.6
    hum = sum(osc(f * (1 + 0.004 * osc(0.7 + k, d)), d) for k, f in enumerate((110, 165, 220.5)))
    hum = hum * env_ar(d, 0.4)
    spark = sweep(noise(d, 300), 3000, 9000, q=3) * env_ar(d, 0.3) * (0.5 + 0.5 * osc(9, d))
    return reverb(mix((hum, 0, 0.35), (spark, 0, 0.35)), 0.4, 2.0, 0.7)


@sfx("gate_open")
def _gate(i):
    creak = mix((K("creak1", 0.8), 0, 1), (K("creak3", 0.7), 0.6, 1))
    rumble = filt(noise(2.2, 310), 30, 160) * env_ar(2.2, 0.5)
    thud = thump(80, 40, 0.5, 0.2, seed=311)
    return reverb(mix((creak, 0, 0.8), (rumble, 0, 0.7), (thud, 1.9, 0.9)), 0.3, 2.0, 0.6)


@sfx("barrier")
def _barrier(i):
    t = thump(160, 70, 0.4, 0.12, seed=320)
    sh = sweep(noise(0.6, 321), 2000, 600, q=2) * env_exp(0.6, 0.15)
    return reverb(mix((t, 0, 1.0), (sh, 0, 0.5)), 0.3, 1.2, 0.35)


@sfx("lock")
def _lock(i):
    return mix((K("metalLatch", 0.5), 0, 1), (partials(2637, [1, 2.0], [1, 0.25], [0.08, 0.04], 0.2, 330), 0.01, 0.35))


@sfx("denied")
def _denied(i):
    return K("error_004", 0.8)


@sfx("ui_move", 2)
def _ui_move(i):
    for name in (f"tick_00{i + 1}", f"select_00{i + 1}", f"click_00{i + 1}"):
        if name in _kenney:
            return K(name, 0.6)
    raise KeyError("ui_move")


@sfx("ui_open")
def _ui_open(i):
    return K("open_001", 0.8)


@sfx("ui_close")
def _ui_close(i):
    return K("close_001", 0.8)


@sfx("ui_start")
def _ui_start(i):
    notes = [293.7, 440, 587.3]
    ps = [(pluck(f, 2.2, 1.0, 1.0, seed=340 + k), 0.07 * k, 0.6) for k, f in enumerate(notes)]
    b = bell(587.3, 3.0, 1.2, 0.5, seed=345)
    return reverb(mix(*ps, (b, 0.2, 0.35)), 0.4, 2.6, 0.9)


@sfx("area_title")
def _area(i):
    notes = [293.7, 311.1, 392, 440, 587.3]  # D Eb G A D: escala in
    ps = [(pluck(f, 2.4, 0.9, 1.1, seed=350 + k), 0.13 * k, 0.5) for k, f in enumerate(notes)]
    return reverb(mix(*ps), 0.45, 2.8, 1.0)


@sfx("dialogue", 3)
def _dialogue(i):
    f = [1200, 1350, 1100][i]
    click = band(noise(0.05, 360 + i), f, 3) * env_exp(0.05, 0.01)
    body = partials(f * 0.5, [1, 2.3], [1, 0.4], [0.03, 0.015], 0.08, 363 + i)
    return mix((click, 0, 0.7), (body, 0, 0.4))


@sfx("finisher_start")
def _finisher_start(i):
    draw = K("drawKnife1", 0.8)
    rev = whoosh(0.7, 200, 3000, 0.95, 1.0, seed=370)
    ring = metal(2800, 1.0, 0.4, seed=371)
    return reverb(mix((rev, 0, 0.7), (draw, 0.45, 0.8), (ring, 0.5, 0.25)), 0.3, 1.5, 0.45)


@sfx("finisher_hit", 2)
def _finisher_hit(i):
    body = K(["impactPunch_heavy_004", "impactPunch_heavy_002"][i])
    shing = sweep(noise(0.4, 380 + i), 2500, 10000, q=2.2) * env_exp(0.4, 0.1)
    sub = thump(80, 30, 0.7, 0.3, seed=382 + i)
    return reverb(mix((body, 0, 1.0), (shing, 0, 0.7), (sub, 0, 1.0)), 0.25, 1.4, 0.45)


def _steps(prefix, gain=1.0):
    def f(i):
        return K(f"{prefix}_00{i}", gain)
    return f


SFX["step"] = (_steps("footstep_grass"), 5)
SFX["step_snow"] = (_steps("footstep_snow"), 5)
SFX["step_wood"] = (_steps("footstep_wood"), 5)
SFX["step_stone"] = (_steps("footstep_concrete"), 5)


# pico de normalización por clave (los clips cortos de interfaz no deben sonar como un golpe)
PEAK = {"ui_move": -10, "ui_open": -7, "ui_close": -7, "dialogue": -12, "denied": -8, "lock": -8,
        "step": -4, "step_snow": -4, "step_wood": -4, "step_stone": -4, "parry_ready": -6, "area_title": -4}


# ============================================================================ AMBIENTES
AMB_LEN, AMB_X = 40.0, 3.0


def crickets(dur, seed, count=6, base=4300, level=1.0, far=0.0):
    r = rng(seed)
    out = np.zeros((secs(dur), 2))
    t = t_axis(dur)
    for c in range(count):
        f = base * r.uniform(0.9, 1.15)
        rate = r.uniform(0.55, 1.1)       # chirps por segundo
        pulses = r.integers(2, 5)
        env = np.zeros(len(t))
        tt = r.uniform(0, 1)
        while tt < dur:
            for p in range(pulses):
                s = secs(tt + p * 0.032)
                e = min(len(t), s + secs(0.018))
                if s < len(t):
                    env[s:e] = np.hanning(max(2, e - s))[:e - s]
            tt += (1 / rate) * r.uniform(0.85, 1.2)
        tone = np.sin(2 * np.pi * f * t + r.uniform(0, 6)) * env
        gain = level * r.uniform(0.25, 1.0) * (1 - far * r.uniform(0.3, 0.9))
        out += pan(tone * gain, r.uniform(-0.9, 0.9))
    return out


def wind_layer(dur, seed, lo=200, hi=900, level=1.0, gust=0.3):
    r = rng(seed)
    x = filt(np.cumsum(r.standard_normal(secs(dur))) * 0.02, 20, None)   # ruido marrón
    x = x + 0.3 * r.standard_normal(secs(dur))
    slow = filt(r.standard_normal(secs(dur)), None, 0.15, 1)
    slow = (slow - slow.min()) / (np.ptp(slow) + 1e-9)
    y = sweep(x, lo, hi, q=1.0, curve=lambda tt: lo + (hi - lo) * np.interp(tt, np.linspace(0, 1, len(slow[::4410])), slow[::4410]))
    y *= (1 - gust) + gust * slow
    L = y; R = np.roll(y, secs(0.013))
    return np.stack([L, R], 1) * level


def rustle(dur, seed, level=1.0):
    r = rng(seed)
    x = filt(r.standard_normal(secs(dur)), 2500, 9000)
    slow = filt(r.standard_normal(secs(dur)), None, 0.3, 1)
    slow = np.clip((slow - np.percentile(slow, 30)) / (np.ptp(slow) + 1e-9) * 2, 0, 1)
    crackle = (r.random(secs(dur)) < 0.002) * r.standard_normal(secs(dur)) * 6
    crackle = filt(crackle, 2000, 8000)
    y = (x + crackle) * slow
    return np.stack([y, filt(np.roll(y, secs(0.02)), 2500, 9000)], 1) * level


def events(dur, seed, every, fn, jitter=0.4, start=0.5):
    """coloca eventos sueltos (fn(seed)->estéreo) a lo largo del loop."""
    r = rng(seed)
    out = np.zeros((secs(dur + 4), 2))
    tt = start + r.uniform(0, every * jitter)
    k = 0
    while tt < dur:
        e = fn(seed * 100 + k)
        if e.ndim == 1:
            e = pan(e, r.uniform(-0.8, 0.8))
        i = secs(tt)
        n = min(len(e), len(out) - i)
        out[i:i + n] += e[:n]
        tt += every * r.uniform(1 - jitter, 1 + jitter)
        k += 1
    # lo que se pasa del loop vuelve al principio
    tail = out[secs(dur):]
    out = out[:secs(dur)]
    out[:len(tail)] += tail
    return out


def owl(seed):
    r = rng(seed)
    f = r.uniform(360, 420)
    hoot = lambda d: osc(glide(f * 1.04, f * 0.97, d), d) * env_points(d, [(0, 0), (0.05, 1), (d * 0.7, 0.8), (d, 0)])
    breath = lambda d: filt(noise(d, seed), 300, 1200) * env_ar(d, 0.05) * 0.15
    h1, h2 = hoot(0.28) + breath(0.28), hoot(0.5) + breath(0.5)
    x = mix((h1, 0, 0.8), (h2, 0.55, 1.0))
    return filt(reverb(x, 0.5, 2.5, 0.9), None, 2500) * 0.12


def frog(seed):
    r = rng(seed)
    d = r.uniform(0.25, 0.45)
    rate = r.uniform(18, 30)
    pulses = (osc(rate, d, "saw") > 0.6).astype(float)
    src = filt(pulses + 0.1 * noise(d, seed), 80, 4000)
    v = peak(peak(src, r.uniform(450, 700), 80, 8), 1300, 150, 4) * env_ar(d, 0.05)
    n = r.integers(1, 4)
    x = mix(*[(v, k * (d + 0.08), 1.0) for k in range(n)])
    return x * 0.1


def bird(seed):
    r = rng(seed)
    d = r.uniform(0.12, 0.25)
    f0 = r.uniform(2500, 3500)
    x = osc(f0 + 900 * osc(r.uniform(18, 30), d), d) * env_ar(d, 0.02)
    n = r.integers(2, 5)
    return reverb(mix(*[(x, k * (d + 0.05), 1.0) for k in range(n)]), 0.4, 1.5, 0.6) * 0.05


def bubbles(dur, seed, rate=40, level=1.0):
    r = rng(seed)
    out = np.zeros((secs(dur) + secs(0.1), 2))
    for k in range(int(dur * rate)):
        d = r.uniform(0.01, 0.035)
        f = r.uniform(900, 2800)
        b = osc(glide(f, f * r.uniform(1.3, 2.0), d), d) * env_exp(d, d * 0.4)
        i = secs(r.uniform(0, dur))
        out[i:i + len(b)] += pan(b * r.uniform(0.2, 1.0), r.uniform(-0.6, 0.6))
    out = out[:secs(dur)]
    bed = filt(noise(dur, seed + 1), 300, 2500) * 0.08
    out += np.stack([bed, np.roll(bed, 500)], 1)
    return out * level


def shishi_odoshi(seed):
    pour = filt(noise(0.8, seed), 600, 3000) * env_ar(0.8, 0.3) * 0.15
    knock = band(noise(0.1, seed + 1), 1100, 4) * env_exp(0.1, 0.012)
    body = partials(620, [1, 2.4, 3.9], [1, 0.5, 0.25], [0.09, 0.05, 0.03], 0.3, seed + 2)
    x = mix((pour, 0, 1.0), (knock, 0.85, 1.0), (body, 0.85, 0.8))
    return reverb(x, 0.45, 2.0, 0.6) * 0.5


def bamboo_knock(seed):
    r = rng(seed)
    n = r.integers(1, 4)
    parts = []
    for k in range(n):
        f = r.uniform(380, 900)
        body = partials(f, [1, 2.6, 4.1], [1, 0.4, 0.2], [0.12, 0.05, 0.03], 0.35, seed + k)
        click = band(noise(0.03, seed + 10 + k), f * 2, 3) * env_exp(0.03, 0.006)
        parts.append((mix((body, 0, 1.0), (click, 0, 0.5)), k * r.uniform(0.07, 0.2), r.uniform(0.5, 1.0)))
    return reverb(mix(*parts), 0.4, 1.6, 0.5) * 0.2


def lapping(dur, seed, level=1.0):
    r = rng(seed)
    x = filt(r.standard_normal(secs(dur)), 80, 700)
    swell = filt(r.standard_normal(secs(dur)), None, 0.35, 1)
    swell = np.clip((swell - swell.min()) / (np.ptp(swell) + 1e-9), 0, 1) ** 1.5
    splash = filt(r.standard_normal(secs(dur)), 1500, 6000) * swell ** 3 * 0.4
    y = x * (0.25 + swell) + splash
    return np.stack([y, np.roll(y, secs(0.03))], 1) * level


def amb_mix(layers):
    n = secs(AMB_LEN + AMB_X)
    out = np.zeros((n, 2))
    for x, g in layers:
        x = pad(x, n)
        out += x * g
    return loop_crossfade(out, AMB_LEN, AMB_X)


AMB = {}


def amb(key):
    def deco(fn):
        AMB[key] = fn
        return fn
    return deco


D = AMB_LEN + AMB_X


@amb("night")
def _night():
    return amb_mix([(crickets(D, 1, 7, 4400, 1.0), 0.05), (crickets(D, 2, 10, 3900, 0.6, far=0.8), 0.03),
                    (wind_layer(D, 3, 150, 500, 1.0, 0.4), 0.25), (events(D, 4, 13, owl), 1.0)])


@amb("forest")
def _forest():
    return amb_mix([(rustle(D, 11, 1.0), 0.05), (wind_layer(D, 12, 180, 700, 1.0, 0.5), 0.3),
                    (crickets(D, 13, 5, 3600, 0.6, far=0.6), 0.03), (events(D, 14, 9, owl), 0.9),
                    (events(D, 15, 6, bamboo_knock), 0.25)])


@amb("garden")
def _garden():
    return amb_mix([(bubbles(D, 21, 35, 1.0), 0.35), (crickets(D, 22, 8, 4500, 1.0), 0.045),
                    (events(D, 23, 14, shishi_odoshi, 0.1, 3.0), 1.0), (wind_layer(D, 24, 200, 600, 1.0, 0.3), 0.12)])


@amb("wind")
def _wind_amb():
    return amb_mix([(wind_layer(D, 31, 250, 1300, 1.0, 0.7), 0.9), (wind_layer(D, 32, 600, 2200, 1.0, 0.8), 0.25),
                    (rustle(D, 33, 1.0), 0.02)])


@amb("water")
def _water():
    return amb_mix([(lapping(D, 41, 1.0), 0.6), (events(D, 42, 3.5, frog, 0.6), 1.0),
                    (crickets(D, 43, 6, 4100, 0.8, far=0.5), 0.035), (wind_layer(D, 44, 150, 500, 1.0, 0.3), 0.15)])


@amb("bamboo")
def _bamboo():
    return amb_mix([(rustle(D, 51, 1.0), 0.07), (wind_layer(D, 52, 220, 900, 1.0, 0.6), 0.35),
                    (events(D, 53, 2.2, bamboo_knock, 0.6), 0.9), (crickets(D, 54, 4, 4000, 0.6, far=0.7), 0.025),
                    (events(D, 55, 11, bird, 0.5), 0.6)])


# ============================================================================ MÚSICA
def build_music(only_key=None):
    credits = []
    done = {}
    for key, (url, author, page) in MUSIC.items():
        if only_key and key != only_key:
            continue
        name = url.split("/")[-1].replace("%20", "_").replace("%28", "(").replace("%29", ")")
        src = fetch(url, "music_" + name)
        out = os.path.join(OUT, "Music", key + ".ogg")
        if url in done:
            subprocess.run(["cp", done[url], out], check=True)
        else:
            lufs = LOUDNESS.get(key, -17)
            af = f"silenceremove=start_periods=1:start_threshold=-55dB,loudnorm=I={lufs}:TP=-1.5:LRA=11"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-af", af, "-ar", "44100",
                            "-ac", "2", "-c:a", "libvorbis", "-q:a", "4", out], check=True)
            done[url] = out
        credits.append(f"| `{key}` | [{page.split('/')[-1]}]({page}) | {author} | CC0 |")
        print("  música", key)
    return credits


def write_credits(music_credits):
    lines = ["# Créditos de audio", "",
             "Todo el audio nuevo de Nindō es CC0 (dominio público) o sintetizado por `Tools/Audio/build_audio.py`.", "",
             "## Música (OpenGameArt, CC0)", "", "| Clave | Tema | Autor | Licencia |", "|---|---|---|---|"]
    lines += music_credits
    lines += ["", "## Efectos", "",
              "* Impactos, pasos, crujidos e interfaz: packs *Impact Sounds*, *RPG Audio* e *Interface Sounds* de Kenney (www.kenney.nl), CC0.",
              "* Capas de acero, silbidos, campanas, magia y todos los ambientes: síntesis propia (numpy).",
              "* Clips originales del equipo (Assets/Audios): SwordSwing, SwordClash, Hurt, Dash, Finisher, Boton, Footsteps.", "",
              "> Ojo: `Assets/Audios/Satellite - John Coltrane.mp3` (y posiblemente `BackgroundMusic.mp3` /",
              "> `Menu-TheRainInfectsAllWaters.mp3`) tienen copyright de terceros: ya no se usan en el juego;",
              "> conviene borrarlos antes de publicar una build.", ""]
    open(os.path.join(OUT, "CREDITS.md"), "w").write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["sfx", "amb", "music"])
    ap.add_argument("--key")
    a = ap.parse_args()
    kenney("impactPunch_medium_000")  # asegura las descargas
    if a.only in (None, "sfx"):
        for key, (fn, n) in SFX.items():
            if a.key and key != a.key:
                continue
            for p in glob.glob(os.path.join(OUT, "Sfx", f"{key}_[0-9]*.wav")):
                os.remove(p)
            for i in range(n):
                write_wav(os.path.join(OUT, "Sfx", f"{key}_{i + 1}.wav"), fn(i), PEAK.get(key, -1.0))
            print("  sfx", key, n)
    if a.only in (None, "amb"):
        for key, fn in AMB.items():
            if a.key and key != a.key:
                continue
            write_ogg(os.path.join(OUT, "Ambience", key + ".ogg"), fn(), -3.0)
            print("  ambiente", key)
    if a.only in (None, "music"):
        cr = build_music(a.key)
        if not a.key:
            write_credits(cr)


if __name__ == "__main__":
    main()
