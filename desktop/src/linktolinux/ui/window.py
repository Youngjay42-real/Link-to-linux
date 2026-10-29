from __future__ import annotations

import base64
import io
import json
import logging
import time
import webbrowser
from urllib.parse import urlencode
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from linktolinux.application import LinkToLinuxApplication

try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gio, GLib, Gtk, Gdk, GdkPixbuf
except (ImportError, ValueError):  # pragma: no cover - depends on system GTK packages
    Adw = None
    Gio = None
    GLib = None
    Gtk = None
    Gdk = None
    GdkPixbuf = None

_LOGGER = logging.getLogger(__name__)


class LinkToLinuxWindow:
    """GTK4/libadwaita application window for the desktop client."""

    def __init__(self, model: "LinkToLinuxApplication") -> None:
        if Adw is None or Gtk is None or Gio is None:
            raise RuntimeError(
                "GTK4, libadwaita, and PyGObject are required to open the desktop window. "
                "Install python3-gi, gir1.2-gtk-4.0, and gir1.2-adw-1."
            )
        self.model = model
        self.model.pairing_server.add_pairing_listener(self._on_pairing_completed)
        self.model.pairing_server.add_status_listener(self._on_phone_status)
        self.model.pairing_server.add_file_listener(self._on_file_received)
        self.model.pairing_server.add_file_sent_listener(self._on_desktop_file_sent)
        self.model.pairing_server.add_clipboard_listener(self._on_phone_clipboard)
        self.model.pairing_server.add_notification_listener(self._on_phone_notification)
        self.model.pairing_server.add_phone_photos_listener(self._on_phone_photos)
        self.model.pairing_server.add_photo_preview_listener(self._on_photo_preview)
        self.application = Adw.Application(
            application_id="io.github.linktolinux.LinkToLinux",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.application.connect("activate", self._on_activate)
        self.window: Any = None
        self.stack: Any = None
        self._navigation_buttons: dict[str, Any] = {}
        self._navigation_labels: list[Any] = []
        self._sidebar_collapsed = False
        self._sidebar_paned: Any = None
        self._pairing_ui: dict[str, Any] | None = None
        self._refresh_trusted_devices: Any = None
        self._home_connection_label: Any = None
        self._home_connection_message: Any = None
        self._home_ring_button: Any = None
        self._home_ring_status: Any = None
        self._home_media_label: Any = None
        self._home_media_note: Any = None
        self._home_media_buttons: list[Any] = []
        self._home_media_button_actions: dict[str, Any] = {}
        self._home_status_label: Any = None
        self._home_status_widgets: dict[str, Any] = {}
        self._clipboard: Any = None
        self._last_remote_clipboard = ""
        self._clipboard_status_label: Any = None
        self._status_refresh_source = 0
        self._photo_page_connected = self.model.pairing_server.session_connected
        self._update_banner: Any = None
        self._update_banner_info: dict | None = None

    def start(self) -> int:
        return self.application.run(None)

    def _on_activate(self, application: Any) -> None:
        if self.window is not None:
            self.window.present()
            return

        self.window = Adw.ApplicationWindow(application=application)
        self.window.connect("close-request", self._on_close_request)
        self.window.set_title("Link to Linux")
        self.window.set_default_size(1100, 760)
        self.window.set_size_request(760, 560)

        self._install_styles()

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        title = Adw.WindowTitle(title="Link to Linux", subtitle="Connect your phone and Linux desktop")
        header.set_title_widget(title)
        toolbar.add_top_bar(header)

        layout = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        layout.set_hexpand(True)
        layout.set_vexpand(True)
        sidebar_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        sidebar_panel.add_css_class("navigation-sidebar")
        sidebar_panel.set_vexpand(True)
        sidebar_panel.set_valign(Gtk.Align.FILL)
        sidebar_panel.set_size_request(56, -1)
        sidebar_panel.set_margin_top(14)
        sidebar_panel.set_margin_bottom(14)
        sidebar_panel.set_margin_start(12)
        sidebar_panel.set_margin_end(12)

        brand_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        brand_row.set_margin_start(4)
        brand_row.set_margin_end(4)
        brand = Gtk.Label(label="LINK TO LINUX")
        brand.add_css_class("heading")
        brand.set_xalign(0)
        brand.set_hexpand(True)
        brand_row.append(brand)
        collapse_button = Gtk.Button.new_from_icon_name("sidebar-hide-symbolic")
        self._sidebar_toggle_icon = collapse_button.get_child()
        collapse_button.add_css_class("flat")
        collapse_button.set_tooltip_text("Collapse sidebar")
        collapse_button.connect("clicked", self._toggle_sidebar)
        brand_row.append(collapse_button)
        sidebar_panel.append(brand_row)
        self._navigation_labels = [brand]

        brand_note = Gtk.Label(label="PHONE COMPANION")
        brand_note.add_css_class("caption")
        brand_note.add_css_class("dim-label")
        brand_note.set_xalign(0)
        brand_note.set_margin_start(12)
        sidebar_panel.append(brand_note)
        self._navigation_labels.append(brand_note)

        self.stack = Gtk.Stack()
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(160)
        self._add_pages()

        self._navigation_buttons = {}
        for name, label, icon_name in (
            ("home", "Home", "go-home-symbolic"),
            ("devices", "Devices & pairing", "phone-symbolic"),
            ("files", "Files", "folder-symbolic"),
            ("photos", "Photos", "image-x-generic-symbolic"),
            ("notifications", "Notifications", "preferences-system-notifications-symbolic"),
            ("clipboard", "Clipboard", "edit-copy-symbolic"),
            ("remote", "Remote input", "input-mouse-symbolic"),
            ("settings", "Settings", "emblem-system-symbolic"),
            ("about", "About", "help-about-symbolic"),
        ):
            button = Gtk.Button()
            button.add_css_class("flat")
            button.add_css_class("navigation-button")
            button.set_hexpand(True)
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row.set_margin_start(4); row.set_margin_end(4)
            icon = Gtk.Image.new_from_icon_name(icon_name)
            icon.set_pixel_size(18)
            text = Gtk.Label(label=label, xalign=0)
            text.set_hexpand(True)
            self._navigation_labels.append(text)
            row.append(icon); row.append(text)
            button.set_child(row)
            button.connect("clicked", lambda _button, page_name=name: self.stack.set_visible_child_name(page_name))
            self._navigation_buttons[name] = button
            sidebar_panel.append(button)
        self.stack.connect("notify::visible-child-name", self._sync_navigation)
        self._sync_navigation(self.stack, None)

        content_frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content_frame.set_hexpand(True)
        content_frame.set_vexpand(True)
        content_frame.set_valign(Gtk.Align.FILL)
        content_frame.set_halign(Gtk.Align.FILL)
        content_frame.append(self.stack)
        self._sidebar_paned = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        self._sidebar_paned.set_wide_handle(True)
        self._sidebar_paned.set_resize_start_child(False)
        self._sidebar_paned.set_shrink_start_child(False)
        self._sidebar_paned.set_start_child(sidebar_panel)
        self._sidebar_paned.set_end_child(content_frame)
        self._sidebar_paned.set_position(190)
        layout.append(self._sidebar_paned)

        toolbar.set_content(layout)
        self.window.set_content(toolbar)
        self.window.present()
        self._status_refresh_source = GLib.timeout_add_seconds(1, self._status_tick)
        display = Gdk.Display.get_default()
        if display is not None:
            self._clipboard = display.get_clipboard()
            self._clipboard.connect("changed", self._on_local_clipboard_changed)

        # Start periodic update checks
        self.model.update_checker.start_periodic_checks(self)

    def _toggle_sidebar(self, button: Any) -> None:
        self._sidebar_collapsed = not self._sidebar_collapsed
        for label in self._navigation_labels:
            label.set_visible(not self._sidebar_collapsed)
        for name, nav_button in self._navigation_buttons.items():
            row = nav_button.get_child()
            row.set_halign(Gtk.Align.CENTER if self._sidebar_collapsed else Gtk.Align.FILL)
            nav_button.set_tooltip_text(name.replace("_", " ").title() if self._sidebar_collapsed else None)
        self._sidebar_paned.set_position(80 if self._sidebar_collapsed else 190)
        self._sidebar_toggle_icon.set_from_icon_name("sidebar-show-symbolic" if self._sidebar_collapsed else "sidebar-hide-symbolic")
        button.set_tooltip_text("Expand sidebar" if self._sidebar_collapsed else "Collapse sidebar")

    def _on_close_request(self, _window: Any) -> bool:
        if self._status_refresh_source:
            GLib.source_remove(self._status_refresh_source)
            self._status_refresh_source = 0
        self.model.update_checker.stop_periodic_checks()
        self.model.pairing_server.stop()
        return False

    def show_update_banner(self, info: dict) -> None:
        """Show an update banner in the home page."""
        version = info.get("version")
        if (
            self._update_banner is not None
            or not isinstance(version, str)
            or version == self.model.settings.last_notified_update_version
        ):
            return  # Already showing a banner

        self._update_banner_info = info

        # Create the banner
        banner = Adw.Banner()
        banner.set_title(f"Update Available: Version {info['version']}")
        banner.set_revealed(True)
        banner.add_button("Later", self._dismiss_update_banner)
        banner.add_button("Download update", self._open_update_url)
        banner.set_button_appearance("Download update", Adw.ResponseAppearance.SUGGESTED)

        notes = info.get("notes", "").strip()
        published_at = info.get("published_at", "")
        summary = notes[:200] + ("..." if len(notes) > 200 else "")
        if published_at:
            summary = f"Published {published_at}. {summary}".strip()
        if summary:
            banner.set_body(summary)

        # Insert banner at the top of the home page
        if self.stack is not None:
            home_page = self.stack.get_child_by_name("home")
            if home_page:
                # Find the first child (the scrolled window) and insert banner before it
                first_child = home_page.get_first_child()
                if first_child:
                    home_page.insert_child_before(banner, first_child)
                    self._update_banner = banner
                    self.model.update_checker.mark_notified(version)

    def _dismiss_update_banner(self, _button: Any) -> None:
        """Dismiss the current update banner."""
        if self._update_banner is not None:
            self._update_banner.set_revealed(False)
            self._update_banner = None

        self._update_banner_info = None

    def _open_update_url(self, _button: Any) -> None:
        """Open the release page in the default browser."""
        if self._update_banner_info:
            url = self._update_banner_info.get("url") or self._update_banner_info.get("release_url")
            try:
                if url and not webbrowser.open(url):
                    _LOGGER.warning("No browser accepted the update URL.")
            except webbrowser.Error as error:
                _LOGGER.warning("Could not open the update URL: %s", type(error).__name__)
        self._dismiss_update_banner(None)

    def _sync_navigation(self, _stack: Any, _property: Any) -> None:
        current = self.stack.get_visible_child_name() if self.stack is not None else "home"
        for name, button in self._navigation_buttons.items():
            if name == current:
                button.add_css_class("navigation-active")
            else:
                button.remove_css_class("navigation-active")

    def _on_pairing_completed(self, _device_id: str, device_name: str) -> None:
        if GLib is not None:
            GLib.idle_add(self._refresh_paired_pages, device_name)

    def _on_phone_status(self, _device_id: str, _status: dict) -> None:
        if GLib is not None:
            GLib.idle_add(self._update_home_status)
            connected = self.model.pairing_server.session_connected
            if connected != self._photo_page_connected:
                self._photo_page_connected = connected
                GLib.idle_add(self._refresh_photos_if_visible)

    def _refresh_photos_if_visible(self) -> bool:
        if self.stack is not None and self.stack.get_visible_child_name() == "photos":
            self._refresh_page("photos")
        return False

    def _update_home_status(self) -> bool:
        phone = self.model.phone_status
        connected = self.model.pairing_server.session_connected
        if self._home_connection_label is not None:
            name = phone.get("device_name", self.model.pairing_server.connected_device_name)
            self._home_connection_label.set_text(f"Connected · {name}" if connected else "Phone disconnected" if phone.get("device_id") else "No phone paired")
        if self._home_connection_message is not None:
            self._home_connection_message.set_text("Secure link active · device status updates every few seconds." if connected else "Start a new pairing session on both devices to connect securely." if phone.get("device_id") else "Pair an Android phone to see its live status and share selected items.")
        ring_requested = self.model.pairing_server.phone_ring_requested
        ring_active = self.model.pairing_server.phone_ring_active
        if self._home_ring_button is not None:
            self._home_ring_button.set_label("Stop ringing" if ring_requested else "Ring phone")
            self._home_ring_button.set_sensitive(connected)
        if self._home_ring_status is not None:
            self._home_ring_status.set_text(
                "Phone is ringing" if ring_active else
                "Waiting for the phone…" if ring_requested else
                "Uses the ringtone and volume set on Android."
            )
        has_media = phone.get("media_available") is True
        if self._home_media_label is not None:
            title, artist = phone.get("media_title", ""), phone.get("media_artist", "")
            self._home_media_label.set_text(
                f"{title} · {artist}" if title and artist else title or artist or
                ("Media session active" if has_media else
                 "Notification access needed" if connected and phone.get("media_access_granted") is not True else
                 "No active media session")
            )
        if self._home_media_note is not None:
            self._home_media_note.set_text(
                "Enable Link to Linux under Android Settings → Notification access to read and control media."
                if connected and phone.get("media_access_granted") is not True else
                "Start Spotify playback; Android will share the active media session while it is connected."
                if connected else
                "Connect your Android phone to control its active media session."
            )
        for action, button in self._home_media_button_actions.items():
            capability = "media_can_play_pause" if action == "play_pause" else f"media_can_{action}"
            button.set_sensitive(connected and has_media and phone.get(capability) is True)
            if action == "play_pause":
                button.set_label("Pause" if phone.get("media_playing") is True else "Play")
        battery = phone.get("battery_percent")
        total, free = phone.get("storage_total_bytes"), phone.get("storage_free_bytes")
        if "battery_value" in self._home_status_widgets:
            self._home_status_widgets["battery_value"].set_text(f"{battery}%" if isinstance(battery, int) else "—")
            self._home_status_widgets["battery_note"].set_text("Charging" if phone.get("charging") else "Battery level")
            if isinstance(battery, int):
                self._home_status_widgets["battery_bar"].set_fraction(battery / 100)
            if isinstance(total, int) and total > 0 and isinstance(free, int):
                self._home_status_widgets["storage_value"].set_text(f"{free / 1_000_000_000:.1f} GB free")
                self._home_status_widgets["storage_note"].set_text(f"of {total / 1_000_000_000:.1f} GB")
                self._home_status_widgets["storage_bar"].set_fraction(max(0, min(1, free / total)))
            else:
                self._home_status_widgets["storage_value"].set_text("—")
                self._home_status_widgets["storage_note"].set_text("Storage unavailable")
            self._home_status_widgets["model"].set_text(phone.get("model", "Waiting for phone"))
            stamp = phone.get("last_seen")
            age = max(0, int(time.time() - stamp)) if isinstance(stamp, (float, int)) else None
            self._home_status_widgets["last_seen"].set_text("Just now" if connected and (age is None or age < 30) else f"{age}s ago" if age is not None else "Not connected")
        if self._clipboard_status_label is not None:
            both_enabled = self.model.clipboard_service.enabled and phone.get("clipboard_enabled") is True
            self._clipboard_status_label.set_text("Connected · text sharing is enabled on both devices" if connected and both_enabled else "Enable here and on Android to share text" if connected else "Waiting for phone connection")
        return False

    def _status_tick(self) -> bool:
        self._update_home_status()
        return True

    def _on_file_received(self, received: dict) -> None:
        if GLib is not None:
            GLib.idle_add(self._notify_transfer, f"Received {received.get('filename', 'file')}", "The Android phone finished sending this file to the desktop.")
            GLib.idle_add(self._refresh_page, "files")
            if received.get("category") == "photo":
                GLib.idle_add(self._refresh_page, "photos")

    def _on_desktop_file_sent(self, sent: dict) -> None:
        if GLib is not None:
            GLib.idle_add(self._notify_transfer, f"Phone received {sent.get('filename', 'file')}", "The Android phone verified the completed transfer.")
            GLib.idle_add(self._refresh_page, "files")

    def _notify_transfer(self, title: str, body: str) -> None:
        notification = Gio.Notification.new(title)
        notification.set_body(body)
        notification.set_icon(Gio.ThemedIcon.new("folder-download-symbolic"))
        self.application.send_notification(None, notification)
        return False

    def _on_phone_clipboard(self, _device_id: str, text: str) -> None:
        if GLib is not None:
            GLib.idle_add(self._apply_remote_clipboard, text)

    def _on_phone_notification(self, notification: dict) -> None:
        if self.model.notification_service.filter.enabled and GLib is not None:
            GLib.idle_add(self._show_phone_notification, notification)

    def _show_phone_notification(self, notification: dict) -> bool:
        app = notification.get("app_name", "Phone")
        title = notification.get("title", "Notification")
        body = notification.get("body", "")
        item = Gio.Notification.new(f"{app}: {title}")
        if body:
            item.set_body(body)
        item.set_icon(Gio.ThemedIcon.new("preferences-system-notifications-symbolic"))
        self.application.send_notification(None, item)
        return False

    def _on_phone_photos(self, _photos: list[dict]) -> None:
        if GLib is not None:
            GLib.idle_add(self._refresh_page, "photos")

    def _on_photo_preview(self, preview: dict) -> None:
        if GLib is not None:
            GLib.idle_add(self._show_photo_preview, preview)

    def _show_photo_preview(self, preview: dict) -> bool:
        self.model.pairing_server.phone_photos_message = ""
        picture = Gtk.Picture.new_for_filename(preview["path"])
        picture.set_can_shrink(True)
        picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        viewer = Adw.Window(transient_for=self.window, title=preview.get("filename", "Phone photo"))
        viewer.set_default_size(900, 700)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        close_button = Gtk.Button.new_from_icon_name("window-close-symbolic")
        close_button.set_tooltip_text("Close image viewer")
        close_button.connect("clicked", lambda _button: viewer.close())
        header.pack_end(close_button)
        toolbar.add_top_bar(header)
        toolbar.set_content(picture)
        viewer.set_content(toolbar)
        keys = Gtk.EventControllerKey.new()
        keys.connect("key-pressed", lambda _controller, keyval, _keycode, _state: viewer.close() or True if keyval == Gdk.KEY_Escape else False)
        viewer.add_controller(keys)
        viewer.present()
        return False

    def _apply_remote_clipboard(self, text: str) -> bool:
        if self.model.clipboard_service.enabled and self._clipboard is not None:
            self._last_remote_clipboard = text
            self._clipboard.set(text)
            if self._clipboard_status_label is not None:
                self._clipboard_status_label.set_text("Received text from Android clipboard")
        return False

    def _on_local_clipboard_changed(self, clipboard: Any) -> None:
        if not self.model.clipboard_service.enabled or not self.model.pairing_server.session_connected:
            return
        clipboard.read_text_async(None, self._local_clipboard_ready)

    def _local_clipboard_ready(self, clipboard: Any, result: Any) -> None:
        try:
            text = clipboard.read_text_finish(result)
        except Exception:
            return
        if text is None or text == self._last_remote_clipboard:
            self._last_remote_clipboard = ""
            return
        if len(text.encode("utf-8")) <= 64 * 1024:
            self.model.pairing_server.queue_clipboard_text(text)
            self._update_home_status()

    def _refresh_paired_pages(self, device_name: str) -> bool:
        current_page = self.stack.get_visible_child_name() if self.stack is not None else None
        self._refresh_page("home")
        if current_page == "devices" and self._pairing_ui is not None:
            ui = self._pairing_ui
            source_id = ui.get("countdown_source", 0)
            if source_id:
                GLib.source_remove(source_id)
                ui["countdown_source"] = 0
            ui["endpoint_label"].set_text("Address: paired")
            ui["code_label"].set_text("Pairing code: used")
            ui["fingerprint_label"].set_text("Certificate verification: successful")
            ui["qr_image"].clear()
            ui["qr_image"].set_visible(False)
            ui["result_label"].set_text(f"Pairing complete. {device_name} is now trusted. This page will stay open.")
            ui["start_button"].set_sensitive(True)
            ui["stop_button"].set_sensitive(False)
            if self._refresh_trusted_devices is not None:
                self._refresh_trusted_devices()
        else:
            self._refresh_page("devices")
        return False

    def _install_styles(self) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(b"""
            .navigation-sidebar { background-color: @sidebar_bg_color; }
            .navigation-button { border-radius: 10px; min-height: 42px; }
            .navigation-active { background-color: alpha(@accent_color, 0.16); color: @accent_color; }
            .navigation-active label { font-weight: bold; }
            .eyebrow { color: @accent_color; font-weight: bold; }
            .empty-state { padding: 24px; }
        """)
        Gtk.StyleContext.add_provider_for_display(
            self.window.get_display(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _add_pages(self) -> None:
        pages = [
            ("home", "Home", "go-home-symbolic", self._home_page()),
            ("devices", "Devices & pairing", "phone-symbolic", self._devices_page()),
            ("files", "Files", "folder-symbolic", self._files_page()),
            ("photos", "Photos", "image-x-generic-symbolic", self._photos_page()),
            ("notifications", "Notifications", "preferences-system-notifications-symbolic", self._notifications_page()),
            ("clipboard", "Clipboard", "edit-copy-symbolic", self._clipboard_page()),
            ("remote", "Remote input", "input-mouse-symbolic", self._remote_input_page()),
            ("settings", "Settings", "emblem-system-symbolic", self._settings_page()),
            ("about", "About", "help-about-symbolic", self._about_page()),
        ]
        for name, title, icon_name, page in pages:
            self.stack.add_titled(page, name, title)
            self.stack.get_page(page).set_icon_name(icon_name)

    @staticmethod
    def _page(title: str, subtitle: str) -> tuple[Any, Any]:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        page.set_margin_top(44)
        page.set_margin_bottom(28)
        page.set_margin_start(32)
        page.set_margin_end(32)

        heading = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        title_label = Gtk.Label(label=title)
        title_label.add_css_class("title-1")
        title_label.set_xalign(0)
        subtitle_label = Gtk.Label(label=subtitle)
        subtitle_label.add_css_class("dim-label")
        subtitle_label.set_xalign(0)
        subtitle_label.set_wrap(True)
        heading.append(title_label)
        heading.append(subtitle_label)
        page.append(heading)
        return page, heading

    @staticmethod
    def _card(title: str, description: str = "") -> tuple[Any, Any]:
        frame = Gtk.Frame()
        frame.add_css_class("card")
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content.set_margin_top(18)
        content.set_margin_bottom(18)
        content.set_margin_start(18)
        content.set_margin_end(18)
        if title:
            label = Gtk.Label(label=title)
            label.add_css_class("heading")
            label.set_xalign(0)
            content.append(label)
        if description:
            label = Gtk.Label(label=description)
            label.set_xalign(0)
            label.set_wrap(True)
            label.add_css_class("dim-label")
            content.append(label)
        frame.set_child(content)
        return frame, content

    @staticmethod
    def _scroll(page: Any) -> Any:
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_hexpand(True)
        scroll.set_vexpand(True)
        clamp = Adw.Clamp()
        clamp.set_maximum_size(920)
        clamp.set_tightening_threshold(680)
        clamp.set_child(page)
        scroll.set_child(clamp)
        return scroll

    @staticmethod
    def _empty_state(icon_name: str, title: str, detail: str) -> Any:
        frame, content = LinkToLinuxWindow._card("", "")
        content.add_css_class("empty-state")
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(36)
        icon.add_css_class("dim-label")
        heading = Gtk.Label(label=title)
        heading.add_css_class("title-3")
        heading.set_xalign(0)
        detail_label = Gtk.Label(label=detail)
        detail_label.set_xalign(0)
        detail_label.set_wrap(True)
        detail_label.add_css_class("dim-label")
        content.append(icon)
        content.append(heading)
        content.append(detail_label)
        return frame

    def _home_page(self) -> Any:
        page, _ = self._page(
            "Your phone, at a glance",
            "A private desktop companion for the Android features you choose to connect.",
        )
        phone = self.model.phone_status
        connected = self.model.pairing_server.session_connected
        frame, content = self._card("", "")
        content.add_css_class("empty-state")
        eyebrow = Gtk.Label(label="CONNECTION")
        eyebrow.add_css_class("eyebrow")
        eyebrow.set_xalign(0)
        content.append(eyebrow)
        status = Gtk.Label(label=(f"Connected · {phone.get('device_name', self.model.pairing_server.connected_device_name)}" if connected else "Phone disconnected" if phone.get("device_id") else "No phone paired"))
        status.add_css_class("title-2")
        status.set_xalign(0)
        content.append(status)
        self._home_connection_label = status
        message = Gtk.Label(
            label=("The secure phone session is active." if connected else "Open Devices & pairing to connect a phone over the local network.")
        )
        message.set_xalign(0)
        message.set_wrap(True)
        message.add_css_class("dim-label")
        content.append(message)
        self._home_connection_message = message
        ring_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        ring_button = Gtk.Button(label="Ring phone")
        ring_button.add_css_class("suggested-action")
        ring_button.set_sensitive(connected)
        ring_button.connect("clicked", self._toggle_phone_ring)
        ring_actions.append(ring_button)
        ring_status = Gtk.Label(label="Uses the ringtone and volume set on Android.", xalign=0)
        ring_status.add_css_class("dim-label")
        ring_status.set_wrap(True)
        ring_status.set_max_width_chars(48)
        ring_status.set_hexpand(True)
        ring_actions.append(ring_status)
        content.append(ring_actions)
        self._home_ring_button = ring_button
        self._home_ring_status = ring_status
        media_frame, media_content = self._card("Phone media", "Control audio playing on your Android phone.")
        media_title = Gtk.Label(label="No active media session", xalign=0, wrap=True)
        media_title.add_css_class("title-4")
        media_content.append(media_title)
        media_controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        for action_name, label in (("previous", "Previous"), ("play_pause", "Play / pause"), ("next", "Next")):
            button = Gtk.Button(label=label)
            button.set_sensitive(connected)
            button.connect("clicked", lambda _button, value=action_name: self._request_media_control(value))
            media_controls.append(button)
            self._home_media_buttons.append(button)
            self._home_media_button_actions[action_name] = button
        media_content.append(media_controls)
        media_note = Gtk.Label(label="Android notification access is required to read media sessions and send controls.", xalign=0, wrap=True)
        media_note.add_css_class("dim-label")
        media_content.append(media_note)
        self._home_media_label = media_title
        self._home_media_note = media_note
        content.append(media_frame)
        action = Gtk.Button(label="Set up a device")
        action.add_css_class("suggested-action")
        action.set_halign(Gtk.Align.START)
        action.set_label("Manage devices" if connected else "Pair a device")
        action.connect("clicked", lambda _button: self.stack.set_visible_child_name("devices"))
        if not connected:
            content.append(action)
        page.append(frame)

        metrics, metric_content = self._card("Phone status", "Live details from your paired Android phone.")
        grid = Gtk.Grid(column_spacing=16, row_spacing=14)
        grid.set_column_homogeneous(True)
        for column, (key, title) in enumerate((("battery", "BATTERY"), ("storage", "STORAGE"))):
            tile, tile_content = self._card("", "")
            tile_content.set_spacing(6)
            tile_content.set_margin_top(12); tile_content.set_margin_bottom(12)
            eyebrow = Gtk.Label(label=title, xalign=0)
            eyebrow.add_css_class("caption"); eyebrow.add_css_class("dim-label")
            value = Gtk.Label(label="—", xalign=0)
            value.add_css_class("title-2")
            note = Gtk.Label(label="Waiting for connection", xalign=0)
            note.add_css_class("dim-label")
            bar = Gtk.ProgressBar()
            bar.set_fraction(0)
            tile_content.append(eyebrow); tile_content.append(value); tile_content.append(note); tile_content.append(bar)
            grid.attach(tile, column, 0, 1, 1)
            self._home_status_widgets[f"{key}_value"] = value
            self._home_status_widgets[f"{key}_note"] = note
            self._home_status_widgets[f"{key}_bar"] = bar
        details = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        model_label = Gtk.Label(label=phone.get("model", "Waiting for phone"), xalign=0)
        model_label.set_hexpand(True)
        last_seen_label = Gtk.Label(label="Just now" if connected else "Not connected", xalign=1)
        last_seen_label.add_css_class("dim-label")
        details.append(model_label); details.append(last_seen_label)
        grid.attach(details, 0, 1, 2, 1)
        self._home_status_widgets["model"] = model_label
        self._home_status_widgets["last_seen"] = last_seen_label
        metric_content.append(grid)
        self._home_status_label = None
        self._update_home_status()
        device_id = Gtk.Label(label=f"This desktop · {self.model.identity.device_id}", xalign=0)
        device_id.add_css_class("dim-label")
        metric_content.append(device_id)
        page.append(metrics)
        section = Gtk.Label(label="FEATURE AREAS")
        section.add_css_class("caption")
        section.add_css_class("dim-label")
        section.set_xalign(0)
        page.append(section)
        page.append(self._feature_summary())
        return self._scroll(page)

    def _toggle_phone_ring(self, _button: Any) -> None:
        server = self.model.pairing_server
        server.set_phone_ringing(not server.phone_ring_requested)
        self._update_home_status()

    def _request_media_control(self, action: str) -> None:
        self.model.pairing_server.request_media_control(action)

    def _feature_summary(self) -> Any:
        grid = Gtk.Grid(column_spacing=14, row_spacing=14)
        grid.set_column_homogeneous(True)
        entries = [
            ("Files", "Transfer files with explicit access.", "files"),
            ("Photos", "Browse phone media you authorize.", "photos"),
            ("Notifications", "Choose whether to sync notifications.", "notifications"),
            ("Clipboard", "Enable text sharing only when you want it.", "clipboard"),
        ]
        for index, (title, description, target) in enumerate(entries):
            frame, content = self._card(title, description)
            button = Gtk.Button(label="Open")
            button.add_css_class("flat")
            button.set_halign(Gtk.Align.START)
            button.connect("clicked", lambda _button, page=target: self.stack.set_visible_child_name(page))
            content.append(button)
            grid.attach(frame, index % 2, index // 2, 1, 1)
        return grid

    def _devices_page(self) -> Any:
        page, _ = self._page(
            "Devices & pairing",
            "Create a short-lived, encrypted pairing session for the Android app on your local Wi-Fi network.",
        )
        form, content = self._card(
            "Pair an Android phone",
            "Keep both devices on the same trusted network. The APK verifies this desktop's certificate before sending the one-time code. Start the listener to show the address, fingerprint, and code. The code expires after three minutes or one successful pairing.",
        )
        endpoint_label = Gtk.Label(label="Address: not started", xalign=0)
        endpoint_label.set_selectable(True)
        code_label = Gtk.Label(label="Pairing code: —", xalign=0)
        code_label.set_selectable(True)
        fingerprint_label = Gtk.Label(label="Certificate SHA-256: —", xalign=0, wrap=True)
        fingerprint_label.set_selectable(True)
        qr_image = Gtk.Image()
        qr_image.set_visible(False)
        qr_image.set_pixel_size(240)
        qr_image.set_halign(Gtk.Align.START)
        content.append(endpoint_label)
        content.append(code_label)
        content.append(fingerprint_label)
        content.append(qr_image)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        start_button = Gtk.Button(label="Start pairing")
        start_button.add_css_class("suggested-action")
        stop_button = Gtk.Button(label="Stop")
        stop_button.set_sensitive(False)
        actions.append(start_button)
        actions.append(stop_button)
        content.append(actions)
        result_label = Gtk.Label(label="The listener is off until you start pairing.", xalign=0, wrap=True)
        content.append(result_label)
        countdown_source = 0
        self._pairing_ui = {
            "endpoint_label": endpoint_label,
            "code_label": code_label,
            "fingerprint_label": fingerprint_label,
            "qr_image": qr_image,
            "result_label": result_label,
            "start_button": start_button,
            "stop_button": stop_button,
            "countdown_source": 0,
        }

        def update_countdown() -> bool:
            advertisement = self.model.pairing_server.advertisement
            if advertisement is None:
                endpoint_label.set_text("Address: not started")
                code_label.set_text("Pairing code: —")
                fingerprint_label.set_text("Certificate SHA-256: —")
                qr_image.clear()
                qr_image.set_visible(False)
                result_label.set_text("Pairing session ended or expired. Start a new session and scan its new QR code.")
                start_button.set_sensitive(True)
                stop_button.set_sensitive(False)
                self._pairing_ui["countdown_source"] = 0
                return False
            remaining = max(0, int(advertisement.expires_at - time.time() + 0.999))
            code_label.set_text(f"Pairing code: {advertisement.code} · expires in {remaining // 60}:{remaining % 60:02d}")
            return True

        def start_pairing(_button: Any) -> None:
            nonlocal countdown_source
            try:
                advertisement = self.model.pairing_server.start()
            except (OSError, RuntimeError) as error:
                result_label.set_text(f"Could not start pairing: {error}")
                return
            endpoint_label.set_text(f"Address: {advertisement.host}:{advertisement.port}")
            code_label.set_text(f"Pairing code: {advertisement.code} · expires in 3:00")
            fingerprint = ":".join(
                advertisement.fingerprint[index:index + 2].upper()
                for index in range(0, len(advertisement.fingerprint), 2)
            )
            fingerprint_label.set_text(f"Certificate SHA-256: {fingerprint}")
            pairing_qr = {
                "kind": "linktolinux.pair",
                "version": 1,
                "host": advertisement.host,
                "port": advertisement.port,
                "code": advertisement.code,
                "fingerprint": advertisement.fingerprint,
            }
            pairing_uri = "linktolinux://pair?" + urlencode({key: value for key, value in pairing_qr.items() if key != "kind"})
            try:
                import segno

                qr_bytes = io.BytesIO()
                segno.make(pairing_uri).save(
                    qr_bytes, kind="png", scale=7, border=3
                )
                loader = GdkPixbuf.PixbufLoader.new_with_type("png")
                loader.write(qr_bytes.getvalue())
                loader.close()
                qr_image.set_from_pixbuf(loader.get_pixbuf())
                qr_image.set_visible(True)
                result_label.set_text("Scan with the Link to Linux app or your phone camera. The one-time code expires in 3 minutes.")
            except Exception as error:
                qr_image.set_visible(False)
                result_label.set_text(f"QR code unavailable ({error}). Enter the address, code, and fingerprint manually.")
            start_button.set_sensitive(False)
            stop_button.set_sensitive(True)
            if countdown_source:
                GLib.source_remove(countdown_source)
            countdown_source = GLib.timeout_add_seconds(1, update_countdown)
            self._pairing_ui["countdown_source"] = countdown_source

        def stop_pairing(_button: Any) -> None:
            nonlocal countdown_source
            self.model.pairing_server.stop()
            if countdown_source:
                GLib.source_remove(countdown_source)
                countdown_source = 0
                self._pairing_ui["countdown_source"] = 0
            endpoint_label.set_text("Address: not started")
            code_label.set_text("Pairing code: —")
            fingerprint_label.set_text("Certificate SHA-256: —")
            qr_image.clear()
            qr_image.set_visible(False)
            result_label.set_text("Pairing listener stopped.")
            start_button.set_sensitive(True)
            stop_button.set_sensitive(False)

        start_button.connect("clicked", start_pairing)
        stop_button.connect("clicked", stop_pairing)
        page.append(form)
        trusted_slot = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        def refresh_trusted_devices() -> None:
            child = trusted_slot.get_first_child()
            while child is not None:
                trusted_slot.remove(child)
                child = trusted_slot.get_first_child()
            trusted_slot.append(self._paired_devices_card())

        self._refresh_trusted_devices = refresh_trusted_devices
        refresh_trusted_devices()
        page.append(trusted_slot)
        return self._scroll(page)

    def _paired_devices_card(self) -> Any:
        frame, content = self._card("Trusted devices", "Revoke a device to remove it from the local trusted list.")
        devices = sorted(self.model.settings.paired_devices)
        if not devices:
            content.append(Gtk.Label(label="No trusted devices yet.", xalign=0))
            return frame
        for device_id in devices:
            device_name = self.model.pairing_server.trusted_devices.get(device_id, {}).get("name", device_id)
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            label = Gtk.Label(label=f"{device_name} · saved for automatic reconnect", xalign=0)
            label.set_hexpand(True)
            revoke = Gtk.Button(label="Revoke")

            def revoke_device(_button: Any, trusted_id: str = device_id) -> None:
                self.model.revoke_device(trusted_id)
                self._refresh_page("devices")
                self._refresh_page("home")

            revoke.connect("clicked", revoke_device)
            row.append(label)
            row.append(revoke)
            content.append(row)
        return frame

    def _files_page(self) -> Any:
        page, _ = self._page(
            "Files",
            "Browse and transfer files only after the phone grants access through Android's system file picker.",
        )
        received = self.model.received_files
        if not received:
            page.append(self._empty_state("folder-symbolic", "No files received", "Choose files in the Android app and send them here. Transfers are saved to your configured Downloads folder."))
        for item in received:
            frame, content = self._card(item["filename"], f"{item.get('device_name', 'Android phone')} · {item.get('size_bytes', 0) / 1_000_000:.2f} MB · {item.get('category', 'file').title()}")
            open_button = Gtk.Button(label="Open file")
            open_button.set_halign(Gtk.Align.START)
            open_button.connect("clicked", lambda _button, path=item["path"]: Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(path).get_uri(), None))
            content.append(open_button)
            page.append(frame)
        outgoing, outgoing_content = self._card("Send files to your phone", "Choose files on this desktop. They will appear in the Android app for the user to accept and save.")
        choose_files = Gtk.Button(label="Choose files")
        choose_files.add_css_class("suggested-action")
        choose_files.set_halign(Gtk.Align.START)
        queue_status = Gtk.Label(label="Files will wait here until a phone connects." if not self.model.pairing_server.session_connected else "Ready to send · maximum 256 MB per file", xalign=0)
        queue_status.add_css_class("dim-label")
        outgoing_content.append(choose_files)
        outgoing_content.append(queue_status)
        with self.model.pairing_server._desktop_files_lock:
            queued = list(self.model.pairing_server.pending_desktop_files.values())
        for offer in queued:
            outgoing_content.append(Gtk.Label(label=f"Waiting for phone: {offer['filename']}", xalign=0))

        def open_file_picker(_button: Any) -> None:
            dialog = Gtk.FileChooserNative.new(
                "Choose files to send", self.window, Gtk.FileChooserAction.OPEN, "Send", "Cancel"
            )
            dialog.set_select_multiple(True)

            def chosen(native: Any, response: int) -> None:
                if response == Gtk.ResponseType.ACCEPT:
                    files = native.get_files()
                    for index in range(files.get_n_items()):
                        selected = files.get_item(index)
                        path = selected.get_path() if selected is not None else None
                        if path is None:
                            queue_status.set_text("Choose files stored on this computer.")
                            continue
                        try:
                            self.model.pairing_server.queue_desktop_file(path)
                        except (OSError, ValueError) as error:
                            queue_status.set_text(str(error))
                    self._refresh_page("files")
                native.destroy()

            dialog.connect("response", chosen)
            dialog.show()

        choose_files.connect("clicked", open_file_picker)
        page.append(outgoing)
        history, history_content = self._card("Transfer history")
        history_content.append(Gtk.Label(label="Completed and cancelled transfers will appear here.", xalign=0))
        page.append(history)
        return self._scroll(page)

    def _photos_page(self) -> Any:
        page, _ = self._page(
            "Photos",
            "Browse recent phone photos over the encrypted connection. Android asks for photo access before sharing thumbnails.",
        )
        load = Gtk.Button(label="Refresh from phone")
        load.set_icon_name("view-refresh-symbolic")
        load.add_css_class("suggested-action")
        load.set_halign(Gtk.Align.START)
        load.set_sensitive(self.model.pairing_server.session_connected)
        def request_photos(_button: Any) -> None:
            self.model.enable_photo_auto_load()
            self.model.pairing_server.request_phone_photos()
            self._refresh_page("photos")

        load.connect("clicked", request_photos)
        page.append(load)
        status_text = self.model.pairing_server.phone_photos_message
        if not self.model.pairing_server.session_connected and self.model.phone_photos:
            status_text = f"Showing {len(self.model.phone_photos)} previously loaded photos. They will refresh automatically when the phone reconnects."
        elif self.model.pairing_server.session_connected and self.model.settings.auto_load_phone_photos and not status_text:
            status_text = "Photo refresh is enabled for this desktop. Recent photos load when the phone connects."
        if status_text:
            status = Gtk.Label(label=status_text, xalign=0, wrap=True)
            status.add_css_class("dim-label")
            page.append(status)
        if not self.model.pairing_server.session_connected:
            page.append(self._empty_state("phone-symbolic", "Phone disconnected", "Previously loaded thumbnails stay visible. Reconnect the phone to refresh or open originals."))
        elif not self.model.phone_photos:
            page.append(self._empty_state("image-x-generic-symbolic", "No phone photos loaded", "Choose Refresh from phone. Approve photo access in Android if asked."))
        for photo in self.model.phone_photos:
            frame, content = self._card(photo["name"], "Recent photo on the paired Android phone")
            try:
                loader = GdkPixbuf.PixbufLoader.new()
                loader.write(base64.b64decode(photo["thumbnail"], validate=True))
                loader.close()
                picture = Gtk.Picture.new_for_pixbuf(loader.get_pixbuf())
                picture.set_can_shrink(True)
                picture.set_size_request(240, 180)
                picture.set_content_fit(Gtk.ContentFit.CONTAIN)
                content.append(picture)
            except Exception:
                content.append(Gtk.Label(label="Thumbnail unavailable", xalign=0))
            actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            view = Gtk.Button(label="View")
            view.add_css_class("suggested-action")
            save = Gtk.Button(label="Save to desktop")

            def request_photo(mode: str, filename: str, media_id: str = photo["id"]) -> None:
                self.model.pairing_server.request_phone_photo(media_id, mode)
                self.model.pairing_server.phone_photos_message = f"Loading {filename} from phone…"
                self._refresh_page("photos")

            view.connect("clicked", lambda _button, name=photo["name"], media_id=photo["id"]: request_photo("view", name, media_id))
            save.connect("clicked", lambda _button, name=photo["name"], media_id=photo["id"]: request_photo("save", name, media_id))
            actions.append(view)
            actions.append(save)
            content.append(actions)
            page.append(frame)
        photos = [item for item in self.model.received_files if item.get("category") == "photo"]
        if photos:
            section = Gtk.Label(label="Saved on this desktop", xalign=0)
            section.add_css_class("heading")
            page.append(section)
        for item in photos:
            frame, content = self._card(item["filename"], f"Received from {item.get('device_name', 'Android phone')}")
            try:
                picture = Gtk.Picture.new_for_filename(item["path"])
                picture.set_can_shrink(True)
                picture.set_size_request(240, 160)
                picture.set_content_fit(Gtk.ContentFit.CONTAIN)
                content.append(picture)
            except Exception:
                pass
            page.append(frame)
        return self._scroll(page)

    def _notifications_page(self) -> Any:
        page, _ = self._page(
            "Notifications",
            "Notification content is private. Sync is opt-in and will require notification-listener authorization on Android.",
        )
        frame, content = self._card("Notification sync")
        enabled = Gtk.CheckButton(label="Enable notification synchronization")
        enabled.set_active(self.model.notification_service.filter.enabled)
        enabled.connect("toggled", self._notification_toggled)
        content.append(enabled)
        availability = Gtk.Label(label="This preference is saved on this desktop. Enable notification sharing and Android notification access on the phone too. Only app name, title, and text are forwarded.", wrap=True)
        availability.add_css_class("caption")
        availability.add_css_class("dim-label")
        availability.set_xalign(0)
        content.append(availability)
        content.append(
            Gtk.Label(
                label="Incoming Android notifications appear as desktop notifications while this app is open.",
                xalign=0,
                wrap=True,
            )
        )
        page.append(frame)
        apps, apps_content = self._card("Allowed apps", "App filters can be managed after an Android connection is available.")
        apps_content.append(Gtk.Label(label="No apps selected.", xalign=0))
        page.append(apps)
        return self._scroll(page)

    def _notification_toggled(self, button: Any) -> None:
        self.model.set_notifications_enabled(button.get_active())

    def _clipboard_page(self) -> Any:
        page, _ = self._page(
            "Shared clipboard",
            "Share plain text over the encrypted connection when clipboard sharing is enabled on both devices.",
        )
        frame, content = self._card("Clipboard synchronization")
        enabled = Gtk.CheckButton(label="Enable text clipboard synchronization")
        enabled.set_active(self.model.clipboard_service.enabled)
        enabled.connect("toggled", self._clipboard_toggled)
        content.append(enabled)
        availability = Gtk.Label(label="Waiting for an active phone connection")
        availability.add_css_class("caption")
        availability.add_css_class("dim-label")
        availability.set_xalign(0)
        content.append(availability)
        content.append(
            Gtk.Label(
                label="Android can send copied text while Link to Linux is open. Desktop text is delivered on the next secure phone update.",
                xalign=0,
                wrap=True,
            )
        )
        self._clipboard_status_label = availability
        page.append(frame)
        return self._scroll(page)

    def _clipboard_toggled(self, button: Any) -> None:
        self.model.set_clipboard_enabled(button.get_active())
        if button.get_active():
            self._read_desktop_clipboard_for_phone()
        else:
            self.model.pairing_server.queue_clipboard_text(None)
            if self._clipboard_status_label is not None:
                self._clipboard_status_label.set_text("Clipboard sharing is off")
        self._update_home_status()

    def _remote_input_page(self) -> Any:
        page, _ = self._page(
            "Remote input",
            "Use your paired Android phone as a touchpad and keyboard for this Linux desktop.",
        )
        frame, content = self._card("Phone control")
        available = self.model.remote_input.available
        enabled = Gtk.CheckButton(label="Allow remote input from the paired phone")
        enabled.set_active(self.model.settings.remote_input_enabled and available)
        enabled.set_sensitive(available)
        enabled.connect("toggled", lambda button: self.model.set_remote_input_enabled(button.get_active()))
        content.append(enabled)
        detail = Gtk.Label(label=self.model.remote_input.description, xalign=0, wrap=True)
        detail.add_css_class("dim-label")
        content.append(detail)
        content.append(Gtk.Label(
            label="Remote input starts disabled. Turn it on here before using the Remote page on Android. The connection is encrypted and limited to the currently paired phone.",
            xalign=0,
            wrap=True,
        ))
        recheck = Gtk.Button(label="Recheck input backend")
        recheck.set_halign(Gtk.Align.START)
        recheck.connect("clicked", lambda _button: self._refresh_page("remote"))
        content.append(recheck)
        page.append(frame)
        return self._scroll(page)

    def _read_desktop_clipboard_for_phone(self) -> None:
        if self._clipboard is not None:
            self._clipboard.read_text_async(None, self._local_clipboard_ready)

    def _settings_page(self) -> Any:
        page, _ = self._page("Settings", "Choose where downloads should be saved and manage optional features.")
        downloads, content = self._card("Download location")
        location_label = Gtk.Label(label=self.model.settings.download_directory, xalign=0)
        location_label.set_selectable(True)
        content.append(location_label)
        choose_button = Gtk.Button(label="Choose folder")
        choose_button.set_halign(Gtk.Align.START)
        content.append(choose_button)

        def choose_folder(_button: Any) -> None:
            dialog = Gtk.FileChooserNative.new(
                "Choose download folder",
                self.window,
                Gtk.FileChooserAction.SELECT_FOLDER,
                "Select",
                "Cancel",
            )

            def on_response(chooser: Any, response: int) -> None:
                if response == Gtk.ResponseType.ACCEPT:
                    selected = chooser.get_file()
                    if selected is not None and selected.get_path():
                        self.model.set_download_directory(selected.get_path())
                        location_label.set_text(selected.get_path())
                chooser.destroy()

            dialog.connect("response", on_response)
            dialog.show()

        choose_button.connect("clicked", choose_folder)
        page.append(downloads)

        privacy, privacy_content = self._card("Privacy & security")
        privacy_content.append(Gtk.Label(label="Trusted devices: explicit local pairing required", xalign=0))
        privacy_content.append(Gtk.Label(label="Wi-Fi and ADB transports: not yet connected", xalign=0))
        privacy_content.append(Gtk.Label(label="Credential storage: platform keyring integration not yet configured", xalign=0))
        page.append(privacy)
        return self._scroll(page)

    def _about_page(self) -> Any:
        from linktolinux import __version__

        page, _ = self._page(
            "About Link to Linux",
            "A desktop companion for bringing selected Android features to your Linux computer.",
        )
        frame, content = self._card("Link to Linux", f"Version {__version__}")
        content.append(Gtk.Label(
            label="Link to Linux is being built to make phone and desktop workflows feel simple, private, and user controlled.",
            xalign=0,
            wrap=True,
        ))
        content.append(Gtk.Label(
            label="Link to Linux connects paired Android phones over your local network. File transfers, phone status, photo browsing, notifications, and clipboard sync are opt-in and require the related Android permission.",
            xalign=0,
            wrap=True,
        ))
        content.append(Gtk.Label(label="Made with Python, GTK 4, and libadwaita.", xalign=0))
        page.append(frame)

        creator, creator_content = self._card("Built by Young Jay", "An independent project from YoungTechSperts.")
        creator_content.append(Gtk.Label(
            label="YoungTechSperts builds practical software and digital projects.", xalign=0, wrap=True
        ))
        github_link = Gtk.LinkButton.new_with_label("https://github.com/Youngjay42-real", "GitHub profile")
        github_link.set_halign(Gtk.Align.START)
        creator_content.append(github_link)
        page.append(creator)

        projects, project_content = self._card("More projects", "Explore YoungAI and other work.")
        youngai_link = Gtk.LinkButton.new_with_label("https://youngai.site", "Visit youngai.site")
        youngai_link.set_halign(Gtk.Align.START)
        project_content.append(youngai_link)
        page.append(projects)
        return self._scroll(page)

    def _refresh_page(self, name: str) -> None:
        if self.stack is None:
            return
        builders = {
            "home": self._home_page,
            "devices": self._devices_page,
            "files": self._files_page,
            "photos": self._photos_page,
            "remote": self._remote_input_page,
        }
        current = self.stack.get_visible_child_name()
        if name not in builders:
            return
        child = self.stack.get_child_by_name(name)
        if child is not None:
            self.stack.remove(child)
        title = {
            "home": "Home",
            "devices": "Devices & pairing",
            "files": "Files",
            "photos": "Photos",
            "remote": "Remote input",
        }[name]
        page = builders[name]()
        self.stack.add_titled(page, name, title)
        self.stack.get_page(page).set_icon_name({
            "home": "go-home-symbolic",
            "devices": "phone-symbolic",
            "files": "folder-symbolic",
            "photos": "image-x-generic-symbolic",
            "remote": "input-mouse-symbolic",
        }[name])
        if current == name:
            self.stack.set_visible_child_name(name)
