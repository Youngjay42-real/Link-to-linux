# Android APK

Build a signed release APK from this directory with:

```sh
./gradlew assembleRelease
```

The APK is written to `app/build/outputs/apk/release/app-release.apk`. Release
signing uses the local `linktolinux-release.jks` keystore and `signing.properties`
file. Both are intentionally ignored by Git. Keep secure backups of both files:
future APK updates must use the same signing key to update an existing install.

To pair, start a session on the desktop and scan its QR code in the app. Manual
entry remains available. Pairing verifies the desktop's certificate before
sending the short-lived code. QR scanning uses Google Play Services' code
scanner, so devices without Play Services can use manual entry instead.
