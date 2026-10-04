"""Mini librería de síntesis (numpy) para los efectos y ambientes de Nindō."""
import os, subprocess, wave
import numpy as np

SR = 44100


def secs(n):
    return int(round(n * SR))


def t_axis(dur):
    return np.arange(secs(dur)) / SR


def rng(seed):
    return np.random.default_rng(seed)


def noise(dur, seed=0):
    return rng(seed).standard_normal(secs(dur))


def pad(x, n):
    return np.pad(x, (0, max(0, n - len(x))))[:n] if x.ndim == 1 else np.pad(x, ((0, max(0, n - len(x))), (0, 0)))[:n]


def mix(*parts):
    """mix((señal, offset_seg, ganancia), ...) -> suma."""
    n = max(secs(o) + len(s) for s, o, g in parts)
    out = np.zeros(n)
    for s, o, g in parts:
        i = secs(o)
        out[i:i + len(s)] += s * g
    return out


# ---------------------------------------------------------------- envolventes
def env_exp(dur, decay, attack=0.002):
    t = t_axis(dur)
    a = np.clip(t / max(attack, 1e-5), 0, 1)
    return a * np.exp(-t / decay)


def env_ar(dur, attack, release_shape=2.0):
    """sube en 'attack' y cae hasta 0 al final (curva potencia)."""
    t = t_axis(dur)
    a = np.clip(t / max(attack, 1e-5), 0, 1)
    r = np.clip((dur - t) / max(dur - attack, 1e-5), 0, 1) ** release_shape
    return a * r


def env_points(dur, pts):
    """pts = [(t, v), ...] interpolación lineal."""
    t = t_axis(dur)
    xs, ys = zip(*pts)
    return np.interp(t, xs, ys)


def fade(x, fin=0.003, fout=0.01):
    x = x.copy()
    a, b = secs(fin), secs(fout)
    if a: x[:a] *= np.linspace(0, 1, a)
    if b: x[-b:] *= np.linspace(1, 0, b)
    return x


# ---------------------------------------------------------------- filtros (dominio de frecuencia)
def _mask(freqs, lo=None, hi=None, order=2):
    m = np.ones_like(freqs)
    f = np.maximum(freqs, 1e-3)
    if lo:
        m *= 1.0 / np.sqrt(1.0 + (lo / f) ** (2 * order))
    if hi:
        m *= 1.0 / np.sqrt(1.0 + (f / hi) ** (2 * order))
    return m


def filt(x, lo=None, hi=None, order=2):
    n = len(x)
    N = 1 << int(np.ceil(np.log2(max(n, 2) * 2)))
    X = np.fft.rfft(x, N)
    f = np.fft.rfftfreq(N, 1 / SR)
    return np.fft.irfft(X * _mask(f, lo, hi, order), N)[:n]


def band(x, center, q=2.0, order=2):
    bw = center / q
    return filt(x, center - bw / 2, center + bw / 2, order)


def peak(x, center, width, gain):
    """realza una banda (formantes)."""
    n = len(x)
    N = 1 << int(np.ceil(np.log2(max(n, 2) * 2)))
    X = np.fft.rfft(x, N)
    f = np.fft.rfftfreq(N, 1 / SR)
    m = 1 + gain * np.exp(-0.5 * ((f - center) / width) ** 2)
    return np.fft.irfft(X * m, N)[:n]


def sweep(x, f0, f1, q=1.5, mode="band", frame=2048, curve=None):
    """filtro variable en el tiempo (STFT + overlap-add). f0->f1 (o curva(t01)->hz)."""
    hop = frame // 4
    win = np.hanning(frame)
    n = len(x)
    xp = np.pad(x, (frame, frame + hop))
    out = np.zeros_like(xp)
    norm = np.zeros_like(xp)
    freqs = np.fft.rfftfreq(frame, 1 / SR)
    nframes = (len(xp) - frame) // hop
    for i in range(nframes):
        s = i * hop
        t01 = np.clip((s - frame) / max(n, 1), 0, 1)
        fc = curve(t01) if curve else f0 * (f1 / f0) ** t01
        if mode == "band":
            m = _mask(freqs, fc / (1 + 0.5 / q), fc * (1 + 0.5 / q), 2)
        elif mode == "low":
            m = _mask(freqs, None, fc, 2)
        else:
            m = _mask(freqs, fc, None, 2)
        seg = np.fft.irfft(np.fft.rfft(xp[s:s + frame] * win) * m, frame) * win
        out[s:s + frame] += seg
        norm[s:s + frame] += win * win
    out = out / np.maximum(norm, 1e-3)
    return out[frame:frame + n]


# ---------------------------------------------------------------- osciladores
def osc(freq, dur, shape="sine", phase=0.0):
    """freq: número o array (Hz por muestra)."""
    n = secs(dur)
    f = np.full(n, float(freq)) if np.isscalar(freq) else pad(np.asarray(freq, float), n)
    ph = phase + 2 * np.pi * np.cumsum(f) / SR
    if shape == "sine":
        return np.sin(ph)
    p = (ph / (2 * np.pi)) % 1.0
    if shape == "saw":
        return 2 * p - 1
    if shape == "square":
        return np.sign(np.sin(ph))
    if shape == "tri":
        return 2 * np.abs(2 * p - 1) - 1
    raise ValueError(shape)


def glide(f0, f1, dur, curve=1.0):
    t = np.linspace(0, 1, secs(dur)) ** curve
    return f0 * (f1 / f0) ** t


def partials(freq, ratios, amps, decays, dur, seed=0, detune=0.0):
    """síntesis modal: suma de parciales con caída exponencial independiente."""
    r = rng(seed)
    t = t_axis(dur)
    out = np.zeros_like(t)
    for k, (ra, a, d) in enumerate(zip(ratios, amps, decays)):
        f = freq * ra * (1 + detune * r.uniform(-1, 1))
        out += a * np.sin(2 * np.pi * f * t + r.uniform(0, 6.28)) * np.exp(-t / d)
    return out


def bell(freq, dur, decay=2.0, bright=1.0, seed=0):
    """campana de templo (parciales inarmónicos típicos de campana)."""
    ratios = [0.5, 1.0, 1.183, 1.506, 2.0, 2.514, 2.662, 3.011, 4.166, 5.433]
    amps = [0.6, 1.0, 0.7, 0.55, 0.45, 0.35, 0.3, 0.22, 0.15 * bright, 0.1 * bright]
    decays = [decay * 1.3, decay, decay * 0.8, decay * 0.6, decay * 0.5, decay * 0.35, decay * 0.3, decay * 0.25, decay * 0.15, decay * 0.1]
    x = partials(freq, ratios, amps, decays, dur, seed, detune=0.002)
    # batido lento típico de las campanas grandes
    t = t_axis(dur)
    x *= 1 + 0.12 * np.sin(2 * np.pi * 1.7 * t)
    strike = filt(noise(0.03, seed + 1), 1500, 7000) * env_exp(0.03, 0.006)
    return mix((x, 0, 1.0), (strike, 0, 0.25 * bright))


def pluck(freq, dur, bright=1.0, decay=1.2, seed=0, nh=18):
    """cuerda pulsada tipo koto (aditiva: los armónicos agudos caen antes)."""
    k = np.arange(1, nh + 1)
    pos = 0.18
    amps = np.abs(np.sin(np.pi * k * pos)) / k ** (1.25 - 0.35 * bright)
    decays = decay / (1 + 0.35 * (k - 1) ** 1.25)
    ratios = k * (1 + 0.0004 * k * k)  # leve inarmonicidad
    x = partials(freq, ratios, amps, decays, dur, seed)
    # pequeño "bend" inicial
    pick = filt(noise(0.02, seed + 3), 2000, 9000) * env_exp(0.02, 0.004)
    return mix((x, 0, 1.0), (pick, 0, 0.15 * bright))


def metal(freq, dur, decay=0.6, seed=0, bright=1.0):
    """golpe metálico (hoja contra hoja): parciales de placa/barra libre."""
    ratios = [1.0, 2.756, 5.404, 8.933, 13.34, 1.49, 3.9]
    amps = [1.0, 0.8, 0.55, 0.35 * bright, 0.2 * bright, 0.4, 0.3]
    decays = [decay, decay * 0.7, decay * 0.45, decay * 0.3, decay * 0.2, decay * 0.9, decay * 0.5]
    x = partials(freq, ratios, amps, decays, dur, seed, detune=0.004)
    return x


def whoosh(dur, f0, f1, peak_t=0.45, q=1.4, seed=0, curve=None, rough=0.0):
    x = noise(dur, seed)
    if rough:
        x *= 1 + rough * osc(np.full(secs(dur), 0.0) + rng(seed).uniform(40, 70), dur, "square")
    y = sweep(x, f0, f1, q=q, curve=curve)
    e = env_points(dur, [(0, 0), (dur * peak_t, 1), (dur, 0)]) ** 1.6
    return y * e


def thump(f0, f1, dur, decay, seed=0):
    f = glide(f0, f1, dur, 0.4)
    x = osc(f, dur) * env_exp(dur, decay, 0.001)
    click = filt(noise(0.012, seed), 200, 3000) * env_exp(0.012, 0.003)
    return mix((x, 0, 1.0), (click, 0, 0.3))


def distort(x, drive=2.0):
    return np.tanh(x * drive) / np.tanh(drive)


# ---------------------------------------------------------------- espacio
def reverb_ir(dur=2.0, decay=0.6, seed=7, stereo=False, damp=6000):
    n = secs(dur)
    t = np.arange(n) / SR
    chans = []
    for c in range(2 if stereo else 1):
        r = rng(seed + c).standard_normal(n) * np.exp(-t / decay)
        # agudos se apagan antes
        lo = filt(r, None, damp * 0.4)
        hi = r - lo
        r = lo + hi * np.exp(-t / (decay * 0.35))
        r[:secs(0.012)] *= np.linspace(0, 1, secs(0.012))
        chans.append(r / np.sqrt(np.sum(r * r)))
    return np.stack(chans, 1) if stereo else chans[0]


def convolve(x, ir):
    n = len(x) + len(ir) - 1
    N = 1 << int(np.ceil(np.log2(n)))
    return np.fft.irfft(np.fft.rfft(x, N) * np.fft.rfft(ir, N), N)[:n]


def reverb(x, wet=0.25, dur=1.8, decay=0.5, seed=7, tail=True):
    ir = reverb_ir(dur, decay, seed)
    w = convolve(x, ir)
    d = np.pad(x, (0, len(w) - len(x)))
    out = d * (1 - wet * 0.5) + w * wet
    return out if tail else out[:len(x)]


def reverb_stereo(x, wet=0.3, dur=2.5, decay=0.8, seed=9):
    """mono/estéreo -> estéreo con cola decorrelacionada."""
    if x.ndim == 1:
        x = np.stack([x, x], 1)
    ir = reverb_ir(dur, decay, seed, stereo=True)
    L = convolve(x[:, 0], ir[:, 0]); R = convolve(x[:, 1], ir[:, 1])
    n = len(L)
    d = np.pad(x, ((0, n - len(x)), (0, 0)))
    return d * (1 - wet * 0.5) + np.stack([L, R], 1) * wet


def pan(x, p):
    """p -1 (izq) .. 1 (der), ley de potencia constante."""
    a = (p + 1) * np.pi / 4
    return np.stack([x * np.cos(a), x * np.sin(a)], 1)


# ---------------------------------------------------------------- E/S
def normalize(x, peak_db=-1.0):
    m = np.max(np.abs(x)) + 1e-9
    return x * (10 ** (peak_db / 20) / m)


def trim_silence(x, thresh=1e-4):
    a = np.abs(x) if x.ndim == 1 else np.max(np.abs(x), 1)
    idx = np.where(a > thresh * np.max(a))[0]
    if len(idx) == 0:
        return x
    return x[:idx[-1] + secs(0.01)]


def write_wav(path, x, peak_db=-1.0, do_trim=True):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if do_trim:
        x = trim_silence(x)
    x = normalize(x, peak_db)
    x = fade(x, 0.0, 0.005) if x.ndim == 1 else x
    data = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1 if x.ndim == 1 else 2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())


def write_ogg(path, x, peak_db=-1.0, quality=5):
    tmp = path + ".tmp.wav"
    write_wav(tmp, x, peak_db, do_trim=False)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", tmp, "-c:a", "libvorbis", "-q:a", str(quality), path], check=True)
    os.remove(tmp)


def load(path, mono=True):
    """decodifica cualquier formato con ffmpeg -> float32 a 44.1 kHz."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", path, "-f", "f32le", "-ac", "1" if mono else "2", "-ar", str(SR), "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    x = np.frombuffer(raw, dtype="<f4").astype(np.float64)
    return x if mono else x.reshape(-1, 2)


def loop_crossfade(x, length, xfade):
    """hace loop perfecto: la cola [length, length+xfade) se funde sobre el inicio."""
    n, f = secs(length), secs(xfade)
    out = x[:n].copy()
    w = np.linspace(0, 1, f)
    if x.ndim == 2:
        w = w[:, None]
    out[:f] = x[:f] * np.sqrt(w) + x[n:n + f] * np.sqrt(1 - w)
    return out
