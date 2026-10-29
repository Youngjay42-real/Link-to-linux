from __future__ import annotations

import json
import urllib.error
from email.message import Message
from types import SimpleNamespace

import pytest

from linktolinux.services.update_checker import (
    GITHUB_RELEASES_URL,
    fetch_latest_release,
    parse_latest_release,
)


def _release(
    tag: str = "v1.2.0",
    *,
    draft: bool = False,
    prerelease: bool = False,
    assets: list[dict[str, str]] | None = None,
) -> dict:
    return {
        "tag_name": tag,
        "draft": draft,
        "prerelease": prerelease,
        "body": "Release notes for this version.",
        "published_at": "2026-10-24T12:00:00Z",
        "html_url": f"https://github.com/Youngjay42-real/Link-to-linux/releases/tag/{tag}",
        "assets": assets or [],
    }


def _asset(name: str, url: str | None = None) -> dict[str, str]:
    return {
        "name": name,
        "browser_download_url": url or (
            "https://github.com/Youngjay42-real/Link-to-linux/releases/download/v1.2.0/"
            + name
        ),
    }


@pytest.mark.parametrize("tag", ["v1.2.0", "1.2.0"])
def test_newer_stable_release_accepts_version_tags_with_or_without_v(tag: str) -> None:
    update = parse_latest_release(_release(tag), "1.1.1", "portable")

    assert update is not None
    assert update.version == "1.2.0"
    assert update.notes == "Release notes for this version."
    assert update.published_at == "2026-10-24"
    assert update.download_url == update.release_url
    assert update.download_url.endswith("/releases/tag/" + tag)


@pytest.mark.parametrize("tag", ["1.1.1", "1.0.9"])
def test_current_or_older_release_does_not_trigger(tag: str) -> None:
    assert parse_latest_release(_release(tag), "1.1.1", "portable") is None


@pytest.mark.parametrize("tag", ["latest", "v1.2", "01.2.0", "v1.2.0-rc.1"])
def test_invalid_or_prerelease_tags_are_ignored(tag: str) -> None:
    assert parse_latest_release(_release(tag), "1.1.1", "portable") is None


@pytest.mark.parametrize(
    ("package_kind", "asset_name"),
    [
        ("deb", "linktolinux_1.2.0_all.deb"),
        ("rpm", "linktolinux-1.2.0-1.noarch.rpm"),
        ("portable", "LinkToLinux-1.2.0-Linux.tar.gz"),
        ("android", "LinkToLinux-Android.apk"),
    ],
)
def test_selects_platform_download_asset(package_kind: str, asset_name: str) -> None:
    update = parse_latest_release(
        _release(assets=[_asset(asset_name)]),
        "1.1.1",
        package_kind,
    )

    assert update is not None
    assert update.download_url.endswith("/" + asset_name)


def test_missing_or_untrusted_asset_falls_back_to_release_page() -> None:
    release = _release(assets=[_asset(
        "LinkToLinux-Android.apk",
        "https://example.com/fake.apk",
    )])

    update = parse_latest_release(release, "1.1.1", "android")

    assert update is not None
    assert update.download_url == release["html_url"]


def test_untrusted_release_page_falls_back_to_official_latest_page() -> None:
    release = _release()
    release["html_url"] = "https://example.com/not-our-release"

    update = parse_latest_release(release, "1.1.1", "portable")

    assert update is not None
    assert update.release_url == GITHUB_RELEASES_URL
    assert update.download_url == GITHUB_RELEASES_URL


def test_already_notified_release_is_suppressed() -> None:
    assert parse_latest_release(
        _release("v1.2.0"),
        "1.1.1",
        "portable",
        last_notified_version="1.2.0",
    ) is None


def test_semver_build_metadata_does_not_change_version_precedence_or_duplicate_checks() -> None:
    assert parse_latest_release(
        _release("v1.2.0+build.2"),
        "1.2.0+build.1",
        "portable",
    ) is None
    assert parse_latest_release(
        _release("v1.2.0+build.2"),
        "1.1.1",
        "portable",
        last_notified_version="1.2.0+build.1",
    ) is None


def test_draft_and_prerelease_releases_are_ignored() -> None:
    assert parse_latest_release(_release(draft=True), "1.1.1", "portable") is None
    assert parse_latest_release(_release(prerelease=True), "1.1.1", "portable") is None


def test_fetch_uses_https_and_parses_mocked_api_response() -> None:
    response = SimpleNamespace(
        read=lambda _limit: json.dumps(_release("v1.2.0")).encode(),
        geturl=lambda: "https://api.github.com/repos/Youngjay42-real/Link-to-linux/releases/latest",
    )
    calls: list[tuple[object, int]] = []

    class MockResponse:
        def __enter__(self) -> SimpleNamespace:
            return response

        def __exit__(self, *_args: object) -> None:
            return None

    def opener(request: object, timeout: int) -> MockResponse:
        calls.append((request, timeout))
        return MockResponse()

    update = fetch_latest_release("1.1.1", "portable", opener=opener)

    assert update is not None
    assert calls[0][1] == 8
    assert calls[0][0].full_url.startswith("https://api.github.com/")


def test_network_failure_does_not_produce_an_update() -> None:
    def opener(*_args: object, **_kwargs: object) -> None:
        raise urllib.error.URLError("offline")

    assert fetch_latest_release("1.1.1", "portable", opener=opener) is None


def test_github_rate_limit_is_handled_without_update() -> None:
    headers = Message()
    headers["X-RateLimit-Remaining"] = "0"

    def opener(*_args: object, **_kwargs: object) -> None:
        raise urllib.error.HTTPError(
            "https://api.github.com/",
            403,
            "rate limit",
            headers,
            None,
        )

    assert fetch_latest_release("1.1.1", "portable", opener=opener) is None


def test_malformed_api_response_and_wrong_endpoint_are_ignored() -> None:
    malformed = SimpleNamespace(
        read=lambda _limit: b"{not-json",
        geturl=lambda: "https://api.github.com/repos/Youngjay42-real/Link-to-linux/releases/latest",
    )

    class MockResponse:
        def __enter__(self) -> SimpleNamespace:
            return malformed

        def __exit__(self, *_args: object) -> None:
            return None

    assert fetch_latest_release("1.1.1", "portable", opener=lambda *_args, **_kwargs: MockResponse()) is None

    wrong_endpoint = SimpleNamespace(
        read=lambda _limit: json.dumps(_release("v1.2.0")).encode(),
        geturl=lambda: "http://example.com/fake",
    )

    class WrongEndpointResponse:
        def __enter__(self) -> SimpleNamespace:
            return wrong_endpoint

        def __exit__(self, *_args: object) -> None:
            return None

    assert fetch_latest_release(
        "1.1.1",
        "portable",
        opener=lambda *_args, **_kwargs: WrongEndpointResponse(),
    ) is None
