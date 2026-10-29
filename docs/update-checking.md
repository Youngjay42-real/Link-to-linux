# Update checks

Link to Linux checks the public GitHub Releases API when the app starts and then
about once every 24 hours while it remains open. Requests use HTTPS, an
eight-second timeout, and no credentials. A failed, offline, rate-limited, or
invalid response is logged and ignored; it does not prevent either app from
starting. Drafts, prereleases, malformed tags, and releases that are not newer
than the installed version are ignored.

The desktop shows a GTK banner and selects a `.deb`, `.rpm`, or portable Linux
archive based on the distribution. Android shows an in-app banner and links to
the APK. If the matching release asset is missing or not a trusted GitHub
asset URL, the banner opens the official release page instead. Selecting
**Download update** opens the platform's browser; files are never installed or
executed automatically. On Android, install the downloaded APK through Android's
normal package installer and approve any system prompt.

The desktop version is defined by `desktop/src/linktolinux/__init__.py`; the
Python package metadata reads that value. Android's `versionName` in
`android/app/build.gradle.kts` is the installed version reported to the checker,
while `versionCode` remains the Android-specific upgrade number.

## Validate locally

Desktop unit tests use mocked API responses and do not contact GitHub:

```bash
cd desktop
PYTHONPATH=src .venv/bin/python -m pytest -q tests
```

Android unit tests also use mocked release JSON/fetch functions:

```bash
cd android
./gradlew testReleaseUnitTest
```

These tests exercise release parsing, version comparisons, download selection,
duplicate suppression, malformed responses, offline errors, and API rate
limits without publishing a release. To build the signed Android release APK
and run those tests together:

```bash
cd android
./gradlew testReleaseUnitTest assembleRelease
```

A signing configuration in `android/signing.properties` and its local
keystore are needed for a signed APK. Keep both out of source control. The
checker itself requires no token, GitHub configuration, Android notification
permission, or extra network service.
Debian/RPM packages declare the Python Packaging module dependency used for
semantic-version parsing; portable Linux users need their distribution's
`python3-packaging` package.

## Publish a release

1. Set the desktop package version in `desktop/src/linktolinux/__init__.py`.
2. Set Android `versionName` and increase `versionCode` in
   `android/app/build.gradle.kts`.
3. Update `packaging/RELEASE_NOTES.md`. Build all release assets with matching
   names, including `LinkToLinux-Android.apk`,
   `linktolinux_<version>_all.deb`,
   `linktolinux-<version>-1.noarch.rpm`, and
   `LinkToLinux-<version>-Linux.tar.gz`.
4. Create and publish a GitHub Release in
   `Youngjay42-real/Link-to-linux`, using a stable tag such as `v1.2.0` or
   `1.2.0`. Upload the assets and publish the release (do not leave it as a
   draft or mark it prerelease).

To run the release builds after updating the two platform versions, build the
signed Android APK and run the complete bundle script from the project root:

```bash
cd android
./gradlew testReleaseUnitTest assembleRelease
cd ..
VERSION=1.2.0 ANDROID_APK=android/app/build/outputs/apk/release/app-release.apk \
  packaging/build_release_bundle.sh
```

The bundle script derives its default package version from the desktop
`__version__`, creates a source archive without the Git directory, local
signing files, virtual environments, caches, or previous `dist/` builds, and
writes the release assets into `dist/release-assets-<version>/`.

After publication, users see the update banner on the next startup check or
within approximately 24 hours if the app remains running. Users choose when to
download and install the update. The desktop uses its distribution's package
asset when available; the Android app points to the APK.

## Limitations

Checks are periodic only while an app process is running; there is no background
service. GitHub's unauthenticated API rate limit may delay a check, in which
case the next scheduled check retries. The first implementation does not verify
release signatures or checksums before opening a download. It trusts HTTPS
GitHub release metadata and only follows asset links hosted on the project's
GitHub release path. Linux users install package updates manually, and Android
installation remains subject to Android's package-installer controls.
