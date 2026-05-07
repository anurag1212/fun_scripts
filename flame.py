#!/usr/bin/env python3
"""Render a classic demo-scene fire effect in the terminal."""

from __future__ import annotations

import math
import random
import shutil
import signal
import sys
import time

try:
    import numpy as np
    import sounddevice as sd
except ImportError:
    np = None
    sd = None


FRAME_DELAY = 0.01
MAX_HEAT = 255
CHARS = " ▁▂▃▄▅▆▇█"
GRADIENT = [
    (1, 0, 0),
    (2, 0, 0),
    (3, 0, 0),
    (4, 0, 0),
    (5, 0, 0),
    (5, 1, 0),
    (5, 2, 0),
    (5, 3, 0),
    (5, 4, 0),
    (5, 5, 0),
    (5, 5, 1),
    (5, 5, 2),
    (5, 5, 3),
    (5, 5, 4),
    (5, 5, 5),
]
PERMUTATION = list(range(256))
random.shuffle(PERMUTATION)
PERMUTATION *= 2


class MicLevel:
    def __init__(self) -> None:
        self.level = 0.0
        self.peak = 0.0
        self.stream = None

    def _callback(self, indata, _frames, _time_info, _status) -> None:
        rms = float(np.sqrt(np.mean(np.square(indata))))
        boosted = min(1.0, rms * 20.0)
        self.peak = max(self.peak * 0.9, boosted)

    def start(self) -> None:
        if sd is None or np is None:
            return

        try:
            self.stream = sd.InputStream(channels=1, callback=self._callback, blocksize=1024)
            self.stream.start()
        except Exception:
            self.stream = None

    def sample(self) -> float:
        self.level = (self.level * 0.68) + (self.peak * 0.32)
        self.peak *= 0.84
        return self.level

    def close(self) -> None:
        if self.stream is None:
            return
        try:
            self.stream.stop()
            self.stream.close()
        except Exception:
            pass
        self.stream = None


def ansi_cube_index(rgb: tuple[int, int, int]) -> int:
    r, g, b = rgb
    return 16 + (36 * r) + (6 * g) + b


COLOR_STEPS = [ansi_cube_index(rgb) for rgb in GRADIENT]


def build_buffer(width: int, height: int) -> list[list[int]]:
    return [[0 for _ in range(width)] for _ in range(height)]


def fade(value: float) -> float:
    return value * value * value * (value * (value * 6 - 15) + 10)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def grad2(hash_value: int, x: float, y: float) -> float:
    gradients = (
        (1.0, 1.0),
        (-1.0, 1.0),
        (1.0, -1.0),
        (-1.0, -1.0),
        (1.0, 0.0),
        (-1.0, 0.0),
        (0.0, 1.0),
        (0.0, -1.0),
    )
    gx, gy = gradients[hash_value & 7]
    return (gx * x) + (gy * y)


def perlin_2d(x: float, y: float) -> float:
    xi = math.floor(x) & 255
    yi = math.floor(y) & 255
    xf = x - math.floor(x)
    yf = y - math.floor(y)
    u = fade(xf)
    v = fade(yf)

    aa = PERMUTATION[PERMUTATION[xi] + yi]
    ab = PERMUTATION[PERMUTATION[xi] + yi + 1]
    ba = PERMUTATION[PERMUTATION[xi + 1] + yi]
    bb = PERMUTATION[PERMUTATION[xi + 1] + yi + 1]

    x1 = lerp(grad2(aa, xf, yf), grad2(ba, xf - 1.0, yf), u)
    x2 = lerp(grad2(ab, xf, yf - 1.0), grad2(bb, xf - 1.0, yf - 1.0), u)
    return lerp(x1, x2, v)


def turbulence(nx: float, ny: float, t: float) -> float:
    angle_a = t * 0.37
    angle_b = -t * 0.29
    angle_c = t * 0.53

    layer_a = perlin_2d(
        nx * 4.5 + math.cos(angle_a) * 1.7,
        ny * 4.5 + math.sin(angle_a) * 1.7,
    )
    layer_b = perlin_2d(
        nx * 9.0 + math.cos(angle_b) * 2.3,
        ny * 9.0 + math.sin(angle_b) * 2.3,
    )
    layer_c = perlin_2d(
        (nx - ny) * 7.0 + math.cos(angle_c) * 1.5,
        (nx + ny) * 7.0 + math.sin(angle_c) * 1.5,
    )
    return (layer_a * 0.5) + (layer_b * 0.3) + (layer_c * 0.2)


def audio_response(mic_level: float) -> float:
    return min(1.0, pow(max(0.0, mic_level), 0.82) * 0.98)


def noise_heat(x: int, t: float, width: int, mic_level: float) -> int:
    mic_response = audio_response(mic_level)
    nx = x / max(1, width)
    combined = turbulence(nx, 0.0, t)
    normalized = (combined + 1.0) * 0.5
    flicker = random.randint(-20, 20) + int(mic_response * 28)
    mic_heat = int(mic_response * 70)
    return max(0, min(MAX_HEAT, int(95 + normalized * 160) + mic_heat + flicker))


def flame_fill_fraction(t: float, mic_level: float) -> float:
    mic_response = audio_response(mic_level)
    low = perlin_2d(3.7, t * 0.12)
    medium = perlin_2d(-8.1, t * 0.27)
    envelope = (low * 0.7) + (medium * 0.3)
    return max(0.68, min(0.99, 0.8 + (envelope * 0.12) + (mic_response * 0.18)))


def seed_bottom_row(
    buffer: list[list[int]], width: int, height: int, t: float, mic_level: float
) -> None:
    mic_response = audio_response(mic_level)
    bottom = buffer[height - 1]
    seeded = [0 for _ in range(width)]

    for x in range(width):
        base = noise_heat(x, t, width, mic_level)
        crest = turbulence((x / max(1, width)) * 6.0 + 21.0, 1.3, t * 1.7)
        if crest > (0.52 - mic_response * 0.08):
            base += int(18 + crest * 20)
        seeded[x] = max(0, min(MAX_HEAT, base))

    smoothed = [0 for _ in range(width)]
    for x in range(width):
        left2 = seeded[(x - 2) % width]
        left = seeded[(x - 1) % width]
        center = seeded[x]
        right = seeded[(x + 1) % width]
        right2 = seeded[(x + 2) % width]
        previous = bottom[x]
        smoothed_heat = (
            left2
            + (left * 2)
            + (center * 4)
            + (right * 2)
            + right2
            + (previous * 3)
        ) // 13
        smoothed[x] = max(0, min(MAX_HEAT, smoothed_heat))

    bottom[:] = smoothed


def update_fire(buffer: list[list[int]], width: int, height: int, t: float, mic_level: float) -> None:
    mic_response = audio_response(mic_level)
    seed_bottom_row(buffer, width, height, t, mic_level)
    active_height = max(1, int(height * flame_fill_fraction(t, mic_level)))
    active_start = max(0, height - active_height)

    for y in range(height - 1):
        if y < active_start:
            buffer[y] = [0 for _ in range(width)]
            continue

        source_row = buffer[y + 1]
        row = buffer[y]
        ny = y / max(1, height)
        ascent = 1.0 - ((y - active_start) / max(1, active_height - 1))
        loft = ascent**0.72
        for x in range(width):
            left2 = source_row[(x - 2) % width]
            left = source_row[(x - 1) % width]
            center = source_row[x]
            right = source_row[(x + 1) % width]
            right2 = source_row[(x + 2) % width]
            far = buffer[min(height - 1, y + 2)][x] if y + 2 < height else center
            swirl = turbulence((x / max(1, width)) * 1.4 + 2.0, ny * 1.5 + 1.0, t * 0.9)
            lean = -1 if swirl < -0.2 else 1 if swirl > 0.2 else 0
            tongue = source_row[(x + lean) % width]
            heat = (
                (center * 5)
                + (tongue * 4)
                + left
                + right
                + (left2 // 2)
                + (right2 // 2)
                + far
            ) // 13
            drift = turbulence(x / max(1, width), ny, t)
            heat -= 4 + int(((drift + 1.0) * 0.5) * (9 - (mic_response * 2)))
            heat += int(8 + loft * 14 + mic_response * 18)

            # Carve thin channels and wispy gaps through the flame body.
            filament = turbulence((x / max(1, width)) * 4.8 + 13.0, ny * 5.2 + 7.0, t * 1.55)
            streak = turbulence((x / max(1, width)) * 7.5 + 19.0, ny * 2.8 + 11.0, t * 1.9)
            if filament < (-0.08 + ascent * 0.18):
                heat -= int(16 + (abs(filament) * 34))
            if streak < (-0.18 + ascent * 0.1):
                heat -= int(10 + abs(streak) * 22)
            if filament > (0.5 - ascent * 0.08):
                heat += int(3 + filament * 8)

            # Make the top of the flame fragment and thin out faster.
            edge_decay = int((ascent**1.95) * 10)
            retention = 1.0 - ((ascent**2.4) * 0.14)
            erosion = turbulence((x / max(1, width)) * 1.2 + 9.0, ny * 1.8 + 4.0, t * 1.1)
            if ascent > 0.72 and erosion < (-0.14 - ascent * 0.06):
                heat -= int(5 + ascent * 10)
            heat = int(max(0, heat - edge_decay) * max(0.7, retention))
            if ascent > 0.35 and random.random() < (0.015 + ascent * 0.05):
                heat = int(heat * (0.55 + random.random() * 0.2))
            if heat < 0:
                heat = 0
            row[x] = heat


def heat_to_style(heat: int) -> tuple[str, int]:
    if heat <= 0:
        return " ", COLOR_STEPS[0]

    char_index = min(len(CHARS) - 1, heat * len(CHARS) // (MAX_HEAT + 1))
    color_index = min(len(COLOR_STEPS) - 1, heat * len(COLOR_STEPS) // (MAX_HEAT + 1))
    return CHARS[char_index], COLOR_STEPS[color_index]


def render(buffer: list[list[int]], width: int, height: int) -> str:
    lines: list[str] = ["\x1b[H"]
    current_color: int | None = None

    for y in range(height):
        fragments: list[str] = []
        for x in range(width):
            char, color = heat_to_style(buffer[y][x])
            if color != current_color:
                fragments.append(f"\x1b[38;5;{color}m")
                current_color = color
            fragments.append(char)
        fragments.append("\x1b[0m")
        current_color = None
        lines.append("".join(fragments))

    return "\n".join(lines)


def cleanup() -> None:
    sys.stdout.write("\x1b[0m\x1b[?25h")
    sys.stdout.flush()


def main() -> int:
    running = True

    def handle_signal(_signum: int, _frame: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, handle_signal)

    sys.stdout.write("\x1b[2J\x1b[H\x1b[?25l")
    sys.stdout.flush()

    try:
        buffer: list[list[int]] = []
        current_size = (0, 0)
        start_time = time.monotonic()
        mic = MicLevel()
        mic.start()

        while running:
            size = shutil.get_terminal_size(fallback=(80, 24))
            width = max(1, size.columns)
            height = max(2, size.lines - 1)
            t = time.monotonic() - start_time
            mic_level = mic.sample()
            motion_t = t * (1.0 + (audio_response(mic_level) * 2.6))

            if (width, height) != current_size:
                buffer = build_buffer(width, height)
                current_size = (width, height)
                sys.stdout.write("\x1b[2J")

            update_fire(buffer, width, height, motion_t, mic_level)
            sys.stdout.write(render(buffer, width, height))
            sys.stdout.flush()
            time.sleep(FRAME_DELAY)
    finally:
        mic.close()
        cleanup()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
