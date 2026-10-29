package com.example.linktolinux

import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.content.Context
import android.content.ComponentName
import android.media.MediaMetadata
import android.media.session.MediaController
import android.media.session.PlaybackState
import android.media.session.MediaSessionManager
import android.app.NotificationManager
import org.json.JSONObject
import java.util.concurrent.ConcurrentHashMap
import android.util.Log

class PhoneNotificationListener : NotificationListenerService() {
    private val lastContent = ConcurrentHashMap<String, String>()
    private var sessionsListener: MediaSessionManager.OnActiveSessionsChangedListener? = null

    override fun onListenerConnected() {
        super.onListenerConnected()
        val manager = getSystemService(Context.MEDIA_SESSION_SERVICE) as MediaSessionManager
        val component = ComponentName(this, PhoneNotificationListener::class.java)
        val listenerCallback = MediaSessionManager.OnActiveSessionsChangedListener { sessions ->
            PhoneMediaSessions.update(sessions.orEmpty())
        }
        sessionsListener = listenerCallback
        runCatching { manager.addOnActiveSessionsChangedListener(listenerCallback, component) }
        runCatching { PhoneMediaSessions.update(manager.getActiveSessions(component)) }
    }

    override fun onListenerDisconnected() {
        val manager = getSystemService(Context.MEDIA_SESSION_SERVICE) as MediaSessionManager
        sessionsListener?.let { listener -> runCatching { manager.removeOnActiveSessionsChangedListener(listener) } }
        sessionsListener = null
        PhoneMediaSessions.update(emptyList())
        super.onListenerDisconnected()
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        if (sbn.packageName == packageName || sbn.isOngoing) return
        val preferences = getSharedPreferences("link_to_linux_pairing", Context.MODE_PRIVATE)
        if (!preferences.getBoolean("notification_sync", false)) return

        val extras = sbn.notification.extras ?: return
        val title = extras.getCharSequence("android.title")?.toString()?.trim().orEmpty()
        val body = (extras.getCharSequence("android.bigText") ?: extras.getCharSequence("android.text"))
            ?.toString()?.trim().orEmpty()
        if (title.isBlank() && body.isBlank()) return
        val appName = runCatching {
            packageManager.getApplicationLabel(packageManager.getApplicationInfo(sbn.packageName, 0)).toString()
        }.getOrDefault(sbn.packageName)
        val key = "${sbn.packageName}:${sbn.id}:${sbn.tag.orEmpty()}"
        val content = "$title|$body"
        if (lastContent.put(key, content) == content) return

        val session = ActiveLink.session ?: return
        Thread({ runCatching { session.sendPhoneNotification(appName, title.ifBlank { appName }, body) } }, "linktolinux-notification").apply {
            isDaemon = true
            start()
        }
    }

    override fun onNotificationRemoved(sbn: StatusBarNotification) {
        lastContent.remove("${sbn.packageName}:${sbn.id}:${sbn.tag.orEmpty()}")
    }
}

internal object PhoneMediaSessions {
    @Volatile private var knownSessions: List<MediaController> = emptyList()

    fun update(sessions: List<MediaController>) {
        val oldSessions = knownSessions
        knownSessions = sessions

        // Log session changes for debugging
        if (oldSessions != sessions) {
            Log.d("LinkToLinux", "Media sessions updated: count=${sessions.size}")
            for (s in sessions) {
                val pkg = s.packageName
                val state = s.playbackState?.state?.let { stateToString(it) } ?: "null"
                val title = s.metadata?.getString(MediaMetadata.METADATA_KEY_TITLE) ?: "no title"
                Log.d("LinkToLinux", "  Session: pkg=$pkg state=$state title=$title")
            }
        }
    }

    private fun sessions(context: Context): List<MediaController> = runCatching {
        val manager = context.getSystemService(Context.MEDIA_SESSION_SERVICE) as MediaSessionManager
        val listener = ComponentName(context, PhoneNotificationListener::class.java)
        manager.getActiveSessions(listener).also(::update)
    }.getOrDefault(knownSessions)

    fun activeController(context: Context): MediaController? = sessions(context)
        .filter { controller ->
            val state = controller.playbackState?.state ?: PlaybackState.STATE_NONE
            // Filter out sessions that are not playable (STOPPED, NONE)
            state != PlaybackState.STATE_STOPPED
                && state != PlaybackState.STATE_NONE
        }
        // Prefer Spotify controllers when available and active, but don't hardcode
        .sortedWith(
            compareByDescending<MediaController> { it ->
                // First priority: PLAYING state
                when (it.playbackState?.state) {
                    PlaybackState.STATE_PLAYING -> 3
                    PlaybackState.STATE_BUFFERING -> 2
                    PlaybackState.STATE_PAUSED -> 1
                    else -> 0
                }
            }
            .thenByDescending { it.packageName == "com.spotify.music" || it.packageName == "com.spotify.music.test" }
            .thenByDescending { it.playbackState?.lastPositionUpdateTime ?: 0L }
        )
        .firstOrNull()

    fun status(context: Context) = JSONObject().apply {
        val listenerComponent = ComponentName(context, PhoneNotificationListener::class.java)
        val access = runCatching {
            context.getSystemService(NotificationManager::class.java)
                .isNotificationListenerAccessGranted(listenerComponent)
        }.getOrDefault(false)
        put("access_granted", access)
        put("available", false)
        if (!access) return@apply
        try {
            val controller = activeController(context) ?: return@apply
            val metadata = controller.metadata
            val state = controller.playbackState?.state
            put("available", true)
            put("title", metadata?.getString(MediaMetadata.METADATA_KEY_TITLE).orEmpty().take(256))
            put("artist", metadata?.getString(MediaMetadata.METADATA_KEY_ARTIST).orEmpty().take(256))
            put("playing", state == PlaybackState.STATE_PLAYING)
            put("package", controller.packageName.take(128))
            val actions = controller.playbackState?.actions ?: 0L
            put("can_play_pause", actions.and(PlaybackState.ACTION_PLAY or PlaybackState.ACTION_PAUSE or PlaybackState.ACTION_PLAY_PAUSE) != 0L)
            put("can_previous", actions.and(PlaybackState.ACTION_SKIP_TO_PREVIOUS) != 0L)
            put("can_next", actions.and(PlaybackState.ACTION_SKIP_TO_NEXT) != 0L)
        } catch (error: SecurityException) {
            put("access_granted", false)
            put("error", "notification_access_required")
        } catch (_: Exception) {
            put("error", "media_session_unavailable")
        }
    }

    fun control(context: Context, action: String): Boolean {
        val controller = activeController(context) ?: return false
        val pkg = controller.packageName
        val state = controller.playbackState?.state?.let { stateToString(it) } ?: "unknown"
        Log.d("LinkToLinux", "Executing media action: $action on $pkg (state=$state)")
        val controls = controller.transportControls
        return runCatching {
            when (action) {
                "play_pause" -> if (controller.playbackState?.state == PlaybackState.STATE_PLAYING) controls.pause() else controls.play()
                "next" -> controls.skipToNext()
                "previous" -> controls.skipToPrevious()
                else -> return false
            }
            true
        }.getOrDefault(false)
    }

    private fun stateToString(state: Int): String {
        return when (state) {
            PlaybackState.STATE_NONE -> "NONE"
            PlaybackState.STATE_STOPPED -> "STOPPED"
            PlaybackState.STATE_PAUSED -> "PAUSED"
            PlaybackState.STATE_PLAYING -> "PLAYING"
            PlaybackState.STATE_BUFFERING -> "BUFFERING"
            PlaybackState.STATE_FAST_FORWARDING -> "FAST_FORWARDING"
            PlaybackState.STATE_REWINDING -> "REWINDING"
            PlaybackState.STATE_SKIPPING_TO_NEXT -> "SKIPPING_TO_NEXT"
            PlaybackState.STATE_SKIPPING_TO_PREVIOUS -> "SKIPPING_TO_PREVIOUS"
            11 -> "SEEKING" // PlaybackState.STATE_SEEKING (API 29+)
            else -> "UNKNOWN($state)"
        }
    }
}
