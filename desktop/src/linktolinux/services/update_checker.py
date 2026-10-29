from __future__ import annotations

import json
import logging
import platform
import re
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable
from urllib.parse import urlsplit

from packaging.version import InvalidVersion, Version

from linktolinux.storage.state import DesktopSettings

if TYPE_CHECKING:
    from linktolinux.ui.window import LinkToLinuxWindow


GITHUB_REPO = "Youngjay42-real/Link-to-linux"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases/latest"
UPDATE_CHECK_INTERVAL_HOURS = 24
MAX_RESPONSE_BYTES = 1024 * 1024
_SEMVER_PATTERN = re.compile(
    r"^[vV]?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class UpdateRelease:
    version: str
    notes: str
    published_at: str
    download_url: str
    release_url: str

    def as_banner_info(self) -> dict[str, str]:
        return {
            "version": self.version,
            "notes": self.notes,
            "published_at": self.published_at,
            "url": self.download_url,
            "release_url": self.release_url,
        }


def _parse_stable_version(value: str) -> Version | None:
    match = _SEMVER_PATTERN.fullmatch(value)
    if match is None:
        return None
    prerelease = match.group(4)
    if prerelease and any(
        identifier.isdigit() and len(identifier) > 1 and identifier.startswith("0")
        for identifier in prerelease.split(".")
    ):
        return None
    version_text = ".".join(match.group(index) for index in (1, 2, 3))
    if prerelease:
        version_text += f"-{prerelease}"
    try:
        version = Version(version_text)
    except InvalidVersion:
        return None
    return None if version.is_prerelease or version.is_devrelease else version


def _trusted_github_url(value: Any, path_prefix: str) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "github.com"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 443)
            or not parsed.path.startswith(path_prefix)
        ):
            return None
    except ValueError:
        return None
    return value


def _release_page_url(payload: dict[str, Any]) -> str:
    prefix = f"/{GITHUB_REPO}/releases/"
    return _trusted_github_url(payload.get("html_url"), prefix) or GITHUB_RELEASES_URL


def _package_kind() -> str:
    try:
        os_release = platform.freedesktop_os_release()
    except OSError:
        return "portable"
    identifiers = {
        os_release.get("ID", "").lower(),
        *(os_release.get("ID_LIKE", "").lower().split()),
    }
    if identifiers.intersection({"debian", "ubuntu", "linuxmint", "pop"}):
        return "deb"
    if identifiers.intersection({"fedora", "rhel", "centos", "suse", "opensuse"}):
        return "rpm"
    return "portable"


def _download_url(payload: dict[str, Any], package_kind: str) -> str:
    if package_kind == "android":
        wanted = lambda name: name.lower() == "linktolinux-android.apk"
    elif package_kind == "deb":
        wanted = lambda name: name.lower().startswith("linktolinux_") and name.lower().endswith(".deb")
    elif package_kind == "rpm":
        wanted = lambda name: name.lower().startswith("linktolinux-") and name.lower().endswith(".rpm")
    else:
        wanted = lambda name: name.lower().startswith("linktolinux-") and "-linux.tar.gz" in name.lower()

    assets = payload.get("assets")
    if isinstance(assets, list):
        for asset in assets:
            if not isinstance(asset, dict) or not isinstance(asset.get("name"), str):
                continue
            if not wanted(asset["name"]):
                continue
            url = _trusted_github_url(
                asset.get("browser_download_url"),
                f"/{GITHUB_REPO}/releases/download/",
            )
            if url is not None:
                return url
    return _release_page_url(payload)


def parse_latest_release(
    payload: Any,
    current_version: str,
    package_kind: str,
    last_notified_version: str = "",
) -> UpdateRelease | None:
    if not isinstance(payload, dict) or payload.get("draft") is not False or payload.get("prerelease") is not False:
        return None
    tag = payload.get("tag_name")
    if not isinstance(tag, str):
        return None
    latest = _parse_stable_version(tag)
    current = _parse_stable_version(current_version)
    if latest is None or current is None or latest <= current:
        return None
    last_notified = _parse_stable_version(last_notified_version)
    if last_notified is not None and latest <= last_notified:
        return None
    version = tag.removeprefix("v").removeprefix("V")
    body = payload.get("body")
    notes = body.strip()[:500] if isinstance(body, str) else ""
    published_at = payload.get("published_at")
    published_at = published_at[:10] if isinstance(published_at, str) and re.match(r"^\d{4}-\d{2}-\d{2}", published_at) else ""
    return UpdateRelease(
        version=version,
        notes=notes,
        published_at=published_at,
        download_url=_download_url(payload, package_kind),
        release_url=_release_page_url(payload),
    )


def fetch_latest_release(
    current_version: str,
    package_kind: str,
    last_notified_version: str = "",
    opener: Callable[..., Any] | None = None,
) -> UpdateRelease | None:
    request = urllib.request.Request(
        GITHUB_API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "LinkToLinux",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    open_url = opener or urllib.request.urlopen
    try:
        with open_url(request, timeout=8) as response:
            final_url = urlsplit(response.geturl())
            if final_url.scheme != "https" or final_url.hostname != "api.github.com":
                raise ValueError("Unexpected GitHub API response URL.")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("GitHub release response was too large.")
        payload = json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as error:
        rate_limit_remaining = getattr(error.headers, "get", lambda _key: None)("X-RateLimit-Remaining")
        if error.code == 403 and rate_limit_remaining == "0":
            _LOGGER.info("GitHub update check rate limited.")
        else:
            _LOGGER.warning("GitHub update check returned HTTP %s.", error.code)
        return None
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        _LOGGER.warning("GitHub update check failed: %s", type(error).__name__)
        return None
    return parse_latest_release(payload, current_version, package_kind, last_notified_version)


UpdateCallback = Callable[[dict[str, str] | None, str | None], None]


class UpdateChecker:
    """Checks GitHub Releases asynchronously and reports stable app updates."""

    def __init__(self, settings: DesktopSettings, current_version: str) -> None:
        self.settings = settings
        self.current_version = current_version
        self.package_kind = _package_kind()
        self._check_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._periodic_source = 0

    def check_for_updates(self, callback: UpdateCallback | None = None) -> None:
        with self._lock:
            if self._check_thread is not None and self._check_thread.is_alive():
                return
            self._check_thread = threading.Thread(
                target=self._do_check,
                args=(callback,),
                name="linktolinux-update-check",
                daemon=True,
            )
            self._check_thread.start()

    def _do_check(self, callback: UpdateCallback | None) -> None:
        update = fetch_latest_release(
            self.current_version,
            self.package_kind,
            self.settings.last_notified_update_version,
        )
        if callback is not None:
            callback(update.as_banner_info() if update is not None else None, None)

    def mark_notified(self, version: str) -> None:
        self.settings.last_notified_update_version = version
        try:
            self.settings.save()
        except OSError as error:
            _LOGGER.warning("Could not save update notification state: %s", type(error).__name__)

    def start_periodic_checks(self, window: "LinkToLinuxWindow") -> None:
        import gi

        gi.require_version("GLib", "2.0")
        from gi.repository import GLib

        self.check_for_updates(lambda info, error: self._on_check_complete(window, info, error))
        if self._periodic_source:
            return

        def periodic_check() -> bool:
            self.check_for_updates(lambda info, error: self._on_check_complete(window, info, error))
            return True

        self._periodic_source = GLib.timeout_add_seconds(
            UPDATE_CHECK_INTERVAL_HOURS * 3600,
            periodic_check,
        )

    def stop_periodic_checks(self) -> None:
        if not self._periodic_source:
            return
        import gi

        gi.require_version("GLib", "2.0")
        from gi.repository import GLib

        GLib.source_remove(self._periodic_source)
        self._periodic_source = 0

    @staticmethod
    def _on_check_complete(
        window: "LinkToLinuxWindow",
        info: dict[str, str] | None,
        _error: str | None,
    ) -> None:
        if info is None:
            return
        import gi

        gi.require_version("GLib", "2.0")
        from gi.repository import GLib

        def show_update() -> bool:
            window.show_update_banner(info)
            return False

        GLib.idle_add(show_update)
