#!/usr/bin/env python3
import sys
import time
import random
import shutil
import os
import math

class PerlinNoise:
    def __init__(self, seed=None):
        if seed is not None:
            random.seed(seed)
        self.p = list(range(256))
        random.shuffle(self.p)
        self.p += self.p

    def _fade(self, t):
        return t * t * t * (t * (t * 6 - 15) + 10)

    def _lerp(self, t, a, b):
        return a + t * (b - a)

    def _grad(self, hash, x, y):
        h = hash & 15
        u = x if h < 8 else y
        v = y if h < 4 else (x if h == 12 or h == 14 else 0)
        return (u if (h & 1) == 0 else -u) + (v if (h & 2) == 0 else -v)

    def noise(self, x, y):
        X = int(math.floor(x)) & 255
        Y = int(math.floor(y)) & 255
        x -= math.floor(x)
        y -= math.floor(y)
        u = self._fade(x)
        v = self._fade(y)
        p = self.p
        A = p[X] + Y
        B = p[X+1] + Y
        return self._lerp(v, self._lerp(u, self._grad(p[A], x, y),
                                          self._grad(p[B], x-1, y)),
                             self._lerp(u, self._grad(p[A+1], x, y-1),
                                          self._grad(p[B+1], x-1, y-1)))

def get_fbm_noise(noise_gen, x, y, t, octaves=3):
    val = 0
    amp = 1
    freq = 1
    for _ in range(octaves):
        val += noise_gen.noise(x * freq, y * freq + t) * amp
        amp *= 0.5
        freq *= 2
    return val

def get_truecolor_rgb(heat):
    """
    Returns (r, g, b) for a high-fidelity fire gradient using Truecolor.
    Gradient: Dark Red -> Orange-Red -> Bright Orange -> Yellow -> White Hot.
    """
    h = max(0.0, min(1.0, heat))
    
    if h < 0.15: # Very dim/dark red
        return (40, 0, 0)
    elif h < 0.4: # Deep orange-red
        return (220, 40, 0)
    elif h < 0.7: # Bright orange
        return (255, 140, 0)
    elif h < 0.9: # Yellow-orange
        return (255, 230, 50)
    else:         # White hot
        return (255, 255, 220)

_color_cache = {}
def get_cached_rgb(heat):
    h = round(max(0.0, min(1.0, heat)), 3) # Higher precision for smoother gradients
    if h not in _color_cache:
        _color_cache[h] = get_truecolor_rgb(h)
    return _color_cache[h]

def main():
    # Hide cursor to make the effect cleaner
    sys.stdout.write("\x1b[?25l")
    sys.stdout.flush()

    noise_gen = PerlinNoise(seed=42)
    grid = []
    cols, rows_term = 0, 0
    frame_count = 0

    try:
        while True:
            # Detect terminal size automatically
            curr_cols, curr_rows_term = shutil.get_terminal_size()
            
            if curr_cols != cols or curr_rows_term != rows_term:
                cols, rows_term = curr_cols, curr_rows_term
                # We use half-blocks (▀) to double the vertical resolution.
                # So simulation grid has 2x rows.
                rows_sim = rows_term * 2
                grid = [[0.0 for _ in range(cols)] for _ in range(rows_sim)]

            frame_count += 1
            t = frame_count * 0.04 # Time evolution parameter

            # 1. Bottom row gets random heat (the "fuel")
            for x in range(cols):
                grid[rows_sim-1][x] = random.random()

            # 2. Propagate upwards using cellular automata with noise influence
            for y in range(rows_sim - 2, -1, -1):
                for x in range(cols):
                    # Coordinates adjusted for simulation grid (which is 2x height)
                    nx = (x / cols * 4.0) * 2.5 
                    ny = (y / rows_sim * 4.0)
                    
                    n = get_fbm_noise(noise_gen, nx, ny, t)

                    # Turbulence: noise influences horizontal drift
                    drift_strength = 1.8
                    vx = n * drift_strength
                    nx_idx = (x + int(math.floor(vx))) % cols
                    
                    # Heat diffusion/decay influenced by noise
                    decay_base = 0.94
                    n_mod = (n + 1.0) / 2.0
                    decay = decay_base + (n_mod * 0.04) # range ~[0.94, 0.98]
                    
                    v_left  = grid[y+1][(x - 1) % cols]
                    v_mid   = grid[y+1][nx_idx]
                    v_right = grid[y+1][(x + 1) % cols]
                    
                    # Weighting for smooth upward flow
                    grid[y][x] = (v_left * 0.25 + v_mid * 0.5 + v_right * 0.25) * decay

            # 3. Build the frame buffer using half-block technique
            # One character position represents two vertical pixels: 
            # foreground color = top pixel, background color = bottom pixel.
            frame_buffer = []
            for ty in range(rows_term):
                line_chars = []
                y_sim_top = ty * 2
                y_sim_bot = y_sim_top + 1
                
                for x in range(cols):
                    h_top = grid[y_sim_top][x]
                    h_bot = grid[y_sim_bot][x]
                    
                    if h_top > 0.01 or h_bot > 0.01:
                        r1, g1, b1 = get_cached_rgb(h_top)
                        r2, g2, b2 = get_cached_rgb(h_bot)
                        # \x1b[38;2;R;G;Bm is foreground (top), \x1b[48;2;R;G;Bm is background (bottom)
                        line_chars.append(f"\x1b[38;2;{r1};{g1};{b1}m\x1b[48;2;{r2};{g2};{b2}m▀")
                    else:
                        # If no heat, just print a black space
                        line_chars.append("\x1b[0m ")
                frame_buffer.append("".join(line_chars))
            
            # Output the whole frame at once
            sys.stdout.write("\x1b[H" + "\n".join(frame_buffer) + "\x1b[0m")
            sys.stdout.flush()

            time.sleep(0.05)

    except KeyboardInterrupt:
        sys.stdout.write("\x1b[?25h\x1b[0m\n")
        sys.stdout.flush()
        print("Fire extinguished.")
    except Exception as e:
        sys.stdout.write("\x1b[?25h\x1b[0m\n")
        sys.stdout.flush()
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
