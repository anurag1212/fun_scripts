#!/usr/bin/env python3
"""Classic 90s demo-scene fire effect using cellular automata.

Heat propagates upwards with horizontal + vertical decay,
mapped to the 6×6×6 ANSI color cube with intensity-differentiated
block characters.

Uses the alternate screen buffer so it never fills scrollback.
Ctrl+C exits cleanly.
"""

import os
import sys
import time
import random

# ── ANSI 6×6×6 cube helpers ──────────────────────────────────────────────────

CUBE_LEVELS = [0, 95, 135, 175, 215, 255]


def cube_index(value: int) -> int:
    value = max(0, min(255, value))
    best, best_dist = 0, abs(CUBE_LEVELS[0] - value)
    for i in range(1, 6):
        d = abs(CUBE_LEVELS[i] - value)
        if d < best_dist:
            best_dist, best = d, i
    return best


def rgb_to_ansi256(r: int, g: int, b: int) -> int:
    ri, gi, bi = cube_index(r), cube_index(g), cube_index(b)
    return 16 + 36 * ri + 6 * gi + bi


# ── Fire gradient palette ────────────────────────────────────────────────────

def build_fire_palette(num_colors: int = 32) -> list[int]:
    palette = []
    for i in range(num_colors):
        t = i / (num_colors - 1)
        if t < 0.15:
            r = int(10 + t / 0.15 * 30)
            g = int(t / 0.15 * 5)
            b = int(t / 0.15 * 2)
        elif t < 0.35:
            s = (t - 0.15) / 0.20
            r, g, b = int(40 + s * 215), int(5 + s * 10), int(2 + s * 2)
        elif t < 0.55:
            s = (t - 0.35) / 0.20
            r, g, b = 255, int(15 + s * 100), 4
        elif t < 0.75:
            s = (t - 0.55) / 0.20
            r, g, b = int(255 - s * 20), int(115 + s * 140), int(4 + s * 10)
        else:
            s = (t - 0.75) / 0.25
            r, g, b = int(235 + s * 20), int(255 - s * 20), int(14 + s * 241)
        palette.append(rgb_to_ansi256(r, g, b))
    return palette


# ── Intensity characters (coolest → hottest) ─────────────────────────────────

CHARS = list(" .:;iIllooooxXXxX#@@")


# ── Cellular automata fire ───────────────────────────────────────────────────

class FireGrid:
    def __init__(self, width: int, height: int):
        self.w = width
        self.h = height
        self.grid = [[0] * width for _ in range(height)]

    def step(self):
        new_grid = [[0] * self.w for _ in range(self.h)]
        for y in range(self.h - 2, -1, -1):
            for x in range(self.w):
                below = self.grid[y + 1][x]
                left = self.grid[y + 1][x - 1] if x > 0 else below
                right = self.grid[y + 1][x + 1] if x < self.w - 1 else below
                new_grid[y][x] = max(0, (below + left + right) // 3 - random.randint(1, 4))
        for y in range(self.h - 1):
            for x in range(self.w):
                self.grid[y][x] = new_grid[y][x]
        # Feed bottom row with random heat
        for x in range(self.w):
            self.grid[self.h - 1][x] = random.randint(180, 255)
            if random.random() < 0.15:
                self.grid[self.h - 1 - random.randint(0, 2)][x] = random.randint(200, 255)


# ── Render ────────────────────────────────────────────────────────────────────

def render(grid: FireGrid, palette: list[int]) -> bytes:
    parts: list[bytes] = []
    for y in range(grid.h):
        for x in range(grid.w):
            heat = grid.grid[y][x]
            pi = min(len(palette) - 1, int(heat / 255 * (len(palette) - 0.5)))
            ci = min(len(CHARS) - 1, int(heat / 255 * (len(CHARS) - 0.5)))
            parts.append(f"\033[38;5;{palette[pi]}m{CHARS[ci]}".encode())
        parts.append(b"\033[0m\n")
    return b"".join(parts)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    try:
        rows, cols = os.get_terminal_size()
    except OSError:
        rows, cols = 24, 80  # fallback for non-terminal
    w, h = cols, rows  # full terminal size, no margin

    grid = FireGrid(w, h)
    palette = build_fire_palette(32)

    # Enter alternate screen buffer (no scrollback accumulation)
    sys.stdout.buffer.write(b"\033[?1049h\033[2J\033[H\033[?25l")
    sys.stdout.buffer.flush()

    try:
        while True:
            grid.step()
            frame = render(grid, palette)
            # Go to home position and overwrite — NO screen clear, no flicker
            sys.stdout.buffer.write(b"\033[H")
            sys.stdout.buffer.write(frame)
            sys.stdout.buffer.flush()
            time.sleep(0.100)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.buffer.write(b"\033[?25h\033[0m\033[?1049l")
        sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
