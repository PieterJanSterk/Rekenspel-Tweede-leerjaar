"""
input_devices.py

Gives us TWO independent cursors (one per player), each with an (x, y)
position and a "just fired" flag.

Why this file exists at all:
  pygame's own mouse API (pygame.mouse.get_pos()) only ever sees ONE cursor,
  because the OS merges every pointing device into a single system cursor.
  That is fine for a single Sinden gun, but breaks the moment you plug in a
  second one. To get two truly independent cursors we bypass pygame.mouse
  entirely and read each gun as its own raw input device via `evdev`
  (Linux only - this is what Batocera runs on).

Two modes, chosen automatically:

  HARDWARE MODE (on Batocera, with guns plugged in)
      We scan /dev/input for devices that report absolute X/Y axes
      (ABS_X / ABS_Y) - that's how Sinden guns and most lightguns present
      themselves. The first two we find become Player 1 and Player 2.

  DEV MODE (anywhere else - your PC, testing without guns)
      Player 1 -> the system mouse (left click = fire)
      Player 2 -> arrow keys to move + Enter to fire
      This lets you build and test the game logic on a laptop before ever
      touching the Batocera box.

If you only have ONE gun plugged in (e.g. testing solo), Player 2
automatically falls back to the keyboard, so you never get stuck.
"""

import pygame

try:
    import evdev
    from evdev import ecodes
    EVDEV_AVAILABLE = True
except ImportError:
    # evdev is Linux-only and won't be installed on e.g. Windows dev machines.
    EVDEV_AVAILABLE = False


class Cursor:
    """One player's pointer: where it is, and whether it just fired."""

    def __init__(self, player_id, color):
        self.player_id = player_id
        self.color = color          # used to draw a distinct crosshair
        self.x = 0.0
        self.y = 0.0
        self.fired = False          # True for exactly one frame per trigger pull
        self._was_down = False      # tracks button state so we can edge-detect

    def _set_button(self, is_down):
        """Turn a raw 'button is down' reading into a one-frame 'fired' pulse."""
        self.fired = is_down and not self._was_down
        self._was_down = is_down


class _EvdevGun:
    """Wraps one raw evdev device and tracks its absolute position + button."""

    def __init__(self, device):
        self.device = device
        device.grab_nonblocking = True
        try:
            device.set_nonblocking(True)
        except Exception:
            pass
        abs_caps = dict(device.capabilities().get(ecodes.EV_ABS, []))
        x_info = abs_caps.get(ecodes.ABS_X)
        y_info = abs_caps.get(ecodes.ABS_Y)
        # Remember the device's own reported range so we can scale it to
        # whatever resolution the game window actually is.
        self.x_min, self.x_max = (x_info.min, x_info.max) if x_info else (0, 1)
        self.y_min, self.y_max = (y_info.min, y_info.max) if y_info else (0, 1)
        self.raw_x = (self.x_min + self.x_max) / 2
        self.raw_y = (self.y_min + self.y_max) / 2
        self.button_down = False

    def poll(self):
        """Drain any pending events from this device. Never blocks."""
        try:
            for event in self.device.read():
                if event.type == ecodes.EV_ABS:
                    if event.code == ecodes.ABS_X:
                        self.raw_x = event.value
                    elif event.code == ecodes.ABS_Y:
                        self.raw_y = event.value
                elif event.type == ecodes.EV_KEY:
                    # Lightguns typically report BTN_LEFT for the trigger.
                    if event.code in (ecodes.BTN_LEFT, ecodes.BTN_GAMEPAD,
                                       ecodes.BTN_TRIGGER):
                        self.button_down = bool(event.value)
        except BlockingIOError:
            pass
        except OSError:
            pass  # device unplugged mid-game - just stop updating it

    def scaled_position(self, screen_w, screen_h):
        norm_x = (self.raw_x - self.x_min) / max(1, (self.x_max - self.x_min))
        norm_y = (self.raw_y - self.y_min) / max(1, (self.y_max - self.y_min))
        return norm_x * screen_w, norm_y * screen_h


def _find_gun_devices(max_count=2):
    """Look for real absolute-pointer hardware (Sinden guns etc)."""
    if not EVDEV_AVAILABLE:
        return []
    found = []
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
            caps = dev.capabilities().get(ecodes.EV_ABS, [])
            has_xy = any(code == ecodes.ABS_X for code, _ in caps) and \
                     any(code == ecodes.ABS_Y for code, _ in caps)
            if has_xy:
                found.append(_EvdevGun(dev))
        except Exception:
            continue
        if len(found) >= max_count:
            break
    return found


class InputManager:
    """
    Owns Player 1 and Player 2 cursors and updates them every frame.
    Call update(screen_w, screen_h) once per frame, then read
    manager.player1 / manager.player2.
    """

    PLAYER_COLORS = [(255, 60, 60), (60, 140, 255)]  # red, blue

    def __init__(self):
        self.player1 = Cursor(1, self.PLAYER_COLORS[0])
        self.player2 = Cursor(2, self.PLAYER_COLORS[1])

        self._guns = _find_gun_devices(max_count=2)
        self.hardware_mode = len(self._guns) >= 1
        if self.hardware_mode:
            print(f"[input] Found {len(self._guns)} lightgun-style device(s); "
                  f"using hardware mode for that many player(s).")
        else:
            print("[input] No lightgun devices found - using mouse+keyboard "
                  "dev mode.")

    def update(self, screen_w, screen_h):
        keys = pygame.key.get_pressed()

        # --- Player 1 ---
        if len(self._guns) >= 1:
            gun = self._guns[0]
            gun.poll()
            self.player1.x, self.player1.y = gun.scaled_position(screen_w, screen_h)
            self.player1._set_button(gun.button_down)
        else:
            mx, my = pygame.mouse.get_pos()
            self.player1.x, self.player1.y = mx, my
            self.player1._set_button(pygame.mouse.get_pressed()[0])

        # --- Player 2 ---
        if len(self._guns) >= 2:
            gun = self._guns[1]
            gun.poll()
            self.player2.x, self.player2.y = gun.scaled_position(screen_w, screen_h)
            self.player2._set_button(gun.button_down)
        else:
            # Keyboard fallback: arrow keys move a virtual cursor, Enter fires.
            speed = 12
            if keys[pygame.K_LEFT]:
                self.player2.x -= speed
            if keys[pygame.K_RIGHT]:
                self.player2.x += speed
            if keys[pygame.K_UP]:
                self.player2.y -= speed
            if keys[pygame.K_DOWN]:
                self.player2.y += speed
            self.player2.x = max(0, min(screen_w, self.player2.x))
            self.player2.y = max(0, min(screen_h, self.player2.y))
            self.player2._set_button(keys[pygame.K_RETURN])
