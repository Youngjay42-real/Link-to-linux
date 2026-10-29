package com.example.linktolinux

import android.app.Activity
import android.app.NotificationManager
import android.Manifest
import android.content.Context
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.ContentResolver
import android.content.BroadcastReceiver
import android.content.ClipboardManager
import android.content.ClipData
import android.content.ContentUris
import android.content.ComponentName
import android.net.Uri
import android.database.Cursor
import android.provider.OpenableColumns
import android.os.BatteryManager
import android.os.PowerManager
import android.provider.Settings
import android.provider.MediaStore
import android.util.Size
import android.util.Log
import android.os.Environment
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.IconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationDrawerItem
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.painterResource
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Settings
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.core.view.WindowCompat
import com.example.linktolinux.ui.theme.LinkToLinuxTheme
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.withContext
import kotlinx.coroutines.channels.Channel
import org.json.JSONObject
import java.io.BufferedReader
import java.io.ByteArrayOutputStream
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.ConnectException
import java.net.InetSocketAddress
import java.net.Socket
import java.net.SocketTimeoutException
import java.security.MessageDigest
import java.security.SecureRandom
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import java.util.UUID
import javax.net.ssl.SSLContext
import javax.net.ssl.SSLSocket
import javax.net.ssl.X509TrustManager
import com.example.linktolinux.BuildConfig

private const val PREFS_NAME = "link_to_linux_pairing"
private const val UPDATE_CHECK_INTERVAL_HOURS = 24
private const val PREF_LAST_NOTIFIED_VERSION = "last_notified_update_version"

private data class FileTransferProgress(
    val filename: String,
    val direction: String,
    val transferredBytes: Long,
    val totalBytes: Long,
)

private fun hasNotificationListenerAccess(context: Context): Boolean = runCatching {
    context.getSystemService(NotificationManager::class.java)
        .isNotificationListenerAccessGranted(ComponentName(context, PhoneNotificationListener::class.java))
}.getOrDefault(false)

private fun parsePairingQr(raw: String?): JSONObject? {
    if (raw.isNullOrBlank()) return null
    val payload = runCatching { JSONObject(raw) }.getOrNull() ?: runCatching {
        val uri = Uri.parse(raw)
        if (uri.scheme != "linktolinux" || uri.host != "pair") return null
        JSONObject().put("kind", "linktolinux.pair")
            .put("version", uri.getQueryParameter("version")?.toIntOrNull() ?: 0)
            .put("host", uri.getQueryParameter("host"))
            .put("port", uri.getQueryParameter("port")?.toIntOrNull() ?: 44888)
            .put("code", uri.getQueryParameter("code"))
            .put("fingerprint", uri.getQueryParameter("fingerprint"))
    }.getOrNull()
    return payload?.takeIf {
        it.optString("kind") == "linktolinux.pair" && it.optInt("version") == 1 &&
            it.optString("host").isNotBlank() && it.optString("code").length == 6 &&
            it.optString("fingerprint").replace(":", "").length == 64
    }
}

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val preferences = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        setContent {
            var darkMode by remember { mutableStateOf(preferences.getBoolean("dark_mode", false)) }
            LinkToLinuxTheme(darkTheme = darkMode) {
                val controller = WindowCompat.getInsetsController(window, window.decorView)
                controller.isAppearanceLightStatusBars = !darkMode
                controller.isAppearanceLightNavigationBars = !darkMode
                Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    LinkToLinuxApp(
                        darkMode = darkMode,
                        pairingLink = intent?.dataString,
                        onDarkModeChanged = {
                            darkMode = it
                            preferences.edit().putBoolean("dark_mode", it).apply()
                        },
                    )
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LinkToLinuxApp(darkMode: Boolean, pairingLink: String?, onDarkModeChanged: (Boolean) -> Unit) {
    val context = LocalContext.current
    val preferences = remember { context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE) }
    val scope = rememberCoroutineScope()
    val remoteInputQueue = remember { Channel<RemoteInputCommand>(Channel.UNLIMITED) }
    val transferProgressState = remember { MutableStateFlow<FileTransferProgress?>(null) }
    val fileTransferProgress by transferProgressState.collectAsState()
    val notificationPermissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        requestBackgroundConnectionExemption(context)
    }
    val deviceId = remember {
        preferences.getString("device_id", null) ?: "android-${UUID.randomUUID()}".also {
            preferences.edit().putString("device_id", it).apply()
        }
    }
    var page by remember { mutableStateOf("Home") }
    var fullRemoteMode by remember { mutableStateOf(false) }
    var host by remember { mutableStateOf(preferences.getString("desktop_host", "") ?: "") }
    var port by remember { mutableStateOf(preferences.getString("desktop_port", "44888") ?: "44888") }
    var code by remember { mutableStateOf("") }
    var fingerprint by remember { mutableStateOf(preferences.getString("desktop_fingerprint", "") ?: "") }
    var desktopName by remember { mutableStateOf(preferences.getString("desktop_name", "") ?: "") }
    var liveSession by remember { mutableStateOf(ActiveLink.session) }
    var connected by remember { mutableStateOf(ActiveLink.session != null) }
    var desktopStatus by remember { mutableStateOf(ActiveLink.desktopStatus) }
    val desktopFileOffers = remember { mutableStateListOf<DesktopFileOffer>().apply { addAll(ActiveLink.pendingOffers()) } }
    var transferMessage by remember { mutableStateOf("") }
    var isPairing by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }
    var isError by remember { mutableStateOf(false) }
    LaunchedEffect(pairingLink) {
        parsePairingQr(pairingLink)?.let { payload ->
            host = payload.optString("host")
            port = payload.optInt("port", 44888).toString()
            code = payload.optString("code")
            fingerprint = payload.optString("fingerprint")
            page = "Devices"
            message = "Desktop details scanned. Check the desktop, then tap Pair securely."
            isError = false
        }
    }
    var notificationSync by remember { mutableStateOf(preferences.getBoolean("notification_sync", false)) }
    var notificationAccessGranted by remember { mutableStateOf(hasNotificationListenerAccess(context)) }
    var phonePhotoAccess by remember { mutableStateOf(hasPhonePhotoAccess(context)) }
    var clipboardSync by remember { mutableStateOf(preferences.getBoolean("clipboard_sync", false)) }
    var downloadFolder by remember { mutableStateOf(preferences.getString("download_folder", "Not selected") ?: "Not selected") }
    var updateInfo by remember { mutableStateOf<UpdateInfo?>(null) }
    var lastNotifiedUpdateVersion by remember {
        mutableStateOf(preferences.getString(PREF_LAST_NOTIFIED_VERSION, "").orEmpty())
    }
    val acknowledgeUpdate = {
        updateInfo?.let { info ->
            preferences.edit().putString(PREF_LAST_NOTIFIED_VERSION, info.version).apply()
            lastNotifiedUpdateVersion = info.version
        }
        updateInfo = null
    }
    val openUpdateDownload: () -> Unit = {
        updateInfo?.let { info ->
            try {
                context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(info.url)))
                acknowledgeUpdate()
            } catch (error: ActivityNotFoundException) {
                Log.w("LinkToLinuxUpdates", "No app is available to open the update link.")
                android.widget.Toast.makeText(context, "No browser is available to open the update.", android.widget.Toast.LENGTH_LONG).show()
            } catch (error: SecurityException) {
                Log.w("LinkToLinuxUpdates", "Platform security blocked the update link.")
                android.widget.Toast.makeText(context, "Android could not open the update link.", android.widget.Toast.LENGTH_LONG).show()
            }
        }
    }
    val photoAccessLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
        phonePhotoAccess = hasPhonePhotoAccess(context)
    }
    DisposableEffect(context) {
        val activity = context as? ComponentActivity
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                notificationAccessGranted = hasNotificationListenerAccess(context)
            }
        }
        activity?.lifecycle?.addObserver(observer)
        onDispose { activity?.lifecycle?.removeObserver(observer) }
    }
    BackHandler(enabled = page != "Home" || fullRemoteMode) {
        if (fullRemoteMode) fullRemoteMode = false else page = "Home"
    }
    LaunchedEffect(context) {
        while (isActive) {
            val availableUpdate = withContext(Dispatchers.IO) {
                UpdateChecker.checkForUpdate(
                    installedVersion = BuildConfig.VERSION_NAME,
                    lastNotifiedVersion = lastNotifiedUpdateVersion,
                )
            }
            if (availableUpdate != null) {
                lastNotifiedUpdateVersion = availableUpdate.version
                updateInfo = availableUpdate
            }
            delay(UPDATE_CHECK_INTERVAL_HOURS * 60 * 60 * 1000L)
        }
    }

    LaunchedEffect(liveSession) {
        val session = liveSession ?: return@LaunchedEffect
        for (command in remoteInputQueue) {
            val result = withContext(Dispatchers.IO) {
                runCatching {
                    session.sendRemoteInput(
                        command.action,
                        command.dx,
                        command.dy,
                        command.button,
                        command.text,
                        command.key,
                        command.repeat,
                    )
                }
            }
            result.onFailure {
                if (liveSession === session) transferMessage = "Remote input failed: ${it.message}"
            }
        }
    }

    LaunchedEffect(deviceId) {
        val savedToken = preferences.getString("desktop_reconnect_token", "").orEmpty()
        val savedHost = preferences.getString("desktop_host", "").orEmpty()
        val savedPort = preferences.getString("desktop_port", "44888")?.toIntOrNull() ?: 44888
        val savedFingerprint = preferences.getString("desktop_fingerprint", "").orEmpty()
        if (savedToken.isNotBlank() && savedHost.isNotBlank() && liveSession == null) {
            isPairing = true
            message = "Reconnecting to your saved desktop…"
            val result = withContext(Dispatchers.IO) {
                requestPairing(savedHost, savedPort, "", savedFingerprint, deviceId, context, savedToken)
            }
            isPairing = false
            result.onSuccess { session ->
                liveSession = session
                ActiveLink.session = session
                connected = true
                desktopName = session.desktopName
                desktopStatus = session.latestDesktopStatus
                ActiveLink.desktopStatus = desktopStatus
                context.startForegroundService(Intent(context, LinkSessionService::class.java).setAction(LinkSessionService.ACTION_START))
                message = "Reconnected to saved desktop: ${session.desktopName}."
            }.onFailure {
                message = "Could not reconnect to the saved desktop. Make sure Link to Linux is open on the desktop, then pair again if needed."
            }
        }
    }

    DisposableEffect(context) {
        val receiver = object : BroadcastReceiver() {
            override fun onReceive(receiverContext: Context?, intent: Intent?) {
                if (intent?.action == LinkSessionService.ACTION_CONNECTION_LOST) {
                    ActiveLink.session = null
                    liveSession = null
                    connected = false
                    transferMessage = "Desktop connection lost. Start a new pairing session to reconnect."
                } else if (intent?.action == LinkSessionService.ACTION_STATUS_UPDATED) {
                    intent.getStringExtra(LinkSessionService.EXTRA_DESKTOP_STATUS)?.let { raw ->
                        desktopStatus = runCatching { DesktopStatus.fromJson(JSONObject(raw)) }.getOrNull()
                        ActiveLink.desktopStatus = desktopStatus
                    }
                    intent.getStringExtra(LinkSessionService.EXTRA_FILE_OFFER)?.let { raw ->
                        runCatching { DesktopFileOffer.fromJson(JSONObject(raw)) }.getOrNull()?.let { offer ->
                            ActiveLink.addOffer(offer)
                            if (desktopFileOffers.none { it.transferId == offer.transferId }) desktopFileOffers.add(offer)
                        }
                    }
                }
            }
        }
        context.registerReceiver(receiver, android.content.IntentFilter().apply {
            addAction(LinkSessionService.ACTION_CONNECTION_LOST)
            addAction(LinkSessionService.ACTION_STATUS_UPDATED)
        }, Context.RECEIVER_NOT_EXPORTED)
        onDispose { runCatching { context.unregisterReceiver(receiver) } }
    }

    fun sendSelected(uri: Uri, category: String) {
        val session = liveSession
        if (session == null) { transferMessage = "Connect to the desktop before sending."; return }
        val filename = uri.lastPathSegment?.substringAfterLast('/')?.takeIf { it.isNotBlank() } ?: "Selected file"
        transferProgressState.value = FileTransferProgress(filename, "Sending", 0L, -1L)
        scope.launch {
            transferMessage = "Sending…"
            val result = withContext(Dispatchers.IO) {
                runCatching {
                    session.sendFile(context.contentResolver, uri, category) { sent, total ->
                        transferProgressState.value = FileTransferProgress(filename, "Sending", sent, total)
                    }
                }
            }
            transferProgressState.value = null
            transferMessage = result.fold({
                postTransferNotification(context, "Desktop received ${it}", "The file was verified and saved on your Linux desktop.")
                "Sent ${it}. Saved in the desktop Downloads folder."
            }, { "Transfer failed: ${it.message ?: "unknown error"}" })
        }
    }
    val filePicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> uri?.let { sendSelected(it, "file") } }
    val photoPicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> uri?.let { sendSelected(it, "photo") } }

    var selectedDesktopOffer by remember { mutableStateOf<DesktopFileOffer?>(null) }
    val desktopFilePicker = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("*/*")) { uri ->
        val offer = selectedDesktopOffer
        selectedDesktopOffer = null
        if (uri != null && offer != null) {
            val session = liveSession
            if (session == null) {
                transferMessage = "Desktop disconnected before the file could be received."
            } else {
                transferProgressState.value = FileTransferProgress(offer.filename, "Receiving", 0L, offer.sizeBytes)
                scope.launch {
                    transferMessage = "Receiving ${offer.filename}…"
                    val result = withContext(Dispatchers.IO) {
                        runCatching {
                            session.receiveFile(context.contentResolver, uri, offer) { received, total ->
                                transferProgressState.value = FileTransferProgress(offer.filename, "Receiving", received, total)
                            }
                        }
                    }
                    transferProgressState.value = null
                    result.fold(
                        onSuccess = {
                            desktopFileOffers.removeAll { it.transferId == offer.transferId }
                            ActiveLink.removeOffer(offer.transferId)
                            postTransferNotification(context, "Received ${offer.filename}", "The desktop file was verified and saved on this phone.")
                            transferMessage = "Received ${offer.filename}."
                        },
                        onFailure = { error -> transferMessage = "Receive failed: ${error.message ?: "unknown error"}" },
                    )
                }
            }
        }
    }

    val folderPicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocumentTree()) { uri ->
        if (uri != null) {
            runCatching {
                context.contentResolver.takePersistableUriPermission(
                    uri,
                    Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION,
                )
            }
            downloadFolder = uri.toString()
            preferences.edit().putString("download_folder", downloadFolder).apply()
        }
    }

    val drawerState = rememberDrawerState(DrawerValue.Closed)
    val destinations = listOf("Home", "Devices", "Remote", "Files", "Photos", "Notifications", "Clipboard", "Settings", "About")
    val navigation = listOf("Home", "Devices", "Remote", "Files")
    val fullRemoteModeActive = page == "Remote" && fullRemoteMode
    ModalNavigationDrawer(
        drawerState = drawerState,
        gesturesEnabled = !fullRemoteModeActive,
        drawerContent = {
            ModalDrawerSheet {
                Row(
                    modifier = Modifier.padding(horizontal = 24.dp, vertical = 20.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Surface(color = Color(0xFF3584E4), shape = MaterialTheme.shapes.small) {
                        Image(
                            painter = painterResource(R.drawable.ic_launcher_foreground),
                            contentDescription = null,
                            modifier = Modifier.size(38.dp).padding(3.dp),
                        )
                    }
                    Text("LINK TO LINUX", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                }
                destinations.forEach { destination ->
                    NavigationDrawerItem(
                        label = { Text(destination) },
                        selected = page == destination,
                        onClick = {
                            page = destination
                            scope.launch { drawerState.close() }
                        },
                        modifier = Modifier.padding(horizontal = 12.dp),
                        icon = { DestinationIcon(destination) },
                    )
                }
            }
        },
    ) {
    Scaffold(
        topBar = {
            if (!fullRemoteModeActive) {
                TopAppBar(
                    title = { Text(if (page == "Devices") "Devices & pairing" else page) },
                    navigationIcon = {
                        IconButton(onClick = { scope.launch { drawerState.open() } }) {
                            Icon(Icons.Filled.Menu, contentDescription = "Open navigation")
                        }
                    },
                )
            }
        },
        bottomBar = {
            if (!fullRemoteModeActive) {
                NavigationBar {
                    navigation.forEach { destination ->
                        NavigationBarItem(
                            selected = page == destination,
                            onClick = { page = destination },
                            icon = { DestinationIcon(destination) },
                            label = { Text(destination) },
                        )
                    }
                }
            }
        },
    ) { insets ->
        Column(
            modifier = Modifier.fillMaxSize()
                .then(if (fullRemoteModeActive) Modifier else Modifier.verticalScroll(rememberScrollState()))
                .padding(insets)
                .padding(if (fullRemoteModeActive) 8.dp else 18.dp),
            verticalArrangement = Arrangement.spacedBy(if (fullRemoteModeActive) 8.dp else 14.dp),
        ) {
            when (page) {
                "Home" -> HomePage(
                    desktopName = desktopName,
                    connected = connected,
                    transferMessage = transferMessage,
                    desktopStatus = desktopStatus,
                    updateInfo = updateInfo,
                    onDismissUpdate = acknowledgeUpdate,
                    onDownloadUpdate = openUpdateDownload,
                    onPair = { page = "Devices" },
                    onNavigate = { page = it }
                )
                "Devices" -> PairingPage(
                    host = host, onHostChange = { host = it },
                    port = port, onPortChange = { port = it },
                    code = code, onCodeChange = { code = it },
                    fingerprint = fingerprint, onFingerprintChange = { fingerprint = it },
                    desktopName = desktopName, isPairing = isPairing,
                    message = message, isError = isError,
                    onForget = {
                        liveSession?.close()
                        ActiveLink.session = null
                        ActiveLink.desktopStatus = null
                        ActiveLink.pendingOffers().forEach { ActiveLink.removeOffer(it.transferId) }
                        desktopStatus = null
                        desktopFileOffers.clear()
                        context.stopService(Intent(context, LinkSessionService::class.java))
                        liveSession = null
                        connected = false
                        preferences.edit().remove("desktop_host").remove("desktop_port")
                            .remove("desktop_fingerprint").remove("desktop_name")
                            .remove("desktop_reconnect_token").apply()
                        host = ""
                        port = "44888"
                        code = ""
                        fingerprint = ""
                        desktopName = ""
                        message = "Saved desktop details removed from this phone. Revoke this phone in the desktop app too."
                        isError = false
                    },
                    onReconnect = {
                        val savedToken = preferences.getString("desktop_reconnect_token", "").orEmpty()
                        scope.launch {
                            isPairing = true
                            message = "Reconnecting to saved desktop…"
                            val result = withContext(Dispatchers.IO) {
                                requestPairing(host, port.toIntOrNull() ?: 44888, "", fingerprint, deviceId, context, savedToken)
                            }
                            isPairing = false
                            result.onSuccess { session ->
                                liveSession = session
                                ActiveLink.session = session
                                connected = true
                                desktopName = session.desktopName
                                desktopStatus = session.latestDesktopStatus
                                ActiveLink.desktopStatus = desktopStatus
                                context.startForegroundService(Intent(context, LinkSessionService::class.java).setAction(LinkSessionService.ACTION_START))
                                message = "Reconnected to ${session.desktopName}."
                                isError = false
                            }.onFailure { error ->
                                message = error.message ?: "Could not reconnect. Make sure the desktop app is open."
                                isError = true
                            }
                        }
                    },
                    onScan = {
                        val activity = context as? Activity
                        if (activity == null) {
                            message = "Could not open the scanner. Enter the desktop details manually."
                            isError = true
                        } else {
                            val options = GmsBarcodeScannerOptions.Builder()
                                .setBarcodeFormats(Barcode.FORMAT_QR_CODE).build()
                            GmsBarcodeScanning.getClient(activity, options).startScan()
                                .addOnSuccessListener { barcode ->
                                    val payload = parsePairingQr(barcode.rawValue)
                                    if (payload == null) {
                                        message = "That QR code is not a Link to Linux pairing code."
                                        isError = true
                                    } else {
                                        host = payload.optString("host")
                                        port = payload.optInt("port", 44888).toString()
                                        code = payload.optString("code")
                                        fingerprint = payload.optString("fingerprint")
                                        message = "Desktop details scanned. Check the desktop, then tap Pair securely."
                                        isError = false
                                    }
                                }
                                .addOnFailureListener { error ->
                                    message = error.localizedMessage ?: "QR scanning failed. Enter the details manually."
                                    isError = true
                                }
                        }
                    },
                    onPair = {
                        isPairing = true
                        message = "Connecting securely…"
                        isError = false
                        val pairingHost = host.trim()
                        val pairingPort = port.toIntOrNull() ?: 0
                        val pairingCode = code.trim()
                        val expectedFingerprint = fingerprint
                        scope.launch {
                            val result = withContext(Dispatchers.IO) {
                                requestPairing(pairingHost, pairingPort, pairingCode, expectedFingerprint, deviceId, context)
                            }
                            isPairing = false
                            result.fold(
                                onSuccess = { session ->
                                    liveSession?.close()
                                    liveSession = session
                                    ActiveLink.session = session
                                    connected = true
                                    desktopStatus = session.latestDesktopStatus
                                    ActiveLink.desktopStatus = desktopStatus
                                    context.startForegroundService(Intent(context, LinkSessionService::class.java).setAction(LinkSessionService.ACTION_START))
                                    if (Build.VERSION.SDK_INT >= 33 && context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != android.content.pm.PackageManager.PERMISSION_GRANTED) {
                                        notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                                    } else {
                                        requestBackgroundConnectionExemption(context)
                                    }
                                    val pairedDesktop = session.desktopName
                                    desktopName = pairedDesktop
                                    message = "Connected to $pairedDesktop. Phone status sync is active."
                                    isError = false
                                    preferences.edit()
                                        .putString("desktop_host", pairingHost)
                                        .putString("desktop_port", pairingPort.toString())
                                        .putString("desktop_fingerprint", expectedFingerprint)
                                        .putString("desktop_name", pairedDesktop)
                                        .putString("desktop_reconnect_token", session.reconnectToken)
                                        .apply()
                                },
                                onFailure = { error ->
                                    message = pairingErrorMessage(error, pairingHost, pairingPort)
                                    isError = true
                                },
                            )
                        }
                    },
                )
                "Files" -> FilesPage(
                    desktopName, transferMessage, connected,
                    { filePicker.launch(arrayOf("*/*")) },
                    transferProgress = fileTransferProgress,
                    offers = desktopFileOffers.toList(),
                    onReceiveOffer = { offer -> selectedDesktopOffer = offer; desktopFilePicker.launch(offer.filename) },
                )
                "Remote" -> RemoteInputPage(
                    connected = connected,
                    available = desktopStatus?.remoteInputAvailable == true,
                    enabled = desktopStatus?.remoteInputEnabled == true,
                    statusMessage = transferMessage,
                    fullScreen = fullRemoteModeActive,
                    onToggleFullScreen = { fullRemoteMode = !fullRemoteMode },
                    onInput = { action, dx, dy, button, text, key, repeat ->
                        if (liveSession == null) {
                            transferMessage = "Connect to the paired desktop to use remote input."
                        } else {
                            remoteInputQueue.trySend(RemoteInputCommand(action, dx, dy, button, text, key, repeat))
                        }
                    },
                )
                "Photos" -> FilesPage(
                    desktopName, transferMessage, connected,
                    { photoPicker.launch(arrayOf("image/*")) }, photos = true,
                    transferProgress = fileTransferProgress,
                    phonePhotoAccess = phonePhotoAccess,
                    onGrantPhonePhotoAccess = {
                        val permissions = if (Build.VERSION.SDK_INT >= 34) {
                            arrayOf(Manifest.permission.READ_MEDIA_IMAGES, Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED)
                        } else arrayOf(Manifest.permission.READ_MEDIA_IMAGES)
                        photoAccessLauncher.launch(permissions)
                    },
                    offers = desktopFileOffers.filter { it.category == "photo" },
                    onReceiveOffer = { offer -> selectedDesktopOffer = offer; desktopFilePicker.launch(offer.filename) },
                )
                "Notifications" -> Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    ToggleFeaturePage(
                        title = "Notifications",
                        description = "Forward notification app names, titles, and text to your paired Linux desktop.",
                        label = "Share phone notifications",
                        enabled = notificationSync,
                        stateDescription = if (notificationAccessGranted) {
                            "Android notification access is granted. Sync works while sharing is enabled and the paired connection is active; Link to Linux notifications are excluded."
                        } else {
                            "Android notification access is not granted yet. Turn on sharing here, then allow Link to Linux in Android's Notification access settings."
                        },
                        onChanged = {
                            notificationSync = it
                            preferences.edit().putBoolean("notification_sync", it).apply()
                            if (it && !hasNotificationListenerAccess(context)) {
                                runCatching { context.startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)) }
                            }
                        },
                        actionLabel = "Open notification access settings",
                        onAction = { runCatching { context.startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)) } },
                    )
                    if (!notificationAccessGranted) SectionCard(
                        "If Android says ‘App was denied access’",
                        "Close that message. Open Link to Linux app info, tap ⋮ in the top corner, then choose Allow restricted settings. Return to Special app access → Notification access and enable Link to Linux. Android requires this extra step for some sideloaded apps; Link to Linux cannot approve it automatically."
                    )
                    OutlinedButton(onClick = {
                        runCatching { context.startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:${context.packageName}"))) }
                    }, modifier = Modifier.fillMaxWidth(), enabled = !notificationAccessGranted) { Text("Open app info to allow restricted settings") }
                }
                "Clipboard" -> ClipboardPage(
                    enabled = clipboardSync,
                    connected = connected,
                    transferMessage = transferMessage,
                    onEnabledChanged = {
                        clipboardSync = it
                        preferences.edit().putBoolean("clipboard_sync", it).apply()
                        val session = liveSession
                        if (session != null) scope.launch {
                            withContext(Dispatchers.IO) { runCatching { session.setClipboardEnabled(it) } }
                        }
                    },
                    onSendClipboard = {
                        val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                        val text = runCatching { clipboard.primaryClip?.getItemAt(0)?.coerceToText(context)?.toString() }.getOrNull()
                        val session = liveSession
                        if (text.isNullOrEmpty()) {
                            transferMessage = "Copy some text first, then tap Send copied text."
                        } else if (session == null || !clipboardSync) {
                            transferMessage = "Connect to a desktop and enable clipboard sharing on both devices."
                        } else {
                            scope.launch {
                                val result = withContext(Dispatchers.IO) { runCatching { session.sendClipboard(text) } }
                                transferMessage = result.fold({ "Copied text sent to the desktop." }, { "Clipboard send failed: ${it.message}" })
                            }
                        }
                    },
                )
                "Settings" -> SettingsPage(
                    darkMode = darkMode,
                    onDarkModeChanged = onDarkModeChanged,
                    downloadFolder = downloadFolder,
                    onChooseFolder = { folderPicker.launch(null) },
                )
                "About" -> AboutPage { url ->
                    runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) }
                }
                else -> HomePage(
                    desktopName = desktopName,
                    connected = connected,
                    transferMessage = transferMessage,
                    desktopStatus = desktopStatus,
                    updateInfo = updateInfo,
                    onDismissUpdate = acknowledgeUpdate,
                    onDownloadUpdate = openUpdateDownload,
                    onPair = { page = "Devices" },
                    onNavigate = { page = it }
                )
            }
        }
    }
    }
}

@Composable
private fun PageHeader(title: String, subtitle: String) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(title, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Text(subtitle, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun ColumnScope.RemoteInputPage(
    connected: Boolean,
    available: Boolean,
    enabled: Boolean,
    statusMessage: String,
    fullScreen: Boolean,
    onToggleFullScreen: () -> Unit,
    onInput: (String, Int, Int, Int, String, String, Int) -> Unit,
) {
    var text by remember { mutableStateOf("") }
    var editMessage by remember { mutableStateOf("") }
    val density = androidx.compose.ui.platform.LocalDensity.current.density
    val lastMoveAt = remember { longArrayOf(0L) }
    if (fullScreen) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text("Remote mode", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            TextButton(onClick = onToggleFullScreen) { Text("Exit full screen") }
        }
    } else {
        PageHeader("Remote input", "Use this phone as a touchpad and keyboard for your Linux desktop.")
        OutlinedButton(onClick = onToggleFullScreen, modifier = Modifier.fillMaxWidth()) {
            Text("Enter full-screen remote mode")
        }
    }
    if (statusMessage.isNotBlank()) {
        Text(statusMessage, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    if (!connected) {
        SectionCard("Desktop disconnected", "Reconnect to your paired desktop before sending pointer or keyboard input.")
        return
    }
    if (!available) {
        SectionCard(
            "Desktop input support unavailable",
            "On Wayland, install ydotool and start its user service on the desktop with `systemctl --user start ydotool.service`. The service also needs access to /dev/uinput. On X11, install xdotool. Reopen the Remote page after fixing the desktop setup."
        )
        return
    }
    if (!enabled) {
        SectionCard("Remote input is off", "On the desktop, open Remote input and enable ‘Allow remote input from the paired phone’.")
        return
    }
    Card(
        modifier = Modifier.fillMaxWidth()
            .then(if (fullScreen) Modifier.weight(1f) else Modifier.height(280.dp)),
    ) {
        Box(
            modifier = Modifier.fillMaxSize()
                .background(MaterialTheme.colorScheme.surfaceVariant)
                .pointerInput(onInput, density) {
                    awaitEachGesture {
                        val firstDown = awaitFirstDown(requireUnconsumed = false)
                        var maxPointers = 1
                        var dragging = false
                        var oneFingerDelta = Offset.Zero
                        var scrollRemainderX = 0f
                        var scrollRemainderY = 0f
                        var previousPositions = mapOf(firstDown.id to firstDown.position)
                        val touchSlop = viewConfiguration.touchSlop
                        while (true) {
                            val event = awaitPointerEvent()
                            val pressed = event.changes.filter { it.pressed }
                            maxPointers = maxOf(maxPointers, pressed.size)
                            if (pressed.isEmpty()) break
                            if (maxPointers == 1 && pressed.size == 1) {
                                val change = pressed.single()
                                val previous = previousPositions[change.id]
                                if (previous != null) {
                                    val delta = change.position - previous
                                    oneFingerDelta += delta
                                    if (dragging || oneFingerDelta.getDistance() >= touchSlop) {
                                        dragging = true
                                        val now = android.os.SystemClock.uptimeMillis()
                                        if (now - lastMoveAt[0] >= 32L) {
                                            onInput(
                                                "move",
                                                (oneFingerDelta.x * 2f).toInt(),
                                                (oneFingerDelta.y * 2f).toInt(),
                                                1, "", "", 1,
                                            )
                                            oneFingerDelta = Offset.Zero
                                            lastMoveAt[0] = now
                                        }
                                        change.consume()
                                    }
                                }
                            } else if (pressed.size >= 2) {
                                val deltas = pressed.mapNotNull { change ->
                                    previousPositions[change.id]?.let { change.position - it }
                                }
                                if (deltas.isNotEmpty()) {
                                    val averageDelta = deltas.reduce(Offset::plus) / deltas.size.toFloat()
                                    scrollRemainderX += averageDelta.x / (32f * density)
                                    scrollRemainderY -= averageDelta.y / (32f * density)
                                    val horizontal = scrollRemainderX.toInt().coerceIn(-12, 12)
                                    val vertical = scrollRemainderY.toInt().coerceIn(-12, 12)
                                    if (horizontal != 0 || vertical != 0) {
                                        onInput("scroll", horizontal, vertical, 1, "", "", 1)
                                        scrollRemainderX -= horizontal
                                        scrollRemainderY -= vertical
                                    }
                                    pressed.forEach { it.consume() }
                                }
                            }
                            previousPositions = pressed.associate { it.id to it.position }
                        }
                        if (dragging && (oneFingerDelta.x != 0f || oneFingerDelta.y != 0f)) {
                            onInput(
                                "move",
                                (oneFingerDelta.x * 2f).toInt(),
                                (oneFingerDelta.y * 2f).toInt(),
                                1, "", "", 1,
                            )
                        }
                        if (!dragging) {
                            when (maxPointers) {
                                1 -> onInput("click", 0, 0, 1, "", "", 1)
                                2 -> onInput("click", 0, 0, 3, "", "", 1)
                            }
                        }
                    }
                },
            contentAlignment = Alignment.Center,
        ) {
            Text(
                "1 finger: move · tap: click\n2 fingers: scroll · tap: right-click",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
            )
        }
    }
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
        OutlinedButton(onClick = { onInput("click", 0, 0, 1, "", "", 1) }, modifier = Modifier.weight(1f)) { Text("Left click") }
        OutlinedButton(onClick = { onInput("click", 0, 0, 3, "", "", 1) }, modifier = Modifier.weight(1f)) { Text("Right click") }
    }
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
        OutlinedButton(onClick = { onInput("key", 0, 0, 1, "", "Backspace", 1) }, modifier = Modifier.weight(1f)) { Text("⌫") }
        OutlinedButton(onClick = { onInput("key", 0, 0, 1, "", "Enter", 1) }, modifier = Modifier.weight(1f)) { Text("Enter") }
    }
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Live keyboard", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            OutlinedTextField(
                value = text,
                onValueChange = { value ->
                    val updated = value.take(1024)
                    when {
                        updated.startsWith(text) -> {
                            val added = updated.substring(text.length)
                            if (added.isNotEmpty()) onInput("type", 0, 0, 1, added, "", 1)
                            text = updated
                            editMessage = ""
                        }
                        text.startsWith(updated) -> {
                            val removed = text.length - updated.length
                            if (removed > 0) onInput("key", 0, 0, 1, "", "Backspace", removed)
                            text = updated
                            editMessage = ""
                        }
                        else -> {
                            editMessage = "For live typing, edit at the end of the text."
                        }
                    }
                },
                modifier = Modifier.fillMaxWidth(),
                label = { Text("Text is sent as you type") },
                singleLine = true,
            )
            if (editMessage.isNotBlank()) {
                Text(editMessage, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
            }
        }
    }
    if (!fullScreen) {
        Text("Pointer, scrolling, and keyboard input are sent over the encrypted paired connection. Disable remote input from the desktop at any time.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun DestinationIcon(destination: String) {
    when (destination) {
        "Home" -> Icon(Icons.Filled.Home, contentDescription = destination)
        "Devices" -> Icon(painterResource(R.drawable.ic_nav_devices), contentDescription = destination)
        "Files" -> Icon(painterResource(R.drawable.ic_nav_folder), contentDescription = destination)
        "Remote" -> Icon(painterResource(R.drawable.ic_nav_remote), contentDescription = destination)
        "Photos" -> Icon(painterResource(R.drawable.ic_nav_photos), contentDescription = destination)
        "Notifications" -> Icon(Icons.Filled.Notifications, contentDescription = destination)
        "Clipboard" -> Icon(painterResource(R.drawable.ic_nav_clipboard), contentDescription = destination)
        "Settings" -> Icon(Icons.Filled.Settings, contentDescription = destination)
        else -> Icon(Icons.Filled.Info, contentDescription = destination)
    }
}

@Composable
private fun HomePage(
    desktopName: String,
    connected: Boolean,
    transferMessage: String,
    desktopStatus: DesktopStatus?,
    updateInfo: UpdateInfo?,
    onDismissUpdate: () -> Unit,
    onDownloadUpdate: () -> Unit,
    onPair: () -> Unit,
    onNavigate: (String) -> Unit,
) {
    PageHeader("Link to Linux", "Your phone companion for Linux.")
    updateInfo?.let { info ->
        UpdateBanner(info, onDismissUpdate, onDownloadUpdate)
    }
    Card(modifier = Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = if (connected) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.secondaryContainer)) {
        Column(Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(if (connected) "● CONNECTED" else if (desktopName.isNotBlank()) "PAIRED · OFFLINE" else "NOT PAIRED", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold)
            Text(if (desktopName.isBlank()) "No desktop paired" else desktopName, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Text(if (connected) "Secure connection active. Phone status is syncing." else if (desktopName.isNotBlank()) "Your desktop is saved. Open Devices to reconnect." else "Pair a desktop on your local network to get started.", style = MaterialTheme.typography.bodyLarge)
            if (transferMessage.isNotBlank()) Text(transferMessage, style = MaterialTheme.typography.bodyMedium)
            if (desktopName.isBlank()) Button(onClick = onPair) { Text("Pair a desktop") }
        }
    }
    DesktopStatusCard(desktopStatus, connected)
    SectionCard("Phone status", if (connected) "This phone's battery, model, and storage are shared with the desktop while connected." else "Phone status appears on the desktop after a connection is active.")
    if (desktopName.isNotBlank()) TextButton(onClick = onPair) { Text("Pair another desktop") }
    Text("FEATURES", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
    listOf("Remote" to "Control your Linux desktop with this phone.", "Files" to "Choose files to send to your desktop.", "Photos" to "Browse phone photos or choose photos to send.", "Notifications" to "Forward selected phone notifications to Linux.", "Clipboard" to "Opt in to plain text sharing.").forEach { (title, detail) ->
        Card(modifier = Modifier.fillMaxWidth().clickable { onNavigate(title) }) {
            Row(Modifier.fillMaxWidth().padding(18.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                    Text(detail, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Text("›", style = MaterialTheme.typography.titleLarge, color = MaterialTheme.colorScheme.primary)
            }
        }
    }
}

@Composable
private fun DesktopStatusCard(status: DesktopStatus?, connected: Boolean) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.fillMaxWidth().padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("LINUX DESKTOP", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold)
                    Text(status?.deviceName ?: "Desktop status", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
                }
                Text(if (connected) "LIVE" else "LAST KNOWN", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
            }
            if (status == null) {
                Text("Desktop battery and storage details will appear after pairing.", color = MaterialTheme.colorScheme.onSurfaceVariant)
            } else {
                Text(status.model, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                val battery = status.batteryPercent
                Text(if (battery == null) "Battery · unavailable on this desktop" else "Battery · $battery%${if (status.charging) " · charging" else ""}", style = MaterialTheme.typography.bodyMedium)
                if (battery != null) LinearProgressIndicator(progress = battery / 100f, modifier = Modifier.fillMaxWidth())
                val total = status.storageTotalBytes
                val free = status.storageFreeBytes
                if (total > 0L && free >= 0L) {
                    Text("Storage · ${formatFileSize(free)} free of ${formatFileSize(total)}", style = MaterialTheme.typography.bodyMedium)
                    LinearProgressIndicator(progress = (free.toFloat() / total).coerceIn(0f, 1f), modifier = Modifier.fillMaxWidth())
                }
                Text(if (connected) "Updated just now" else "Showing the last status received", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

private fun formatFileSize(bytes: Long): String {
    if (bytes < 0L) return "Unknown size"
    if (bytes < 1000L) return "$bytes B"
    val units = arrayOf("KB", "MB", "GB", "TB")
    var amount = bytes.toDouble()
    var unit = -1
    do {
        amount /= 1000.0
        unit++
    } while (amount >= 1000.0 && unit < units.lastIndex)
    return String.format(java.util.Locale.getDefault(), "%.1f %s", amount, units[unit])
}

@Composable
private fun PairingPage(
    host: String, onHostChange: (String) -> Unit,
    port: String, onPortChange: (String) -> Unit,
    code: String, onCodeChange: (String) -> Unit,
    fingerprint: String, onFingerprintChange: (String) -> Unit,
    desktopName: String, isPairing: Boolean, message: String, isError: Boolean,
    onForget: () -> Unit, onReconnect: () -> Unit, onScan: () -> Unit, onPair: () -> Unit,
) {
    PageHeader("Pair a desktop", "Pair securely over your local network.")
    if (desktopName.isNotBlank()) Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)) {
        Column(Modifier.padding(22.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("PAIRED DESKTOP", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold)
            Text(desktopName, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Text("This desktop is saved. The phone tries to reconnect when the app opens; tap Reconnect to try again later.")
        }
    }
    if (desktopName.isNotBlank()) OutlinedButton(onClick = onReconnect, modifier = Modifier.fillMaxWidth(), enabled = !isPairing) {
        Text(if (isPairing) "Connecting…" else "Reconnect to saved desktop")
    }
    SectionCard("Pair another desktop", "On the desktop, open Devices & pairing and choose Start pairing. The session lasts three minutes and accepts one phone.")
    Button(onClick = onScan, modifier = Modifier.fillMaxWidth(), enabled = !isPairing) { Text("Scan desktop QR code") }
    OutlinedTextField(host, onHostChange, modifier = Modifier.fillMaxWidth(), label = { Text("Desktop IP address") }, placeholder = { Text("192.168.1.20") }, singleLine = true, enabled = !isPairing)
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        OutlinedTextField(port, { onPortChange(it.filter(Char::isDigit).take(5)) }, modifier = Modifier.weight(0.8f), label = { Text("Port") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), singleLine = true, enabled = !isPairing)
        OutlinedTextField(code, { onCodeChange(it.filter(Char::isDigit).take(6)) }, modifier = Modifier.weight(1.2f), label = { Text("6 digit code") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword), singleLine = true, enabled = !isPairing)
    }
    OutlinedTextField(
        fingerprint,
        { value -> onFingerprintChange(value.filter { it.isDigit() || it.lowercaseChar() in 'a'..'f' || it == ':' || it == ' ' || it == '-' }) },
        modifier = Modifier.fillMaxWidth(), label = { Text("Desktop certificate SHA-256") },
        placeholder = { Text("Scan the QR code or paste the fingerprint") },
        supportingText = { Text("This verifies the desktop before the pairing code is sent.") },
        minLines = 2, enabled = !isPairing,
    )
    Button(onClick = onPair, modifier = Modifier.fillMaxWidth(), enabled = !isPairing && host.isNotBlank() && code.length == 6 && fingerprint.isNotBlank()) {
        if (isPairing) { CircularProgressIndicator(modifier = Modifier.height(20.dp), strokeWidth = 2.dp); Spacer(Modifier.width(10.dp)) }
        Text(if (isPairing) "Pairing…" else "Pair securely")
    }
    if (message.isNotBlank()) Text(message, color = if (isError) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.bodyMedium)
    if (desktopName.isNotBlank()) {
        Button(onClick = onForget, modifier = Modifier.fillMaxWidth()) { Text("Forget this desktop on this phone") }
    }
}

@Composable
private fun FilesPage(
    desktopName: String,
    transferMessage: String,
    connected: Boolean,
    onChoose: () -> Unit,
    transferProgress: FileTransferProgress? = null,
    photos: Boolean = false,
    phonePhotoAccess: Boolean = false,
    onGrantPhonePhotoAccess: () -> Unit = {},
    offers: List<DesktopFileOffer> = emptyList(),
    onReceiveOffer: (DesktopFileOffer) -> Unit = {},
) {
    PageHeader(if (photos) "Photos" else "Files", if (photos) "Choose photos to copy securely to your Linux desktop." else "Choose files to copy securely to your Linux desktop.")
    if (photos) {
        SectionCard("Browse phone photos from desktop", if (phonePhotoAccess) "Photo access is enabled. The desktop can request a page of recent thumbnails when you choose Load photos." else "Allow access so the desktop Photos page can show recent thumbnails and request originals you choose to save." )
        OutlinedButton(onClick = onGrantPhonePhotoAccess, modifier = Modifier.fillMaxWidth(), enabled = !phonePhotoAccess) {
            Text(if (phonePhotoAccess) "Photo access enabled" else "Allow desktop photo browsing")
        }
    }
    SectionCard(if (connected) "Connected to $desktopName" else "Desktop not connected", if (connected) "Only the items you select in Android's picker are shared." else "Pair and connect to a desktop before sending items.")
    Button(onClick = onChoose, modifier = Modifier.fillMaxWidth(), enabled = connected) { Text(if (photos) "Choose photos" else "Choose files") }
    if (offers.isNotEmpty()) {
        Text(if (photos) "FROM YOUR DESKTOP" else "READY TO RECEIVE", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
        offers.forEach { offer ->
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(offer.filename, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                    Text("${offer.category.replaceFirstChar { it.uppercase() }} · ${formatFileSize(offer.sizeBytes)}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Button(onClick = { onReceiveOffer(offer) }, enabled = connected) { Text("Save to phone") }
                }
            }
        }
    }
    transferProgress?.let { progress ->
        TransferProgressCard(progress)
    }
    if (transferMessage.isNotBlank()) SectionCard("Transfer", transferMessage)
    SectionCard("Privacy", "Items are sent over the pinned encrypted connection and saved in the desktop's configured download folder.")
}

@Composable
private fun TransferProgressCard(progress: FileTransferProgress) {
    Card(Modifier.fillMaxWidth()) {
        Column(
            Modifier.fillMaxWidth().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text("${progress.direction} ${progress.filename}", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            val total = progress.totalBytes
            if (total >= 0L) {
                val fraction = if (total == 0L) 1f else (progress.transferredBytes.toFloat() / total).coerceIn(0f, 1f)
                LinearProgressIndicator(progress = fraction, modifier = Modifier.fillMaxWidth())
                Text(
                    "${formatFileSize(progress.transferredBytes)} of ${formatFileSize(total)} · ${(fraction * 100).toInt()}%",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            } else {
                LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
                Text(
                    "${formatFileSize(progress.transferredBytes)} sent · total size unavailable",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun EmptyFeaturePage(title: String, description: String, emptyTitle: String) {
    PageHeader(title, description)
    SectionCard(emptyTitle, "This feature is not connected yet. No phone data has been read.")
}

@Composable
private fun ToggleFeaturePage(
    title: String,
    description: String,
    label: String,
    enabled: Boolean,
    stateDescription: String,
    onChanged: (Boolean) -> Unit,
    actionLabel: String? = null,
    onAction: () -> Unit = {},
) {
    PageHeader(title, description)
    Card(modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth().padding(16.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(label, modifier = Modifier.weight(1f), style = MaterialTheme.typography.titleMedium)
            Switch(checked = enabled, onCheckedChange = onChanged)
        }
    }
    SectionCard("Privacy and permission", stateDescription)
    if (actionLabel != null) OutlinedButton(onClick = onAction, modifier = Modifier.fillMaxWidth()) { Text(actionLabel) }
}

@Composable
private fun ClipboardPage(enabled: Boolean, connected: Boolean, transferMessage: String, onEnabledChanged: (Boolean) -> Unit, onSendClipboard: () -> Unit) {
    PageHeader("Clipboard", "Share plain text between this phone and your Linux desktop.")
    Card(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth().padding(16.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Column(Modifier.weight(1f)) {
                Text("Enable clipboard sharing", style = MaterialTheme.typography.titleMedium)
                Text("Android reads copied text only when you tap Send copied text.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Switch(checked = enabled, onCheckedChange = onEnabledChanged)
        }
    }
    Button(onClick = onSendClipboard, modifier = Modifier.fillMaxWidth(), enabled = enabled && connected) { Text("Send copied text to desktop") }
    SectionCard(if (connected) "Secure link connected" else "Desktop disconnected", "Enable clipboard sharing on the desktop too. Text copied on the desktop will be sent to the phone while the app connection is active.")
    if (transferMessage.isNotBlank()) SectionCard("Clipboard", transferMessage)
    SectionCard("Privacy", "Clipboard text is limited to 64 KB and is not sent unless sharing is enabled on both devices.")
}

@Composable
private fun SettingsPage(darkMode: Boolean, onDarkModeChanged: (Boolean) -> Unit, downloadFolder: String, onChooseFolder: () -> Unit) {
    PageHeader("Settings", "Appearance, downloads, and privacy controls.")
    Card(modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth().padding(16.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Column(Modifier.weight(1f)) {
                Text("Dark mode", style = MaterialTheme.typography.titleMedium)
                Text("Use a dark appearance for Link to Linux.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Switch(checked = darkMode, onCheckedChange = onDarkModeChanged)
        }
    }
    SectionCard("Download location", downloadFolder)
    Button(onClick = onChooseFolder, modifier = Modifier.fillMaxWidth()) { Text("Choose download folder") }
    SectionCard("Background connection", "Link to Linux uses an ongoing connection notification while paired. Allow unrestricted battery use when Android asks if you want the link to stay active while the screen is off. This can use extra battery.")
    SectionCard("Privacy & security", "Trusted devices require explicit local pairing. Wi-Fi discovery, ADB, and production key storage are not connected yet.")
}

@Composable
private fun MorePage(onNavigate: (String) -> Unit) {
    PageHeader("More", "Additional features and app information.")
    listOf("Photos", "Notifications", "Clipboard", "Settings", "About").forEach { destination ->
        Card(modifier = Modifier.fillMaxWidth().clickable { onNavigate(destination) }) {
            Row(Modifier.fillMaxWidth().padding(18.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(destination, modifier = Modifier.weight(1f), style = MaterialTheme.typography.titleMedium)
                Text("›", style = MaterialTheme.typography.titleLarge, color = MaterialTheme.colorScheme.primary)
            }
        }
    }
}

@Composable
private fun AboutPage(onOpenLink: (String) -> Unit) {
    PageHeader("About Link to Linux", "A desktop companion for the Android features you choose to connect.")
    SectionCard("Link to Linux · 1.1.1", "Pair your phone with a Linux desktop to share files and photos, control media, use touchpad-style remote input, receive device status, and opt in to notifications and clipboard sharing.")
    SectionCard("Built by Young Jay", "An independent project from YoungTechsperts. YoungTechsperts builds practical software and digital projects.")
    Button(onClick = { onOpenLink("https://github.com/Youngjay42-real") }, modifier = Modifier.fillMaxWidth()) { Text("GitHub profile") }
    Button(onClick = { onOpenLink("https://youngai.site") }, modifier = Modifier.fillMaxWidth()) { Text("Visit youngai.site") }
}

@Composable
private fun SectionCard(title: String, description: String) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            Text(description, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

private fun pairingErrorMessage(error: Throwable, host: String, port: Int): String {
    val cause = generateSequence(error) { it.cause }.toList()
    return when {
        cause.any { it is ConnectException } -> "The desktop refused the connection at $host:$port. On the desktop, stop and start pairing again, then scan its new QR code. Keep both devices on the same Wi-Fi and allow incoming TCP port 44888 through the desktop firewall."
        cause.any { it is SocketTimeoutException } -> "The desktop did not respond. Check that it is awake, both devices are on the same network, and pairing is still active; then scan a fresh QR code."
        cause.any { it is CertificateException } -> error.message ?: "The desktop certificate did not match. Stop pairing and scan the current desktop QR code again."
        else -> error.message ?: "Pairing failed. Start a fresh pairing session on the desktop and scan its QR code again."
    }
}

private fun requestPairing(host: String, port: Int, code: String, fingerprint: String, deviceId: String, context: Context, reconnectToken: String = ""): Result<LiveLinkSession> = runCatching {
    require(host.isNotBlank()) { "Enter the desktop IP address." }
    require(port in 1..65535) { "Enter a valid port." }
    require((code.length == 6 && code.all(Char::isDigit)) || reconnectToken.isNotBlank()) { "Enter the 6 digit pairing code." }
    val expectedPin = fingerprint.filter { it.isDigit() || it.lowercaseChar() in 'a'..'f' }.lowercase()
    require(expectedPin.length == 64) { "Scan the QR code or enter the complete 64 character SHA-256 fingerprint." }

    val trustManager = object : X509TrustManager {
        override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
        override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) = Unit
        override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
            if (chain.isEmpty()) throw CertificateException("Desktop did not provide a certificate.")
            val actualPin = MessageDigest.getInstance("SHA-256").digest(chain[0].encoded).joinToString("") { "%02x".format(it) }
            if (!MessageDigest.isEqual(actualPin.toByteArray(), expectedPin.toByteArray())) {
                throw CertificateException("Certificate fingerprint does not match the desktop. Pairing stopped.")
            }
        }
    }
    val tls = SSLContext.getInstance("TLS")
    tls.init(null, arrayOf(trustManager), SecureRandom())
    val raw = Socket()
    raw.connect(InetSocketAddress(host, port), 6000)
    raw.soTimeout = 8000
    val secure = tls.socketFactory.createSocket(raw, host, port, true) as SSLSocket
    secure.startHandshake()
    val session = LiveLinkSession(secure)
    try {
        val request = JSONObject()
            .put("kind", "pairing.request")
            .put("protocol_version", "1.0.0")
            .put("device_id", deviceId)
            .put("device_name", "${Build.MANUFACTURER} ${Build.MODEL}".take(80))
            .put("pairing_code", code)
            .put("reconnect_token", reconnectToken)
            .put("device_status", readPhoneStatus(context).put("clipboard_enabled", context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE).getBoolean("clipboard_sync", false)))
            .put("clipboard_enabled", context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE).getBoolean("clipboard_sync", false))
        val payload = session.exchange(request)
        if (payload.optString("kind") != "pairing.accept") throw java.io.IOException(payload.optString("message", "Pairing was rejected by the desktop."))
        if (payload.optString("protocol_version") != "1.0.0") throw java.io.IOException("The desktop is using an unsupported pairing protocol.")
        session.desktopName = payload.optString("desktop_name").ifBlank { "Linux desktop" }
        session.reconnectToken = payload.optString("reconnect_token")
        if (session.reconnectToken.isBlank()) throw java.io.IOException("Desktop did not save this device for reconnecting.")
        payload.optJSONObject("desktop_status")?.let { session.latestDesktopStatus = DesktopStatus.fromJson(it) }
        session
    } catch (error: Throwable) {
        session.close()
        throw error
    }
}

internal fun readPhoneStatus(context: Context): JSONObject {
    val batteryIntent = context.registerReceiver(null, android.content.IntentFilter(Intent.ACTION_BATTERY_CHANGED))
    val level = batteryIntent?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
    val scale = batteryIntent?.getIntExtra(BatteryManager.EXTRA_SCALE, 100) ?: 100
    val percent = if (level >= 0 && scale > 0) (level * 100 / scale).coerceIn(0, 100) else 0
    val plugged = (batteryIntent?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) ?: 0) != 0
    val root = Environment.getDataDirectory()
    val stats = android.os.StatFs(root.path)
    return JSONObject()
        .put("kind", "device.status")
        .put("battery_percent", percent)
        .put("charging", plugged)
        .put("storage_total_bytes", stats.totalBytes)
        .put("storage_free_bytes", stats.availableBytes)
        .put("model", "${Build.MANUFACTURER} ${Build.MODEL}".take(100))
}

private fun requestBackgroundConnectionExemption(context: Context) {
    val power = context.getSystemService(Context.POWER_SERVICE) as PowerManager
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !power.isIgnoringBatteryOptimizations(context.packageName)) {
        runCatching {
            context.startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:${context.packageName}")))
        }
    }
}

private fun hasPhonePhotoAccess(context: Context): Boolean {
    if (context.checkSelfPermission(Manifest.permission.READ_MEDIA_IMAGES) == android.content.pm.PackageManager.PERMISSION_GRANTED) return true
    return Build.VERSION.SDK_INT >= 34 && context.checkSelfPermission(Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED) == android.content.pm.PackageManager.PERMISSION_GRANTED
}

@Suppress("DEPRECATION")
internal fun postTransferNotification(context: Context, title: String, message: String) {
    val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as android.app.NotificationManager
    val channelId = "linktolinux-transfers"
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        manager.createNotificationChannel(
            android.app.NotificationChannel(channelId, "File transfers", android.app.NotificationManager.IMPORTANCE_DEFAULT)
                .apply { description = "Confirms files received by a paired device." },
        )
    }
    val notification = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        android.app.Notification.Builder(context, channelId)
    } else {
        android.app.Notification.Builder(context)
    }
        .setSmallIcon(android.R.drawable.stat_sys_download_done)
        .setContentTitle(title)
        .setContentText(message)
        .setAutoCancel(true)
        .build()
    manager.notify((System.currentTimeMillis() % Int.MAX_VALUE).toInt(), notification)
}

data class DesktopStatus(
    val deviceName: String,
    val model: String,
    val batteryPercent: Int?,
    val charging: Boolean,
    val storageTotalBytes: Long,
    val storageFreeBytes: Long,
    val remoteInputAvailable: Boolean,
    val remoteInputEnabled: Boolean,
) {
    companion object {
        fun fromJson(value: JSONObject) = DesktopStatus(
            deviceName = value.optString("device_name", "Linux desktop"),
            model = value.optString("model", "Linux"),
            batteryPercent = if (value.isNull("battery_percent")) null else value.optInt("battery_percent"),
            charging = value.optBoolean("charging"),
            storageTotalBytes = value.optLong("storage_total_bytes"),
            storageFreeBytes = value.optLong("storage_free_bytes"),
            remoteInputAvailable = value.optBoolean("remote_input_available"),
            remoteInputEnabled = value.optBoolean("remote_input_enabled"),
        )
    }
}

private data class RemoteInputCommand(
    val action: String,
    val dx: Int = 0,
    val dy: Int = 0,
    val button: Int = 1,
    val text: String = "",
    val key: String = "",
    val repeat: Int = 1,
)

data class DesktopFileOffer(
    val transferId: String,
    val filename: String,
    val sizeBytes: Long,
    val mimeType: String,
    val category: String,
) {
    companion object {
        fun fromJson(value: JSONObject) = DesktopFileOffer(
            transferId = value.getString("transfer_id"),
            filename = value.getString("filename"),
            sizeBytes = value.optLong("size_bytes"),
            mimeType = value.optString("mime_type", "application/octet-stream"),
            category = value.optString("category", "file"),
        )
    }
}

internal object ActiveLink {
    @Volatile var session: LiveLinkSession? = null
    @Volatile var desktopStatus: DesktopStatus? = null
    private val offers = linkedMapOf<String, DesktopFileOffer>()
    @Synchronized fun addOffer(offer: DesktopFileOffer) { offers[offer.transferId] = offer }
    @Synchronized fun removeOffer(id: String) { offers.remove(id) }
    @Synchronized fun pendingOffers(): List<DesktopFileOffer> = offers.values.toList()
}

internal class LiveLinkSession(private val socket: SSLSocket) {
    private val reader = BufferedReader(InputStreamReader(socket.getInputStream(), Charsets.UTF_8))
    private val writer = OutputStreamWriter(socket.getOutputStream(), Charsets.UTF_8)
    var desktopName: String = "Linux desktop"
    var reconnectToken: String = ""
    var latestDesktopStatus: DesktopStatus? = null

    @Synchronized fun exchange(message: JSONObject): JSONObject {
        check(!socket.isClosed) { "Desktop connection is closed." }
        writer.write(message.toString()); writer.write("\n"); writer.flush()
        return JSONObject(reader.readLine() ?: throw java.io.IOException("Desktop closed the connection."))
    }

    @Synchronized fun sendRemoteInput(
        action: String,
        dx: Int,
        dy: Int,
        button: Int,
        text: String,
        key: String,
        repeat: Int = 1,
    ) {
        val message = JSONObject().put("kind", "remote.input").put("action", action)
        when (action) {
            "move" -> message.put("dx", dx).put("dy", dy)
            "click" -> message.put("button", button)
            "scroll" -> message.put("dx", dx).put("dy", dy)
            "type" -> message.put("text", text)
            "key" -> message.put("key", key).put("repeat", repeat)
            else -> throw IllegalArgumentException("Unsupported remote input action.")
        }
        val reply = exchange(message)
        if (reply.optString("kind") != "remote.input.accept") {
            throw java.io.IOException(reply.optString("message", "Desktop rejected remote input."))
        }
    }

    @Synchronized fun sendStatus(context: Context, clipboardEnabled: Boolean, phoneRinging: Boolean, mediaCommandAck: String): JSONObject {
        val reply = exchange(readPhoneStatus(context)
            .put("clipboard_enabled", clipboardEnabled)
            .put("phone_ringing", phoneRinging)
            .put("media", PhoneMediaSessions.status(context))
            .put("media_command_ack", mediaCommandAck))
        if (reply.optString("kind") != "status.accept") throw java.io.IOException(reply.optString("message", "Status update rejected."))
        reply.optJSONObject("desktop_status")?.let { latestDesktopStatus = DesktopStatus.fromJson(it) }
        if (clipboardEnabled && reply.optBoolean("clipboard_enabled") && reply.has("clipboard_text")) {
            val text = reply.optString("clipboard_text")
            val manager = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            val current = runCatching { manager.primaryClip?.getItemAt(0)?.coerceToText(context)?.toString() }.getOrNull()
            if (text != current) manager.setPrimaryClip(ClipData.newPlainText("Link to Linux", text))
        }
        reply.optJSONObject("file_offer")?.let { offer -> ActiveLink.addOffer(DesktopFileOffer.fromJson(offer)) }
        return reply
    }

    @Synchronized fun receiveFile(
        resolver: ContentResolver,
        uri: Uri,
        offer: DesktopFileOffer,
        onProgress: (Long, Long) -> Unit = { _, _ -> },
    ): String {
        require(offer.sizeBytes in 0..(256L * 1024 * 1024)) { "Files must be 256 MB or smaller." }
        var started = false
        try {
            var reply = exchange(JSONObject().put("kind", "file.get.begin").put("transfer_id", offer.transferId))
            if (reply.optString("kind") != "file.get.ready") throw java.io.IOException(reply.optString("message", "Desktop did not accept the transfer."))
            started = true
            val expectedSize = reply.optLong("size_bytes", -1)
            if (expectedSize != offer.sizeBytes || expectedSize !in 0..(256L * 1024 * 1024)) throw java.io.IOException("Desktop file size changed.")
            onProgress(0L, expectedSize)
            val output = resolver.openOutputStream(uri, "w") ?: throw java.io.IOException("Could not open the selected save location.")
            val digest = MessageDigest.getInstance("SHA-256")
            var index = 0
            var written = 0L
            var lastProgressAt = android.os.SystemClock.uptimeMillis()
            var lastProgressBytes = 0L
            output.use { stream ->
                while (written < expectedSize) {
                    reply = exchange(JSONObject().put("kind", "file.get.chunk").put("transfer_id", offer.transferId).put("index", index))
                    if (reply.optString("kind") != "file.get.data" || reply.optInt("index", -1) != index) throw java.io.IOException(reply.optString("message", "Desktop file transfer was interrupted."))
                    val chunk = android.util.Base64.decode(reply.getString("data"), android.util.Base64.DEFAULT)
                    if (chunk.isEmpty() || written + chunk.size > expectedSize) throw java.io.IOException("Desktop sent an invalid file chunk.")
                    stream.write(chunk)
                    digest.update(chunk)
                    written += chunk.size
                    index++
                    val now = android.os.SystemClock.uptimeMillis()
                    if (written - lastProgressBytes >= 128 * 1024 || now - lastProgressAt >= 100) {
                        onProgress(written, expectedSize)
                        lastProgressAt = now
                        lastProgressBytes = written
                    }
                }
                stream.flush()
            }
            onProgress(written, expectedSize)
            reply = exchange(JSONObject().put("kind", "file.get.finish").put("transfer_id", offer.transferId)
                .put("sha256", digest.digest().joinToString("") { "%02x".format(it) }))
            started = false
            if (reply.optString("kind") != "file.get.saved") throw java.io.IOException(reply.optString("message", "Desktop could not verify the received file."))
            return reply.optString("filename", offer.filename)
        } catch (error: Throwable) {
            if (started) runCatching { exchange(JSONObject().put("kind", "file.get.cancel").put("transfer_id", offer.transferId)) }
            runCatching { resolver.delete(uri, null, null) }
            throw error
        }
    }

    @Synchronized fun sendClipboard(text: String) {
        require(text.toByteArray(Charsets.UTF_8).size <= 64 * 1024) { "Clipboard text is limited to 64 KB." }
        val reply = exchange(JSONObject().put("kind", "clipboard.update").put("clipboard_enabled", true).put("text", text))
        if (reply.optString("kind") != "clipboard.accept") throw java.io.IOException(reply.optString("message", "Desktop rejected the clipboard update."))
    }

    @Synchronized fun sendPhoneNotification(appName: String, title: String, body: String) {
        val reply = exchange(JSONObject().put("kind", "notification.sync")
            .put("app_name", appName.take(120)).put("title", title.take(256)).put("body", body.take(2048)))
        if (reply.optString("kind") != "notification.accept") {
            throw java.io.IOException(reply.optString("message", "Desktop rejected the phone notification."))
        }
    }

    @Synchronized fun sendPhonePhotos(context: Context) {
        if (!hasPhonePhotoAccess(context)) {
            exchange(JSONObject().put("kind", "photos.unavailable")
                .put("message", "Open Link to Linux on Android and allow photo access from the Photos page."))
            return
        }
        val rows = org.json.JSONArray()
        var encodedBytes = 0
        val columns = arrayOf(MediaStore.Images.Media._ID, MediaStore.Images.Media.DISPLAY_NAME, MediaStore.Images.Media.DATE_ADDED)
        val cursor = context.contentResolver.query(
            MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
            columns,
            null,
            null,
            "${MediaStore.Images.Media.DATE_ADDED} DESC",
        ) ?: run {
            exchange(JSONObject().put("kind", "photos.unavailable")
                .put("message", "Android could not read the photo library. Check photo access in Link to Linux settings."))
            return
        }
        cursor.use { images ->
            val idColumn = images.getColumnIndexOrThrow(MediaStore.Images.Media._ID)
            val nameColumn = images.getColumnIndexOrThrow(MediaStore.Images.Media.DISPLAY_NAME)
            val dateColumn = images.getColumnIndexOrThrow(MediaStore.Images.Media.DATE_ADDED)
            while (images.moveToNext() && rows.length() < 12) {
                val id = images.getLong(idColumn)
                val uri = ContentUris.withAppendedId(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, id)
                runCatching {
                    val bitmap = context.contentResolver.loadThumbnail(uri, Size(128, 128), null)
                    val output = ByteArrayOutputStream()
                    bitmap.compress(android.graphics.Bitmap.CompressFormat.JPEG, 48, output)
                    val bytes = output.toByteArray()
                    val encoded = android.util.Base64.encodeToString(bytes, android.util.Base64.NO_WRAP)
                    if (bytes.size <= 12 * 1024 && encodedBytes + encoded.length <= 72 * 1024) {
                        encodedBytes += encoded.length
                        rows.put(JSONObject().put("id", id.toString())
                            .put("name", images.getString(nameColumn).take(240))
                            .put("date_added", images.getLong(dateColumn))
                            .put("thumbnail", encoded))
                    }
                    bitmap.recycle()
                }
            }
        }
        val reply = exchange(JSONObject().put("kind", "photos.page").put("photos", rows))
        if (reply.optString("kind") != "photos.page.accept") {
            throw java.io.IOException(reply.optString("message", "Desktop could not display phone photos."))
        }
    }

    @Synchronized fun sendPhonePhoto(context: Context, mediaId: String, mode: String): String {
        require(mediaId.all(Char::isDigit)) { "Invalid phone photo selection." }
        require(mode == "save" || mode == "view") { "Invalid phone photo action." }
        if (!hasPhonePhotoAccess(context)) throw SecurityException("Allow photo access in Link to Linux on Android first.")
        val accepted = exchange(JSONObject().put("kind", "photos.download.accept").put("id", mediaId).put("mode", mode))
        if (accepted.optString("kind") != "photos.download.accepted") {
            throw java.io.IOException(accepted.optString("message", "Desktop photo request expired."))
        }
        val uri = ContentUris.withAppendedId(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, mediaId.toLong())
        return sendFile(context.contentResolver, uri, if (mode == "view") "preview" else "photo")
    }

    @Synchronized fun setClipboardEnabled(enabled: Boolean) {
        val reply = exchange(JSONObject().put("kind", "clipboard.state").put("enabled", enabled))
        if (reply.optString("kind") != "clipboard.state.accept") throw java.io.IOException(reply.optString("message", "Desktop did not update the clipboard setting."))
    }

    @Synchronized fun sendFile(
        resolver: ContentResolver,
        uri: Uri,
        category: String,
        onProgress: (Long, Long) -> Unit = { _, _ -> },
    ): String {
        val name = queryName(resolver, uri)
        val size = querySize(resolver, uri)
        require(size <= if (category == "preview") 32L * 1024 * 1024 else 256L * 1024 * 1024) {
            if (category == "preview") "This image is too large to preview (32 MB limit). Save it to the desktop instead."
            else "Files must be 256 MB or smaller."
        }
        val id = UUID.randomUUID().toString()
        val mime = resolver.getType(uri) ?: "application/octet-stream"
        var started = false
        try {
            var reply = exchange(JSONObject().put("kind", "file.begin").put("transfer_id", id).put("filename", name)
                .put("size_bytes", size).put("category", category).put("mime_type", mime))
            if (reply.optString("kind") != "file.ready") throw java.io.IOException(reply.optString("message", "Desktop did not accept the transfer."))
            started = true
            onProgress(0L, size)
            val digest = MessageDigest.getInstance("SHA-256")
            var chunkIndex = 0
            var total = 0L
            var lastProgressAt = android.os.SystemClock.uptimeMillis()
            var lastProgressBytes = 0L
            resolver.openInputStream(uri)?.use { input ->
                val buffer = ByteArray(48 * 1024)
                while (true) {
                    val count = input.read(buffer)
                    if (count < 0) break
                    if (count == 0) continue
                    total += count
                    require(total <= if (category == "preview") 32L * 1024 * 1024 else 256L * 1024 * 1024) {
                        if (category == "preview") "This image is too large to preview (32 MB limit)."
                        else "Files must be 256 MB or smaller."
                    }
                    digest.update(buffer, 0, count)
                    val encoded = android.util.Base64.encodeToString(buffer.copyOf(count), android.util.Base64.NO_WRAP)
                    reply = exchange(JSONObject().put("kind", "file.chunk").put("transfer_id", id).put("index", chunkIndex).put("data", encoded))
                    if (reply.optString("kind") != "file.ack" || reply.optInt("index", -1) != chunkIndex) throw java.io.IOException(reply.optString("message", "Desktop did not acknowledge a file chunk."))
                    chunkIndex++
                    val now = android.os.SystemClock.uptimeMillis()
                    if (total - lastProgressBytes >= 128 * 1024 || now - lastProgressAt >= 100) {
                        onProgress(total, size)
                        lastProgressAt = now
                        lastProgressBytes = total
                    }
                }
            } ?: throw java.io.IOException("Could not open the selected item.")
            if (size >= 0 && size != total) throw java.io.IOException("Selected file changed during transfer.")
            onProgress(total, if (size >= 0) size else total)
            reply = exchange(JSONObject().put("kind", "file.finish").put("transfer_id", id)
                .put("sha256", digest.digest().joinToString("") { "%02x".format(it) }))
            started = false
            val expectedReply = if (category == "preview") "file.preview.saved" else "file.saved"
            if (reply.optString("kind") != expectedReply) throw java.io.IOException(reply.optString("message", "Desktop could not save the file."))
            return reply.optString("filename", name)
        } catch (error: Throwable) {
            if (started) runCatching { exchange(JSONObject().put("kind", "file.cancel").put("transfer_id", id)) }
            throw error
        }
    }

    fun close() { runCatching { socket.close() } }

    private fun queryName(resolver: ContentResolver, uri: Uri): String {
        var name = uri.lastPathSegment?.substringAfterLast('/') ?: "shared-file"
        val cursor: Cursor? = resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)
        cursor?.use { if (it.moveToFirst()) name = it.getString(0) ?: name }
        return name.take(240).ifBlank { "shared-file" }
    }

    private fun querySize(resolver: ContentResolver, uri: Uri): Long {
        val cursor = resolver.query(uri, arrayOf(OpenableColumns.SIZE), null, null, null)
        cursor?.use { if (it.moveToFirst()) return it.getLong(0) }
        return -1L
    }
}

@Composable
private fun UpdateBanner(
    info: UpdateInfo,
    onDismiss: () -> Unit,
    onDownload: () -> Unit,
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 8.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.tertiaryContainer),
        elevation = CardDefaults.cardElevation(defaultElevation = 4.dp)
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        "Update Available: Version ${info.version}",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                    )
                    if (info.notes.isNotBlank()) {
                        Text(
                            info.notes,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            maxLines = 2,
                            overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis
                        )
                    }
                    if (info.publishedAt.isNotBlank()) {
                        Text(
                            "Published ${info.publishedAt}",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TextButton(onClick = onDismiss) {
                        Text("Later")
                    }
                    Button(onClick = onDownload, colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary)) {
                        Text("Download update")
                    }
                }
            }
        }
    }
}
