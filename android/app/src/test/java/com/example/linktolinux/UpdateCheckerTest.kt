package com.example.linktolinux

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test
import java.io.IOException

class UpdateCheckerTest {
    @Test
    fun detectsNewerStableReleaseWithVTagAndAndroidAsset() {
        val update = UpdateChecker.parseLatestRelease(
            release("v1.2.0", androidAsset = true).toString(),
            "1.1.1",
        )

        assertNotNull(update)
        assertEquals("1.2.0", update?.version)
        assertEquals("2026-10-24", update?.publishedAt)
        assertEquals(
            "https://github.com/Youngjay42-real/Link-to-linux/releases/download/v1.2.0/LinkToLinux-Android.apk",
            update?.url,
        )
    }

    @Test
    fun acceptsTagWithoutVPrefixAndIgnoresBuildMetadataForComparison() {
        val update = UpdateChecker.parseLatestRelease(
            release("1.2.0+build.4").toString(),
            "1.1.1",
        )

        assertEquals("1.2.0+build.4", update?.version)
        assertNull(
            UpdateChecker.parseLatestRelease(
                release("1.2.0+build.4").toString(),
                "1.2.0+build.3",
            ),
        )
    }

    @Test
    fun currentAndOlderVersionsDoNotTriggerAnUpdate() {
        assertNull(UpdateChecker.parseLatestRelease(release("v1.1.1").toString(), "1.1.1"))
        assertNull(UpdateChecker.parseLatestRelease(release("1.0.9").toString(), "1.1.1"))
    }

    @Test
    fun invalidAndPrereleaseTagsAreIgnored() {
        listOf("latest", "v1.2", "01.2.0", "v1.2.0-rc.1").forEach { tag ->
            assertNull(UpdateChecker.parseLatestRelease(release(tag).toString(), "1.1.1"))
        }
        assertNull(UpdateChecker.parseLatestRelease(release("v1.2.0", prerelease = true).toString(), "1.1.1"))
        assertNull(UpdateChecker.parseLatestRelease(release("v1.2.0", draft = true).toString(), "1.1.1"))
    }

    @Test
    fun semanticVersionComparisonHandlesPrereleasesAndLargeNumbers() {
        val release = UpdateChecker.parseSemanticVersion("1.2.0")
        val candidate = UpdateChecker.parseSemanticVersion("1.2.0-rc.2")
        val numeric = UpdateChecker.parseSemanticVersion("10.0.0")
        val largerMajor = UpdateChecker.parseSemanticVersion("9.999999999999999999999.0")

        assertNotNull(release)
        assertNotNull(candidate)
        assertNotNull(numeric)
        assertNotNull(largerMajor)
        assertEquals(true, release!! > candidate!!)
        assertEquals(true, numeric!! > largerMajor!!)
    }

    @Test
    fun suppressesAlreadyNotifiedVersion() {
        assertNull(
            UpdateChecker.parseLatestRelease(
                release("v1.2.0").toString(),
                "1.1.1",
                lastNotifiedVersion = "1.2.0",
            ),
        )
    }

    @Test
    fun missingOrUntrustedAssetsFallBackToOfficialReleasePage() {
        val noAsset = UpdateChecker.parseLatestRelease(release("v1.2.0").toString(), "1.1.1")
        assertEquals(
            "https://github.com/Youngjay42-real/Link-to-linux/releases/tag/v1.2.0",
            noAsset?.url,
        )

        val untrustedAsset = release("v1.2.0", androidAsset = true).apply {
            getJSONArray("assets").getJSONObject(0)
                .put("browser_download_url", "https://example.com/fake.apk")
        }
        assertEquals(
            "https://github.com/Youngjay42-real/Link-to-linux/releases/tag/v1.2.0",
            UpdateChecker.parseLatestRelease(untrustedAsset.toString(), "1.1.1")?.url,
        )
    }

    @Test
    fun failedNetworkAndRateLimitChecksAreNonFatal() {
        assertNull(
            UpdateChecker.checkForUpdate("1.1.1", "") {
                throw IOException("offline")
            },
        )
        assertNull(
            UpdateChecker.checkForUpdate("1.1.1", "") {
                throw ReleaseHttpException(403, rateLimitExhausted = true)
            },
        )
    }

    @Test
    fun malformedApiResponseAndInvalidInstalledVersionDoNotTrigger() {
        assertNull(UpdateChecker.checkForUpdate("1.1.1", "") { "{bad json" })
        assertNull(UpdateChecker.parseLatestRelease(release("v1.2.0").toString(), "unknown"))
    }

    private fun release(
        tag: String,
        draft: Boolean = false,
        prerelease: Boolean = false,
        androidAsset: Boolean = false,
    ): JSONObject {
        val assets = JSONArray()
        if (androidAsset) {
            assets.put(
                JSONObject()
                    .put("name", "LinkToLinux-Android.apk")
                    .put(
                        "browser_download_url",
                        "https://github.com/Youngjay42-real/Link-to-linux/releases/download/$tag/LinkToLinux-Android.apk",
                    ),
            )
        }
        return JSONObject()
            .put("tag_name", tag)
            .put("draft", draft)
            .put("prerelease", prerelease)
            .put("body", "Release notes")
            .put("published_at", "2026-10-24T12:00:00Z")
            .put(
                "html_url",
                "https://github.com/Youngjay42-real/Link-to-linux/releases/tag/$tag",
            )
            .put("assets", assets)
    }
}
