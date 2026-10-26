"""
sounds.py

Loads the three sound effects extracted directly from the original SWF
(goed = correct, fout = wrong, klik = button click) and plays them on
request.

Loaded as WAV, not MP3: the original audio was decoded once (via
pygame itself) and re-saved as WAV, specifically because pygame's
bundled MP3 decoder has been unreliable on some Windows setups -
loading without error but producing no audible output. WAV has no such
decoder ambiguity, so this sidesteps the problem entirely. The original
MP3s are kept alongside for reference but are no longer loaded here.

Deliberately defensive: some Batocera setups / dev machines won't have a
working audio device (or you might run this over SSH with no sound card
at all). Rather than crash the whole game over a missing beep, every
method here fails silently if audio isn't available.
"""

import os
import paths
import pygame

# Ships with the game, read-only (see paths.py: differs from the data folder once packaged).
ASSET_DIR = paths.resource_path("assets", "sounds")


class SoundBank:
    def __init__(self):
        self.enabled = True          # overall on/off, e.g. from Keuzescherm
        self._sounds = {}
        self._audio_ok = False
        try:
            pygame.mixer.init()
            self._audio_ok = True
        except pygame.error as e:
            print(f"[sounds] No audio device available ({e}); "
                  f"running silently.")
            return

        for name in ("goed", "fout", "klik"):
            path = os.path.join(ASSET_DIR, f"{name}.wav")
            try:
                self._sounds[name] = pygame.mixer.Sound(path)
            except (pygame.error, FileNotFoundError) as e:
                print(f"[sounds] Could not load {path}: {e}")

    def play(self, name):
        if not self.enabled or not self._audio_ok:
            return
        sound = self._sounds.get(name)
        if sound is not None:
            sound.play()

    def play_correct(self):
        self.play("goed")

    def play_wrong(self):
        self.play("fout")

    def play_click(self):
        self.play("klik")

