package com.example.linktolinux

import org.json.JSONException
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.math.BigInteger
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL
import java.util.logging.Logger

private const val GITHUB_REPO = "Youngjay42-real/Link-to-linux"
private const val GITHUB_API_URL = "https://api.github.com/repos/$GITHUB_REPO/releases/latest"
private const val GITHUB_RELEASES_URL = "https://github.com/$GITHUB_REPO/releases/latest"
private const val MAX_RELEASE_RESPONSE_BYTES = 1024 * 1024
private val updateLogger = Logger.getLogger("LinkToLinuxUpdates")

internal data class UpdateInfo(
    val version: String,
    val notes: String,
    val publishedAt: String,
    val url: String,
    val releaseUrl: String,
)

internal object UpdateChecker {
    fun checkForUpdate(
        installedVersion: String,
        lastNotifiedVersion: String,
        fetchRelease: () -> String = ::fetchLatestRelease,
    ): UpdateInfo? {
        val response = try {
            fetchRelease()
        } catch (error: IOException) {
            if (error is ReleaseHttpException && error.statusCode == 403 && error.rateLimitExhausted) {
                updateLogger.info("GitHub API rate limit reached; update check deferred.")
            } else if (error is ReleaseHttpException) {
                updateLogger.warning("GitHub update API returned HTTP ${error.statusCode}.")
            } else {
                updateLogger.warning("GitHub update check failed: ${error.javaClass.simpleName}.")
            }
            return null
        } catch (error: SecurityException) {
            updateLogger.warning("GitHub update check was blocked by platform security.")
            return null
        }

        return try {
            parseLatestRelease(response, installedVersion, lastNotifiedVersion)
        } catch (error: JSONException) {
            updateLogger.warning("GitHub returned an invalid release response.")
            null
        } catch (error: IllegalArgumentException) {
            updateLogger.warning("GitHub release metadata was invalid.")
            null
        }
    }

    internal fun parseLatestRelease(
        response: String,
        installedVersion: String,
        lastNotifiedVersion: String = "",
    ): UpdateInfo? {
        val release = JSONObject(response)
        if (release.optBoolean("draft", true) || release.optBoolean("prerelease", true)) return null

        val rawTag = release.optString("tag_name", "")
        val latestVersion = parseSemanticVersion(rawTag) ?: return null
        if (latestVersion.isPrerelease) return null
        val currentVersion = parseSemanticVersion(installedVersion) ?: return null
        if (latestVersion <= currentVersion) return null

        val version = rawTag.removePrefix("v").removePrefix("V")
        val lastNotified = parseSemanticVersion(lastNotifiedVersion)
        if (lastNotified != null && latestVersion <= lastNotified) return null
        val releaseUrl = trustedReleasePage(release.optString("html_url", ""))
        val notes = release.optString("body", "").trim().take(500)
        val publishedAt = release.optString("published_at", "")
            .takeIf { Regex("^\\d{4}-\\d{2}-\\d{2}").containsMatchIn(it) }
            ?.take(10)
            .orEmpty()
        return UpdateInfo(
            version = version,
            notes = notes,
            publishedAt = publishedAt,
            url = androidDownloadUrl(release) ?: releaseUrl,
            releaseUrl = releaseUrl,
        )
    }

    internal fun parseSemanticVersion(value: String): SemanticVersion? {
        val match = SEMVER_REGEX.matchEntire(value) ?: return null
        val prerelease = match.groupValues[4].takeIf(String::isNotEmpty)?.split(".").orEmpty()
        if (prerelease.any { it.length > 1 && it.startsWith('0') && it.all(Char::isDigit) }) return null
        return try {
            SemanticVersion(
                major = BigInteger(match.groupValues[1]),
                minor = BigInteger(match.groupValues[2]),
                patch = BigInteger(match.groupValues[3]),
                prerelease = prerelease,
            )
        } catch (_: NumberFormatException) {
            null
        }
    }

    private fun fetchLatestRelease(): String {
        val connection = URL(GITHUB_API_URL).openConnection() as HttpURLConnection
        connection.connectTimeout = 8_000
        connection.readTimeout = 8_000
        connection.requestMethod = "GET"
        connection.instanceFollowRedirects = false
        connection.setRequestProperty("Accept", "application/vnd.github+json")
        connection.setRequestProperty("User-Agent", "LinkToLinux")
        connection.setRequestProperty("X-GitHub-Api-Version", "2022-11-28")
        try {
            val statusCode = connection.responseCode
            if (statusCode != HttpURLConnection.HTTP_OK) {
                throw ReleaseHttpException(
                    statusCode,
                    connection.getHeaderField("X-RateLimit-Remaining") == "0",
                )
            }
            if (connection.contentLengthLong > MAX_RELEASE_RESPONSE_BYTES) {
                throw IOException("Release response exceeded the size limit.")
            }
            return connection.inputStream.use(::readLimited)
        } finally {
            connection.disconnect()
        }
    }

    private fun readLimited(input: java.io.InputStream): String {
        val output = ByteArrayOutputStream()
        val buffer = ByteArray(8_192)
        while (true) {
            val read = input.read(buffer)
            if (read < 0) break
            if (output.size() + read > MAX_RELEASE_RESPONSE_BYTES) {
                throw IOException("Release response exceeded the size limit.")
            }
            output.write(buffer, 0, read)
        }
        return output.toByteArray().toString(Charsets.UTF_8)
    }

    private fun androidDownloadUrl(release: JSONObject): String? {
        val assets = release.optJSONArray("assets") ?: return null
        for (index in 0 until assets.length()) {
            val asset = assets.optJSONObject(index) ?: continue
            if (!asset.optString("name").equals("LinkToLinux-Android.apk", ignoreCase = true)) continue
            val url = trustedAssetUrl(asset.optString("browser_download_url"))
            if (url != null) return url
        }
        return null
    }

    private fun trustedReleasePage(value: String): String {
        val uri = runCatching { URI(value) }.getOrNull()
        if (
            uri?.scheme == "https"
            && uri.host == "github.com"
            && uri.rawUserInfo == null
            && uri.port in listOf(-1, 443)
            && uri.path.orEmpty().startsWith("/$GITHUB_REPO/releases/")
        ) return value
        return GITHUB_RELEASES_URL
    }

    private fun trustedAssetUrl(value: String): String? {
        val uri = runCatching { URI(value) }.getOrNull()
        return value.takeIf {
            uri?.scheme == "https"
                && uri.host == "github.com"
                && uri.rawUserInfo == null
                && uri.port in listOf(-1, 443)
                && uri.path.orEmpty().startsWith("/$GITHUB_REPO/releases/download/")
        }
    }

    private val SEMVER_REGEX = Regex(
        "^v?(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)" +
            "(?:-([0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*))?" +
            "(?:\\+[0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*)?$",
    )
}

internal class SemanticVersion(
    private val major: BigInteger,
    private val minor: BigInteger,
    private val patch: BigInteger,
    private val prerelease: List<String>,
) : Comparable<SemanticVersion> {
    val isPrerelease: Boolean get() = prerelease.isNotEmpty()

    override fun compareTo(other: SemanticVersion): Int {
        compareValuesBy(this, other, SemanticVersion::major, SemanticVersion::minor, SemanticVersion::patch)
            .takeIf { it != 0 }
            ?.let { return it }
        if (prerelease.isEmpty() || other.prerelease.isEmpty()) {
            return when {
                prerelease.isEmpty() && other.prerelease.isEmpty() -> 0
                prerelease.isEmpty() -> 1
                else -> -1
            }
        }
        for (index in 0 until minOf(prerelease.size, other.prerelease.size)) {
            val left = prerelease[index]
            val right = other.prerelease[index]
            val leftNumber = left.toBigIntegerOrNull()
            val rightNumber = right.toBigIntegerOrNull()
            val comparison = when {
                leftNumber != null && rightNumber != null -> leftNumber.compareTo(rightNumber)
                leftNumber != null -> -1
                rightNumber != null -> 1
                else -> left.compareTo(right)
            }
            if (comparison != 0) return comparison
        }
        return prerelease.size.compareTo(other.prerelease.size)
    }
}

internal class ReleaseHttpException(
    val statusCode: Int,
    val rateLimitExhausted: Boolean,
) : IOException()
