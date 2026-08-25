#!/usr/bin/env python3
"""mep_render_audio — renderiza os MIDI do bootstrap em OGG (F5.3, ADR-0047).

Lê `<pack>/auto/audio/fingerprints.json` (e/ou `<pack>/audio/fingerprints.json`)
e, para cada faixa `bgm` com MIDI, escreve `<camada>/bgm/<id>.ogg`:

  1. com **fluidsynth** + um SoundFont (`--sf2`, ou $MEP_SF2, ou um GeneralUser/
     FluidR3 encontrado nos caminhos usuais) → render General MIDI;
  2. sem fluidsynth, um sintetizador interno em Python/numpy (pulso 25 %/50 %,
     triângulo, ruído) — timbre próximo do chip original, útil como
     placeholder e para provar o pipeline;
  3. a codificação OGG usa **ffmpeg** (libvorbis); sem ffmpeg fica o WAV ao lado
     e o host não toca (só OGG é suportado pelo OggMixer).

Nunca sobrescreve um OGG na camada humana (`audio/bgm/`); só escreve em
`auto/audio/bgm/` (ou em `audio/bgm/` quando o fingerprints.json está lá e
não existe camada auto — `--layer` força).

Uso: python3 scripts/mep_render_audio.py <pasta-do-pack> [--sf2 arquivo.sf2] [--layer auto|human] [--force]
"""
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import wave
from pathlib import Path

RATE = 44100
SF2_CANDIDATES = [
    "/opt/homebrew/share/soundfonts/default.sf2",
    "/usr/share/sounds/sf2/FluidR3_GM.sf2",
    "/usr/share/soundfonts/FluidR3_GM.sf2",
    "/usr/share/sounds/sf2/default-GM.sf2",
]


# ---------------------------------------------------------------- SMF parser
def read_varlen(data, pos):
    value = 0
    while True:
        b = data[pos]
        pos += 1
        value = (value << 7) | (b & 0x7F)
        if not b & 0x80:
            return value, pos


def parse_smf(path: Path):
    """Devolve (tpqn, tempo_us, eventos [(tick, kind, channel, note)])."""
    data = path.read_bytes()
    assert data[:4] == b"MThd", "não é SMF"
    hdr_len = struct.unpack(">I", data[4:8])[0]
    fmt, ntracks, division = struct.unpack(">HHH", data[8:14])
    pos = 8 + hdr_len
    tempo = 500000
    events = []
    for _ in range(ntracks):
        assert data[pos:pos + 4] == b"MTrk"
        length = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        pos += 8
        end = pos + length
        tick = 0
        status = 0
        while pos < end:
            delta, pos = read_varlen(data, pos)
            tick += delta
            b = data[pos]
            if b == 0xFF:
                meta = data[pos + 1]
                mlen, p2 = read_varlen(data, pos + 2)
                if meta == 0x51:
                    tempo = int.from_bytes(data[p2:p2 + 3], "big")
                pos = p2 + mlen
                continue
            if b in (0xF0, 0xF7):
                slen, p2 = read_varlen(data, pos + 1)
                pos = p2 + slen
                continue
            if b & 0x80:
                status = b
                pos += 1
            kind = status & 0xF0
            ch = status & 0x0F
            if kind in (0x80, 0x90, 0xA0, 0xB0, 0xE0):
                d1, d2 = data[pos], data[pos + 1]
                pos += 2
                if kind == 0x90 and d2 == 0:
                    kind = 0x80
                if kind in (0x80, 0x90):
                    events.append((tick, kind, ch, d1))
            elif kind in (0xC0, 0xD0):
                pos += 1
        pos = end
    events.sort(key=lambda e: e[0])
    return division, tempo, events


# ------------------------------------------------------- internal chip synth
def render_internal(midi: Path, wav: Path):
    import numpy as np

    tpqn, tempo, events = parse_smf(midi)
    sec_per_tick = tempo / 1_000_000 / tpqn
    total_ticks = events[-1][0] if events else 0
    total = int((total_ticks * sec_per_tick + 0.5) * RATE) + 1
    out = np.zeros(total, dtype=np.float32)
    active = {}  # (ch, note) -> start sample
    rng = np.random.default_rng(1234)

    def voice(ch, note, n):
        t = np.arange(n) / RATE
        if ch == 9:
            # drums: short noise burst, brighter for hi-hat
            decay = 0.06 if note == 42 else 0.15
            env = np.exp(-t / decay)
            return (rng.uniform(-1, 1, n) * env * 0.5).astype(np.float32)
        f = 440.0 * 2 ** ((note - 69) / 12)
        phase = (t * f) % 1.0
        if ch == 2:
            w = 4 * np.abs(phase - 0.5) - 1  # triangle
            amp = 0.28
        else:
            duty = 0.5 if ch == 0 else 0.25
            w = np.where(phase < duty, 1.0, -1.0)
            amp = 0.22
        env = np.minimum(1.0, t / 0.005) * np.exp(-t / 3.0)
        return (w * env * amp).astype(np.float32)

    for tick, kind, ch, note in events:
        s = int(tick * sec_per_tick * RATE)
        key = (ch, note)
        if kind == 0x90:
            if key in active:
                start = active.pop(key)
                seg = voice(ch, note, s - start)
                out[start:start + len(seg)] += seg
            active[key] = s
        elif key in active:
            start = active.pop(key)
            seg = voice(ch, note, max(1, s - start))
            out[start:start + len(seg)] += seg[: len(out) - start]
    for (ch, note), start in active.items():
        seg = voice(ch, note, max(1, total - start))
        out[start:start + len(seg)] += seg[: len(out) - start]

    peak = float(np.max(np.abs(out))) or 1.0
    pcm = (out / peak * 0.8 * 32767).astype("<i2")
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())


def render_fluidsynth(midi: Path, wav: Path, sf2: str) -> bool:
    cmd = ["fluidsynth", "-ni", "-g", "0.8", "-r", str(RATE), "-F", str(wav), sf2, str(midi)]
    return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0 and wav.exists()


def encode_ogg(wav: Path, ogg: Path) -> bool:
    if not shutil.which("ffmpeg"):
        return False
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-c:a", "libvorbis", "-q:a", "5", str(ogg)]
    return subprocess.run(cmd).returncode == 0 and ogg.exists()


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    pack = Path(argv[1])
    sf2 = os.environ.get("MEP_SF2")
    force = "--force" in argv
    layer_opt = None
    for i, a in enumerate(argv):
        if a == "--sf2" and i + 1 < len(argv):
            sf2 = argv[i + 1]
        if a == "--layer" and i + 1 < len(argv):
            layer_opt = argv[i + 1]
    if not sf2:
        sf2 = next((c for c in SF2_CANDIDATES if Path(c).exists()), None)
    use_fluid = bool(shutil.which("fluidsynth") and sf2)

    layers = []
    if layer_opt in (None, "auto") and (pack / "auto/audio/fingerprints.json").exists():
        layers.append(pack / "auto/audio")
    if layer_opt in (None, "human") and (pack / "audio/fingerprints.json").exists() and (layer_opt == "human" or not layers):
        layers.append(pack / "audio")
    if not layers:
        print("nenhum fingerprints.json encontrado em auto/audio/ ou audio/")
        return 1

    print(f"renderer: {'fluidsynth + ' + sf2 if use_fluid else 'sintetizador interno (instale fluidsynth + um SoundFont para General MIDI)'}")
    if not shutil.which("ffmpeg"):
        print("aviso: ffmpeg não encontrado — só WAV será gerado (o emulador toca apenas OGG)")

    done = skipped = failed = 0
    for layer in layers:
        tracks = json.loads((layer / "fingerprints.json").read_text()).get("tracks", [])
        (layer / "bgm").mkdir(parents=True, exist_ok=True)
        for t in tracks:
            if t.get("kind") != "bgm" or not t.get("midi"):
                continue
            midi = layer / t["midi"]
            ogg = layer / "bgm" / f"{t['id']}.ogg"
            human_ogg = pack / "audio/bgm" / f"{t['id']}.ogg"
            if not midi.exists():
                print(f"  {t['id']}: MIDI ausente ({midi})")
                failed += 1
                continue
            if ogg.exists() and not force:
                skipped += 1
                continue
            wav = ogg.with_suffix(".wav")
            ok = render_fluidsynth(midi, wav, sf2) if use_fluid else False
            if not ok:
                try:
                    render_internal(midi, wav)
                    ok = True
                except Exception as exc:  # noqa: BLE001
                    print(f"  {t['id']}: falha no render interno: {exc}")
            if ok and encode_ogg(wav, ogg):
                wav.unlink(missing_ok=True)
                note = " (a camada humana tem o próprio OGG — prevalece)" if human_ogg.exists() and layer.name == "audio" and layer.parent.name == "auto" else ""
                print(f"  {t['id']}: {ogg.relative_to(pack)} ({t.get('frames', 0) / 60:.1f} s){note}")
                done += 1
            elif ok:
                print(f"  {t['id']}: {wav.relative_to(pack)} (sem ffmpeg — não codificado)")
                failed += 1
            else:
                failed += 1
    print(f"{done} renderizada(s), {skipped} já existiam, {failed} falha(s)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
