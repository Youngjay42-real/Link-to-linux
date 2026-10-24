from __future__ import annotations

import os
import shutil
import socket
import subprocess
from pathlib import Path


class RemoteInputController:
    """Apply tightly validated remote input through the active Linux session."""

    _KEYS = {
        "Enter": ("Return", 28),
        "Backspace": ("BackSpace", 14),
        "Tab": ("Tab", 15),
        "Escape": ("Escape", 1),
        "Left": ("Left", 105),
        "Right": ("Right", 106),
        "Up": ("Up", 103),
        "Down": ("Down", 108),
    }
    _BUTTONS = {1: ("1", "0xC0"), 2: ("2", "0xC2"), 3: ("3", "0xC1")}

    def __init__(self) -> None:
        session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
        wayland = session_type == "wayland" or (
            not session_type and bool(os.environ.get("WAYLAND_DISPLAY"))
        )
        preferred = "ydotool" if wayland else "xdotool"
        self.backend = preferred if shutil.which(preferred) else ""

    @property
    def socket_path(self) -> Path:
        configured_path = os.environ.get("YDOTOOL_SOCKET")
        if configured_path:
            return Path(configured_path)
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        return Path(runtime_dir) / ".ydotool_socket"

    @property
    def daemon_ready(self) -> bool:
        if self.backend != "ydotool":
            return self.backend == "xdotool"
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
                client.settimeout(0.2)
                client.connect(str(self.socket_path))
            return True
        except OSError:
            return False

    @property
    def available(self) -> bool:
        return bool(self.backend) and self.daemon_ready

    @property
    def description(self) -> str:
        if self.backend == "ydotool":
            if not self.daemon_ready:
                return (
                    f"ydotool is installed, but its daemon is not reachable at {self.socket_path}. "
                    "Start it with `systemctl --user start ydotool.service`. The daemon also needs "
                    "permission to access /dev/uinput; do not run Link to Linux as root."
                )
            return "ydotool and its daemon are available for this Wayland session."
        if self.backend == "xdotool":
            return "xdotool is available for this desktop session."
        return "Install ydotool for Wayland or xdotool for X11 to enable remote input."

    def perform(
        self,
        action: str,
        *,
        dx: int = 0,
        dy: int = 0,
        button: int = 1,
        text: str = "",
        key: str = "",
        repeat: int = 1,
    ) -> None:
        if not self.available:
            raise ValueError(self.description)
        if action == "move":
            dx, dy = max(-800, min(800, dx)), max(-800, min(800, dy))
            if dx == 0 and dy == 0:
                return
            command = ([self.backend, "mousemove_relative", "--sync", "--", str(dx), str(dy)]
                       if self.backend == "xdotool" else [self.backend, "mousemove", "--", str(dx), str(dy)])
        elif action == "click":
            if button not in self._BUTTONS:
                raise ValueError("Unsupported mouse button.")
            command = ([self.backend, "click", "--clearmodifiers", self._BUTTONS[button][0]]
                       if self.backend == "xdotool" else [self.backend, "click", self._BUTTONS[button][1]])
        elif action == "scroll":
            dx = max(-12, min(12, dx))
            dy = max(-12, min(12, dy))
            if dx == 0 and dy == 0:
                return
            if self.backend == "xdotool":
                command = [self.backend]
                if dy:
                    command.extend([
                        "click", "--repeat", str(abs(dy)), "--delay", "0", "4" if dy > 0 else "5",
                    ])
                if dx:
                    command.extend([
                        "click", "--repeat", str(abs(dx)), "--delay", "0", "7" if dx > 0 else "6",
                    ])
            else:
                command = [self.backend, "mousemove", "--wheel", "-x", str(dx), "-y", str(dy)]
        elif action == "type":
            if not text or len(text) > 1024 or any(ord(char) < 32 and char not in "\n\t" for char in text):
                raise ValueError("Text input must contain 1–1024 printable characters.")
            command = ([self.backend, "type", "--clearmodifiers", "--delay", "0", "--", text]
                       if self.backend == "xdotool" else [
                           self.backend, "type", "--key-delay=1", "--key-hold=1", "--", text
                       ])
        elif action == "key":
            if key not in self._KEYS:
                raise ValueError("Unsupported keyboard key.")
            if type(repeat) is not int or not 1 <= repeat <= 1024:
                raise ValueError("Key repeat must be between 1 and 1024.")
            command = ([self.backend, "key", "--clearmodifiers", self._KEYS[key][0]]
                       if self.backend == "xdotool" and repeat == 1 else
                       [self.backend, "key", "--repeat", str(repeat), "--delay", "0", self._KEYS[key][0]]
                       if self.backend == "xdotool" else
                       [self.backend, "key", *([f"{self._KEYS[key][1]}:1", f"{self._KEYS[key][1]}:0"] * repeat)])
        else:
            raise ValueError("Unsupported remote input action.")
        try:
            timeout = max(5.0, len(text) * 0.01 + 3.0) if action == "type" else 2.0
            result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as error:
            raise ValueError("Desktop input tool timed out.") from error
        if result.returncode:
            detail = result.stderr.strip()[:180]
            raise ValueError(detail or "The desktop input tool could not apply the event.")
