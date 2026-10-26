"""
icons.py

Every picture in the game, drawn in code instead of loaded from image
files. The old pictures were extracted from the original Flash movie and
looked dated (hard, blocky edges and muddy fixed colors). Drawing them
fresh gives:

  - clean, smooth edges: each icon is drawn at 3x size and scaled down,
    which anti-aliases it using nothing but pygame's own drawing calls;
  - theme support for free: the CALLER passes the colors, so the same
    icon can follow dark / light / regenboog, and the caller can pick a
    color with guaranteed contrast against whatever it's drawn on;
  - no image files to ship, lose, or mis-place on the Batocera box.

Icons are cached by (size, colors), so drawing one every frame is cheap.
"""

import math
import pygame

_SUPERSAMPLE = 3
_CACHE_LIMIT = 600      # regenboog keeps inventing colors; don't grow forever
_cache = {}

# Where the number should sit on a balloon: the middle of the round body,
# not the middle of the whole picture (which includes the knot and string).
BALLOON_BODY_CENTER_FRAC = 0.40


def _render(key, size, draw):
    surf = _cache.get(key)
    if surf is not None:
        return surf
    if len(_cache) >= _CACHE_LIMIT:
        _cache.clear()
    w, h = size
    big = pygame.Surface((w * _SUPERSAMPLE, h * _SUPERSAMPLE), pygame.SRCALPHA)
    draw(big)
    # smoothscale rounds fully-opaque pixels to ~253/255 opacity and colors
    # to within 2/255 - invisible, but don't compare icon pixels exactly.
    surf = pygame.transform.smoothscale(big, (w, h))
    _cache[key] = surf
    return surf


def _rect(x, y, w, h):
    return pygame.Rect(int(x), int(y), max(1, int(w)), max(1, int(h)))


def _shade(color, factor):
    return tuple(max(0, min(255, int(c * factor))) for c in color[:3])


def _mix(color, other, t):
    return tuple(int(c + (o - c) * t) for c, o in zip(color[:3], other[:3]))


def balloon(size, color):
    """A balloon: round body with highlight, knot, and a wavy string.
    The caller draws the number at BALLOON_BODY_CENTER_FRAC down."""
    color = tuple(color[:3])

    def draw(s):
        w, h = s.get_size()
        k = _SUPERSAMPLE
        cx = w / 2
        body_h = int(h * 0.80)

        # String (behind everything), a neutral grey that shows on both
        # dark and light backgrounds.
        top = body_h + 0.05 * h
        pts = []
        for i in range(13):
            f = i / 12
            pts.append((cx + math.sin(f * math.pi * 2.2) * 0.07 * w,
                        top + (h - 2 * k - top) * f))
        pygame.draw.lines(s, (140, 140, 150), False, pts, max(2, int(1.6 * k)))

        # Knot
        pygame.draw.polygon(s, _shade(color, 0.8), [
            (cx, body_h - 0.02 * h),
            (cx - 0.09 * w, body_h + 0.065 * h),
            (cx + 0.09 * w, body_h + 0.065 * h)])

        # Body, with a darker outline so it stands out on any background
        body = _rect(0, 0, w, body_h)
        pygame.draw.ellipse(s, color, body)
        pygame.draw.ellipse(s, _shade(color, 0.6), body, max(2, int(2.2 * k)))

        # Highlight, kept high so it never sits behind the number
        pygame.draw.ellipse(s, _mix(color, (255, 255, 255), 0.5),
                            _rect(0.22 * w, 0.06 * body_h, 0.20 * w, 0.20 * body_h))

    return _render(("balloon", size, color), size, draw)


def stopwatch(size, color, fraction=1.0):
    """A stopwatch whose hand shows how much time is left: pointing at
    12 when full, sweeping clockwise as it runs down. One color, so the
    caller can pass a color that contrasts with its background."""
    color = tuple(color[:3])
    fraction = max(0.0, min(1.0, fraction))
    step = round(fraction * 60)         # 60 cached hand positions at most

    def draw(s):
        w, h = s.get_size()
        cx = w / 2
        r = 0.46 * w
        cy = h - r - 0.03 * h
        ring = max(2, int(0.075 * w))

        # Crown button and stem
        pygame.draw.rect(s, color, _rect(cx - 0.12 * w, 0, 0.24 * w, 0.10 * h),
                         border_radius=int(0.03 * w))
        pygame.draw.rect(s, color, _rect(cx - 0.05 * w, 0.08 * h, 0.10 * w,
                                         cy - r - 0.08 * h + ring))
        # Side button
        a = math.radians(45)
        pygame.draw.circle(s, color, (cx + (r + 0.02 * w) * math.sin(a),
                                      cy - (r + 0.02 * w) * math.cos(a)), 0.07 * w)
        # Case
        pygame.draw.circle(s, color, (cx, cy), r, ring)
        # Tick marks: long at 12/3/6/9, short elsewhere
        r1 = r - ring - 0.02 * w
        for i in range(12):
            ang = i * math.pi / 6
            major = i % 3 == 0
            r2 = r1 - (0.11 if major else 0.06) * w
            pygame.draw.line(s, color,
                             (cx + r1 * math.sin(ang), cy - r1 * math.cos(ang)),
                             (cx + r2 * math.sin(ang), cy - r2 * math.cos(ang)),
                             max(1, int((0.05 if major else 0.03) * w)))
        # Hand
        ang = 2 * math.pi * (1 - step / 60)
        length = r - ring - 0.14 * w
        pygame.draw.line(s, color, (cx, cy),
                         (cx + length * math.sin(ang), cy - length * math.cos(ang)),
                         max(2, int(0.06 * w)))
        pygame.draw.circle(s, color, (cx, cy), 0.07 * w)

    return _render(("stopwatch", size, color, step), size, draw)


def speaker(size, color, muted=False):
    """A loudspeaker with sound waves - or, when muted, a cross instead
    of the waves, so on/off is visible from the picture alone."""
    color = tuple(color[:3])

    def draw(s):
        w, h = s.get_size()
        lw = max(2, int(0.07 * w))
        pygame.draw.rect(s, color, _rect(0.06 * w, 0.36 * h, 0.20 * w, 0.28 * h),
                         border_radius=int(0.03 * w))
        pygame.draw.polygon(s, color, [(0.24 * w, 0.36 * h), (0.54 * w, 0.12 * h),
                                       (0.54 * w, 0.88 * h), (0.24 * w, 0.64 * h)])
        if muted:
            cx, cy, d = 0.78 * w, 0.5 * h, 0.12 * w
            pygame.draw.line(s, color, (cx - d, cy - d), (cx + d, cy + d), lw)
            pygame.draw.line(s, color, (cx - d, cy + d), (cx + d, cy - d), lw)
        else:
            cx, cy = 0.54 * w, 0.5 * h
            for radius in (0.20 * w, 0.36 * w):
                pts = [(cx + radius * math.cos(a), cy + radius * math.sin(a))
                       for a in [(-0.75 + 1.5 * i / 14) for i in range(15)]]
                pygame.draw.lines(s, color, False, pts, lw)
                for p in (pts[0], pts[-1]):     # round caps
                    pygame.draw.circle(s, color, p, lw / 2)

    return _render(("speaker", size, color, muted), size, draw)


def _is_dark(color):
    """Rough perceived brightness test, only used to pick a detail color."""
    r, g, b = color[:3]
    return (0.299 * r + 0.587 * g + 0.114 * b) < 128


def _detail(color):
    """A color for fine detail (hat band, highlights) that stays visible on
    top of `color`: lighter if the base is dark, darker if it is light."""
    return _mix(color, (255, 255, 255), 0.55) if _is_dark(color) else _shade(color, 0.55)


def hat(size, color):
    """A top hat (for Hoeden): tall crown, a band, and a wide brim. One
    color plus a detail shade, so it works in every theme."""
    color = tuple(color[:3])

    def draw(s):
        w, h = s.get_size()
        k = _SUPERSAMPLE
        line = max(2, int(2.2 * k))
        edge = _shade(color, 0.6) if not _is_dark(color) else _mix(color, (255, 255, 255), 0.35)
        detail = _detail(color)

        # Brim: a wide flat ellipse at the bottom.
        brim = _rect(0.02 * w, 0.70 * h, 0.96 * w, 0.26 * h)
        pygame.draw.ellipse(s, color, brim)
        pygame.draw.ellipse(s, edge, brim, line)

        # Crown: a tall rectangle whose bottom sits inside the brim.
        crown = _rect(0.20 * w, 0.12 * h, 0.60 * w, 0.68 * h)
        pygame.draw.rect(s, color, crown)
        pygame.draw.line(s, edge, crown.topleft, (crown.left, crown.bottom), line)
        pygame.draw.line(s, edge, crown.topright, (crown.right, crown.bottom), line)

        # Front lip of the brim, drawn over the crown's foot so the crown
        # looks like it goes INTO the hat, not on top of it.
        lip = _rect(0.02 * w, 0.70 * h, 0.96 * w, 0.26 * h)
        pygame.draw.arc(s, edge, lip, math.pi, 2 * math.pi, line)
        pygame.draw.ellipse(s, color, _rect(0.20 * w, 0.66 * h, 0.60 * w, 0.20 * h))
        pygame.draw.arc(s, edge, _rect(0.20 * w, 0.66 * h, 0.60 * w, 0.20 * h),
                        math.pi, 2 * math.pi, line)

        # Top face of the crown.
        top = _rect(0.20 * w, 0.06 * h, 0.60 * w, 0.14 * h)
        pygame.draw.ellipse(s, _mix(color, (255, 255, 255), 0.25) if _is_dark(color)
                            else _shade(color, 0.85), top)
        pygame.draw.ellipse(s, edge, top, line)

        # Band around the crown.
        band_top = 0.52 * h
        pygame.draw.rect(s, detail, _rect(0.20 * w + line / 2, band_top,
                                          0.60 * w - line, 0.12 * h))

    return _render(("hat", size, color), size, draw)


def memory_cards(size, color):
    """Two playing cards for Memory: a face-down card with a "?" cut out of
    it, and an outlined face-up card peeking out behind it."""
    color = tuple(color[:3])

    def draw(s):
        w, h = s.get_size()
        k = _SUPERSAMPLE
        line = max(2, int(3 * k))
        radius = int(0.10 * w)

        # Back card (face up, outline only) peeking out behind, with one
        # diamond "pip" so it reads as a playing card, not a document.
        back = _rect(0.40 * w, 0.02 * h, 0.54 * w, 0.76 * h)
        pygame.draw.rect(s, color, back, line, border_radius=radius)
        pcx, pcy, pr = back.centerx + 0.06 * w, back.top + 0.30 * h, 0.09 * w
        pygame.draw.polygon(s, color, [(pcx, pcy - pr * 1.3), (pcx + pr, pcy),
                                       (pcx, pcy + pr * 1.3), (pcx - pr, pcy)])

        # Front card (face down): a big solid block with a "?" punched out.
        front = _rect(0.04 * w, 0.16 * h, 0.64 * w, 0.82 * h)
        pygame.draw.rect(s, color, front, border_radius=radius)
        pygame.draw.rect(s, _detail(color), front, line, border_radius=radius)
        font = pygame.font.SysFont("arial", int(0.66 * front.h), bold=True)
        # Punch the "?" out of the card: build a mask whose ONLY non-zero
        # channel is alpha (the text shape), then subtract it from the card.
        # (Subtracting the plain rendered text would also black out its
        # whole bounding box, because transparent pixels still carry RGB.)
        q = font.render("?", True, (255, 255, 255))
        mask = pygame.Surface(q.get_size(), pygame.SRCALPHA)
        mask.blit(q, (0, 0))
        mask.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGBA_MULT)
        s.blit(mask, mask.get_rect(center=front.center),
               special_flags=pygame.BLEND_RGBA_SUB)

    return _render(("memory_cards", size, color), size, draw)
