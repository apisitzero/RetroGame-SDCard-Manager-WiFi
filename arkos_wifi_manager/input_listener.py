# -*- coding: utf-8 -*-
"""
Console Input Listener for R36S & ArkOS Handhelds
Listens for physical gamepad buttons (B, SELECT+START, FN, START) and keyboard inputs.
Zero-dependency: uses standard Python os, select, struct, glob.
"""

import os
import sys
import glob
import select
import struct
import threading
import time

class ConsoleInputListener(threading.Thread):
    """
    Background daemon thread that monitors Linux /dev/input/event* devices,
    /dev/tty1, and sys.stdin for gamepad button presses and keyboard inputs.
    """
    def __init__(self, on_exit_callback):
        super().__init__(daemon=True)
        self.on_exit = on_exit_callback
        self.running = True
        self.pressed_keys = set()
        self._exit_triggered = False

    def stop(self):
        self.running = False

    def run(self):
        # 1. Open all available /dev/input/event* devices
        event_fds = {}
        if os.path.exists('/dev/input'):
            event_paths = sorted(glob.glob('/dev/input/event*'))
            for p in event_paths:
                try:
                    fd = os.open(p, os.O_RDONLY | os.O_NONBLOCK)
                    event_fds[fd] = p
                except Exception:
                    pass

        # 2. Add stdin fd if available
        stdin_fd = None
        try:
            if hasattr(sys.stdin, 'fileno'):
                stdin_fd = sys.stdin.fileno()
                try:
                    import fcntl
                    flags = fcntl.fcntl(stdin_fd, fcntl.F_GETFL)
                    fcntl.fcntl(stdin_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
                except Exception:
                    pass
        except Exception:
            pass

        # 3. Add /dev/tty1 direct handle if available on Linux console
        tty_fd = None
        if os.path.exists('/dev/tty1'):
            try:
                tty_fd = os.open('/dev/tty1', os.O_RDONLY | os.O_NONBLOCK)
            except Exception:
                pass

        all_read_fds = list(event_fds.keys())
        if stdin_fd is not None and stdin_fd not in all_read_fds:
            all_read_fds.append(stdin_fd)
        if tty_fd is not None and tty_fd not in all_read_fds:
            all_read_fds.append(tty_fd)

        # Polling loop
        while self.running and not self._exit_triggered:
            if not all_read_fds:
                time.sleep(0.3)
                continue

            try:
                readable, _, _ = select.select(all_read_fds, [], [], 0.15)
            except Exception:
                break

            for fd in readable:
                if self._exit_triggered:
                    break

                # Handle /dev/input/event*
                if fd in event_fds:
                    try:
                        raw_bytes = os.read(fd, 256)
                        if raw_bytes:
                            self._process_evdev_data(raw_bytes, event_fds[fd])
                    except Exception:
                        pass

                # Handle stdin or tty1 (keyboard / terminal input)
                elif fd == stdin_fd or fd == tty_fd:
                    try:
                        chars = os.read(fd, 64)
                        if chars:
                            for b in chars:
                                # 'q', 'Q', 'b', 'B', ESC (0x1b), Ctrl+C (0x03), Enter (0x0a, 0x0d)
                                if b in (ord('q'), ord('Q'), ord('b'), ord('B'), 0x1b, 0x03, 0x0a, 0x0d):
                                    self._trigger_exit(f"Keyboard input: {chr(b) if b >= 32 else hex(b)}")
                                    break
                    except Exception:
                        pass

        # Cleanup file descriptors on termination
        for fd in list(event_fds.keys()):
            try:
                os.close(fd)
            except Exception:
                pass
        if tty_fd is not None:
            try:
                os.close(tty_fd)
            except Exception:
                pass

    def _process_evdev_data(self, data, dev_path):
        """Decodes raw input_event structures from evdev node."""
        step = 24 if len(data) % 24 == 0 else (16 if len(data) % 16 == 0 else 24)
        for i in range(0, len(data), step):
            chunk = data[i:i + step]
            if len(chunk) < 8:
                continue

            # Last 8 bytes are (=HHi): type (unsigned short), code (unsigned short), value (signed int)
            ev_type, ev_code, ev_val = struct.unpack('=HHi', chunk[-8:])

            # EV_KEY = 1
            if ev_type == 1:
                # ev_val: 1 = Press, 0 = Release, 2 = Repeat/Hold
                if ev_val == 1:
                    self.pressed_keys.add(ev_code)
                elif ev_val == 0:
                    self.pressed_keys.discard(ev_code)

                # ================= Button Actions =================
                # 1. Button B:
                #    In Linux evdev:
                #    305 = BTN_B / BTN_EAST (Standard B button)
                #    304 = BTN_A / BTN_SOUTH (In Nintendo layout, B is at south / A is east)
                #    48  = KEY_B
                #    1   = KEY_ESC
                #    16  = KEY_Q
                #    116 = KEY_POWER
                #    316 = BTN_MODE (FN button on R36S)
                #    102 = KEY_HOME
                if ev_val == 1:
                    if ev_code in (304, 305, 48, 1, 16, 316, 102):
                        self._trigger_exit(f"Button pressed (code: {ev_code})")
                        return

                # 2. SELECT (314) + START (315) combo:
                if 314 in self.pressed_keys and 315 in self.pressed_keys:
                    self._trigger_exit("SELECT + START combo pressed")
                    return

                # 3. START (315) alone:
                if ev_val == 1 and ev_code == 315:
                    self._trigger_exit("START button pressed")
                    return

    def _trigger_exit(self, reason):
        if self._exit_triggered:
            return
        self._exit_triggered = True
        self.running = False
        if callable(self.on_exit):
            self.on_exit(reason)
