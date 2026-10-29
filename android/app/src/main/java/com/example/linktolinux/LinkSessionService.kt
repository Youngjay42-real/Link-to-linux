package com.example.linktolinux

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.Context
import android.content.pm.ServiceInfo
import android.media.Ringtone
import android.media.RingtoneManager
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.util.Log

class LinkSessionService : Service() {
    private var worker: Thread? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private var phoneRingtone: Ringtone? = null
    private var phoneRinging = false
    private var mediaCommandAck = ""
    private var lastMediaCommandId = ""
    private var lastMediaCommandAction = ""
    private var lastMediaCommandTime = 0L

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            ActiveLink.session?.close()
            ActiveLink.session = null
            stopSelf()
            return START_NOT_STICKY
        }
        val session = ActiveLink.session
        if (session == null) {
            stopSelf()
            return START_NOT_STICKY
        }
        ensureNotificationChannel()
        val notification = buildNotification()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
        acquireWakeLock()
        if (worker?.isAlive != true) {
            worker = Thread({ keepSessionAlive() }, "linktolinux-live-session").apply {
                isDaemon = true
                start()
            }
        }
        return START_STICKY
    }

    private fun keepSessionAlive() {
        while (!Thread.currentThread().isInterrupted) {
            val session = ActiveLink.session ?: break
            try {
                val prefs = getSharedPreferences("link_to_linux_pairing", Context.MODE_PRIVATE)
                val status = session.sendStatus(this, prefs.getBoolean("clipboard_sync", false), phoneRinging, mediaCommandAck)
                mediaCommandAck = ""
                status.optJSONObject("media_command")?.let { command ->
                    val commandId = command.optString("id")
                    val commandAction = command.optString("action")
                    val now = System.currentTimeMillis()

                    // Check if this is a new command (not a duplicate)
                    val isNewCommand = commandId.isNotBlank() && (commandId != lastMediaCommandId || now - lastMediaCommandTime > 5000)

                    if (isNewCommand) {
                        Log.d("LinkToLinux", "Received media command: $commandAction (id=$commandId)")
                        lastMediaCommandId = commandId
                        lastMediaCommandAction = commandAction
                        lastMediaCommandTime = now
                        PhoneMediaSessions.control(this, commandAction)
                        mediaCommandAck = commandId
                    } else if (commandId.isNotBlank() && commandId == lastMediaCommandId) {
                        // Duplicate command, just ack it
                        Log.d("LinkToLinux", "Duplicate media command ignored: $commandAction (id=$commandId)")
                        mediaCommandAck = commandId
                    }
                }
                runCatching { updatePhoneRinging(status.optBoolean("ring_phone")) }
                if (status.optBoolean("photos_requested")) {
                    runCatching { session.sendPhonePhotos(this) }
                }
                val requestedPhotoId = status.optString("photo_download_id")
                if (requestedPhotoId.isNotBlank()) {
                    runCatching {
                        val mode = status.optString("photo_download_mode", "save")
                        val name = session.sendPhonePhoto(this, requestedPhotoId, mode)
                        if (mode != "view") postTransferNotification(this, "Desktop received $name", "The selected phone photo was saved on your Linux desktop.")
                    }
                }
                status.optJSONObject("desktop_status")?.let { desktopStatus ->
                    val update = Intent(ACTION_STATUS_UPDATED)
                        .putExtra(EXTRA_DESKTOP_STATUS, desktopStatus.toString())
                        .setPackage(packageName)
                    status.optJSONObject("file_offer")?.let { update.putExtra(EXTRA_FILE_OFFER, it.toString()) }
                    sendBroadcast(update)
                }
                updateNotification()
            } catch (e: Exception) {
                Log.e("LinkToLinux", "Session error: ${e.message}", e)
                val wasCurrent = ActiveLink.session === session
                if (wasCurrent) ActiveLink.session = null
                session.close()
                if (wasCurrent) {
                    sendBroadcast(Intent(ACTION_CONNECTION_LOST).setPackage(packageName))
                    stopSelf()
                }
                return
            }
            try {
                // Keep photo browsing and desktop file requests responsive without a long polling wait.
                Thread.sleep(2_000)
            } catch (_: InterruptedException) {
                Thread.currentThread().interrupt()
            }
        }
        stopSelf()
    }

    private fun ensureNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(CHANNEL_ID, "Desktop connection", NotificationManager.IMPORTANCE_LOW)
            channel.description = "Shows when Link to Linux is maintaining a secure desktop connection."
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }

    private fun buildNotification(): Notification {
        val openApp = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        return Notification.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setContentTitle("Link to Linux connected")
            .setContentText(ActiveLink.pendingOffers().firstOrNull()?.let { "${it.filename} is ready to receive" } ?: "Keeping your paired desktop link available")
            .setContentIntent(openApp)
            .setOngoing(true)
            .setCategory(Notification.CATEGORY_SERVICE)
            .build()
    }

    private fun updateNotification() {
        getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, buildNotification())
    }

    private fun updatePhoneRinging(shouldRing: Boolean) {
        if (!shouldRing) {
            runCatching { phoneRingtone?.stop() }
            phoneRingtone = null
            phoneRinging = false
            return
        }
        if (phoneRinging && phoneRingtone?.isPlaying == true) return

        val ringtoneUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE)
            ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
            ?: return
        val ringtone = RingtoneManager.getRingtone(this, ringtoneUri) ?: return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) ringtone.isLooping = true
        runCatching { ringtone.play() }
            .onSuccess {
                phoneRingtone = ringtone
                phoneRinging = true
            }
            .onFailure {
                phoneRingtone = null
                phoneRinging = false
            }
    }

    private fun acquireWakeLock() {
        if (wakeLock?.isHeld == true) return
        wakeLock = (getSystemService(POWER_SERVICE) as PowerManager)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "LinkToLinux:session")
            .apply { setReferenceCounted(false); acquire() }
    }

    override fun onDestroy() {
        worker?.interrupt()
        worker = null
        runCatching { phoneRingtone?.stop() }
        phoneRingtone = null
        phoneRinging = false
        wakeLock?.let { if (it.isHeld) it.release() }
        wakeLock = null
        super.onDestroy()
    }

    companion object {
        const val ACTION_START = "com.example.linktolinux.START_SESSION"
        const val ACTION_STOP = "com.example.linktolinux.STOP_SESSION"
        const val ACTION_CONNECTION_LOST = "com.example.linktolinux.CONNECTION_LOST"
        const val ACTION_STATUS_UPDATED = "com.example.linktolinux.STATUS_UPDATED"
        const val EXTRA_DESKTOP_STATUS = "desktop_status"
        const val EXTRA_FILE_OFFER = "file_offer"
        private const val CHANNEL_ID = "link_session"
        private const val NOTIFICATION_ID = 44888
    }
}
