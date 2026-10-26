"""
theme_audit.py - dev-only pixel-level readability audit.

Instead of trusting what the code SAYS its colors are, this measures what is
actually on screen: every text label that gets drawn is recorded together with
the real pixels behind it at the moment it was drawn, and the contrast between
the text color and that background is computed (WCAG ratio).

How it works
  - pygame.font.SysFont is patched so every font a screen creates is wrapped;
    its render() returns a tagged Surface that remembers the text + color.
  - The screen handed to draw() is an AuditScreen (a Surface subclass) whose
    blit() looks at what it is about to cover, then records the pair.
  - Unlabelled icon-like blits (pictures with transparency) are measured the
    same way: their dominant opaque color against the pixels behind them.

Use:  from theme_audit import Audit
      with Audit() as audit:            # patches SysFont for the duration
          obj = SomeScreen(...)         # create AFTER entering, so its fonts are wrapped
          surf = audit.screen()
          obj.draw(surf)
      audit.findings(min_text=4.5, min_graphic=3.0)
"""
import collections

import pygame

from theme import contrast_ratio


class TaggedSurface(pygame.Surface):
    """A rendered label that remembers what it says and what color it is."""
    audit_text = ""
    audit_color = (0, 0, 0)


class AuditFont:
    """Wraps a pygame Font; render() returns a TaggedSurface."""

    def __init__(self, font):
        self._f = font

    def render(self, text, antialias, color, *args):
        base = self._f.render(text, antialias, color, *args)
        tagged = TaggedSurface(base.get_size(), pygame.SRCALPHA)
        tagged.blit(base, (0, 0))
        tagged.audit_text = str(text)
        tagged.audit_color = tuple(color[:3])
        return tagged

    def __getattr__(self, name):
        return getattr(self._f, name)


def _dominant(pixels):
    """Most common EXACT (r, g, b) in a list of pixels. Flat backgrounds and
    flat icon bodies dominate their area, so the exact mode is the real color
    (bucketing colors would shift a ratio sitting right at 4.5 and report
    false failures)."""
    counts = collections.Counter(pixels)
    return counts.most_common(1)[0][0] if counts else None


class AuditScreen(pygame.Surface):
    """A Surface that records, for every labelled blit, the text color and
    the actual background right underneath it."""

    def __init__(self, size, log, where):
        super().__init__(size, pygame.SRCALPHA)
        self._log = log
        self._where = where

    def _target_rect(self, source, dest):
        if isinstance(dest, pygame.Rect):
            return pygame.Rect(dest.topleft, source.get_size())
        return pygame.Rect(int(dest[0]), int(dest[1]), *source.get_size())

    def _background_under(self, rect):
        rect = rect.clip(self.get_rect())
        if rect.w < 1 or rect.h < 1:
            return None
        pixels = []
        step_x = max(1, rect.w // 14)
        step_y = max(1, rect.h // 5)
        for x in range(rect.left, rect.right, step_x):
            for y in range(rect.top, rect.bottom, step_y):
                pixels.append(tuple(self.get_at((x, y)))[:3])
        return _dominant(pixels)

    def blit(self, source, dest=(0, 0), area=None, special_flags=0):
        try:
            rect = self._target_rect(source, dest)
            if isinstance(source, TaggedSurface):
                if source.audit_text.strip():
                    bg = self._background_under(rect)
                    if bg is not None:
                        self._log.append(("text", self._where, source.audit_text,
                                          source.audit_color, bg, rect))
            elif (source.get_flags() & pygame.SRCALPHA and source.get_width() * source.get_height() >= 600
                  and source.get_width() * source.get_height() < 0.25 * self.get_width() * self.get_height()):
                # (full-screen dimming overlays are not icons - skipped)
                opaque = []
                step_x = max(1, source.get_width() // 24)
                step_y = max(1, source.get_height() // 24)
                for x in range(0, source.get_width(), step_x):
                    for y in range(0, source.get_height(), step_y):
                        r, g, b, a = source.get_at((x, y))
                        if a > 200:
                            opaque.append((r, g, b))
                color = _dominant(opaque)
                bg = self._background_under(rect)
                if color is not None and bg is not None and len(opaque) > 8:
                    self._log.append(("graphic", self._where, f"icon {source.get_size()}",
                                      color, bg, rect))
        except Exception:      # an audit problem must never break the drawing itself
            pass
        return super().blit(source, dest, area, special_flags)


class Audit:
    """Context manager: patches SysFont, hands out AuditScreens, collects records."""

    def __init__(self, size=(1280, 720)):
        self.size = size
        self.log = []
        self._real = None

    def __enter__(self):
        self._real = pygame.font.SysFont
        pygame.font.SysFont = lambda *a, **k: AuditFont(self._real(*a, **k))
        return self

    def __exit__(self, *exc):
        pygame.font.SysFont = self._real

    def screen(self, where="?"):
        return AuditScreen(self.size, self.log, where)

    def rect_of(self, text):
        """Where the label `text` was drawn (the last time), or None."""
        found = [rect for kind, _w, what, _fg, _bg, rect in self.log
                 if kind == "text" and what == text]
        return found[-1] if found else None

    def findings(self, min_text=4.5, min_graphic=3.0):
        """Records below the thresholds: [(kind, where, what, fg, bg, ratio)]."""
        bad = []
        for kind, where, what, fg, bg, _rect in self.log:
            ratio = contrast_ratio(fg, bg)
            if ratio < (min_text if kind == "text" else min_graphic):
                bad.append((kind, where, what, fg, bg, round(ratio, 2)))
        return bad
