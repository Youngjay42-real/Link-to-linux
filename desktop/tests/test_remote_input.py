from __future__ import annotations

import socket
from types import SimpleNamespace

from linktolinux.services.remote_input import RemoteInputController


def _install_ydotool(monkeypatch, socket_path: str) -> None:
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("YDOTOOL_SOCKET", socket_path)
    monkeypatch.setattr(
        "linktolinux.services.remote_input.shutil.which",
        lambda command: f"/usr/bin/{command}" if command == "ydotool" else None,
    )


def test_wayland_backend_selected_from_session_type(monkeypatch) -> None:
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(
        "linktolinux.services.remote_input.shutil.which",
        lambda command: f"/usr/bin/{command}" if command == "ydotool" else None,
    )

    assert RemoteInputController().backend == "ydotool"


def test_wayland_detected_from_display_when_session_type_missing(monkeypatch) -> None:
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setattr(
        "linktolinux.services.remote_input.shutil.which",
        lambda command: f"/usr/bin/{command}" if command == "ydotool" else None,
    )

    assert RemoteInputController().backend == "ydotool"


def test_ydotool_requires_reachable_daemon_socket(monkeypatch, tmp_path) -> None:
    socket_path = str(tmp_path / "ydotool.sock")
    _install_ydotool(monkeypatch, socket_path)
    controller = RemoteInputController()

    assert controller.available is False
    assert "systemctl --user start ydotool.service" in controller.description


def test_ydotool_available_when_daemon_socket_is_listening(monkeypatch, tmp_path) -> None:
    socket_path = str(tmp_path / "ydotool.sock")
    _install_ydotool(monkeypatch, socket_path)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    listener.bind(socket_path)
    try:
        assert RemoteInputController().available is True
    finally:
        listener.close()


def test_ydotool_move_passes_negative_coordinates_as_arguments(monkeypatch) -> None:
    _install_ydotool(monkeypatch, "/not-used")
    monkeypatch.setattr(RemoteInputController, "available", property(lambda _self: True))
    commands = []
    monkeypatch.setattr(
        "linktolinux.services.remote_input.subprocess.run",
        lambda command, **kwargs: commands.append((command, kwargs)) or SimpleNamespace(
            returncode=0, stderr=""
        ),
    )

    RemoteInputController().perform("move", dx=-12, dy=-7)

    assert commands[0][0] == ["ydotool", "mousemove", "--", "-12", "-7"]


def test_ydotool_type_uses_low_delay_and_sufficient_timeout(monkeypatch) -> None:
    _install_ydotool(monkeypatch, "/not-used")
    monkeypatch.setattr(RemoteInputController, "available", property(lambda _self: True))
    commands = []
    monkeypatch.setattr(
        "linktolinux.services.remote_input.subprocess.run",
        lambda command, **kwargs: commands.append((command, kwargs)) or SimpleNamespace(
            returncode=0, stderr=""
        ),
    )
    text = "complete message " * 60

    RemoteInputController().perform("type", text=text)

    command, options = commands[0]
    assert command == [
        "ydotool", "type", "--key-delay=1", "--key-hold=1", "--", text
    ]
    assert options["timeout"] > 5
