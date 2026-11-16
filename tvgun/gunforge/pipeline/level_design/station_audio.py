"""Original procedural audio for the night-market playtest candidate."""
import hashlib
import math
import struct
import tempfile
import wave
from pathlib import Path

from compiler import ROOT


RATE = 22050
BEAT = 0.625


def light_shot():
    """A short warm body with a filtered paper snap."""
    noise_state = 51091
    low = 0.0
    snap = 0.0
    for i in range(int(RATE * 0.15)):
        time = i / RATE
        noise_state = (1664525 * noise_state + 1013904223) & 0xffffffff
        low += 0.14 * (noise_state / 2147483648 - 1 - low)
        snap += 0.04 * (low - snap)
        fundamental = math.sin(math.tau * (216 * time - 435 * time * time))
        overtone = math.sin(math.tau * (410 * time - 680 * time * time))
        body = (0.68 * fundamental + 0.18 * overtone) * math.exp(-time * 46)
        paper = 0.72 * (low - snap) * math.exp(-time * 120)
        tail = 0.11 * math.sin(math.tau * 555 * time) * math.exp(-time * 28)
        yield (body + paper + tail) * min(1.0, time / 0.002)


def night_market():
    """Eight bars of plucked notes, bass and a quiet wooden pulse at 96 BPM."""
    size = round(RATE * BEAT * 32)
    samples = [0.0] * size

    def note(beat, midi, duration, gain, decay, overtones):
        start = round(beat * BEAT * RATE)
        count = round(duration * BEAT * RATE)
        omega = math.tau * 440 * 2 ** ((midi - 69) / 12) / RATE
        for index in range(count):
            seconds = index / RATE
            phase = index * omega
            envelope = min(1.0, seconds / 0.012, (count - index) / (0.06 * RATE))
            tone = math.sin(phase) + sum(weight * math.sin(phase * partial) for partial, weight in overtones)
            samples[(start + index) % size] += gain * envelope * tone * math.exp(-seconds * decay)

    roots = (50, 50, 46, 48, 50, 53, 46, 48)
    phrases = (
        (69, 72, 74, 77), (76, 74, 69, 72),
        (65, 69, 72, 74), (72, 69, 67, 69),
        (69, 72, 77, 74), (81, 77, 76, 72),
        (74, 72, 69, 65), (67, 72, 69, 67),
    )
    for bar, root in enumerate(roots):
        start = 4 * bar
        note(start, root - 12, 3.7, 0.16, 1.8, ((2, 0.17),))
        note(start + 2, root - 5, 1.6, 0.08, 3.0, ((2, 0.1),))
        for beat, pitch in zip((0.5, 1.5, 2.25, 3.25), phrases[bar]):
            note(start + beat, pitch, 0.85, 0.11, 6.5, ((2, 0.25), (3.01, 0.13)))
        for beat in (0, 1.75, 2.5, 3.5):
            note(start + beat, 43, 0.24, 0.055, 31.0, ((2.8, 0.47), (5.1, 0.19)))
    return samples


def ensure_station_audio():
    assets = {}
    directory = ROOT / "gunforge/level_design/generated/audio"
    directory.mkdir(parents=True, exist_ok=True)
    for name, samples, peak in (
        ("light_shot", list(light_shot()), 0.58),
        ("night_market", night_market(), 0.66),
    ):
        gain = peak / max(abs(sample) for sample in samples)
        pcm = b"".join(struct.pack("<h", int(sample * gain * 32767)) for sample in samples)
        path = directory / f"station_{name}.wav"
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as file:
            pending = Path(file.name)
        try:
            with wave.open(str(pending), "wb") as stream:
                stream.setparams((1, 2, RATE, len(samples), "NONE", "not compressed"))
                stream.writeframes(pcm)
            checksum = hashlib.sha256(pending.read_bytes()).hexdigest()
            pending.replace(path)
        finally:
            pending.unlink(missing_ok=True)
        assets[name] = {
            "resource": {
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": checksum,
                "kind": "audio",
            },
            "duration_ms": round(1000 * len(samples) / RATE),
        }
    return assets
