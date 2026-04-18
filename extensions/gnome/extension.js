'use strict';

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Meta from 'gi://Meta';
import St from 'gi://St';
import Clutter from 'gi://Clutter';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

const TRACKER_BUS_NAME = 'org.waid.WindowTracker';
const TRACKER_OBJECT_PATH = '/org/waid/WindowTracker';
const DAEMON_BUS_NAME = 'org.waid.Daemon';
const DAEMON_OBJECT_PATH = '/org/waid/Daemon';
const DAEMON_INTERFACE = 'org.waid.Daemon';

const PANEL_KIND_CLASSIFIED = 'classified';
const PANEL_KIND_UNCLASSIFIED = 'unclassified';
const PANEL_KIND_DISCONNECTED = 'disconnected';
const PANEL_KIND_PAUSED = 'paused';
const UNCLASSIFIED_ICON = 'help-about-symbolic';
const DISCONNECTED_ICON = 'network-offline-symbolic';
const PAUSED_ICON = 'media-playback-pause-symbolic';

const STATE_DIR = GLib.build_filenamev([GLib.get_home_dir(), '.local', 'state', 'waid']);
const STATUS_FILE = GLib.build_filenamev([STATE_DIR, 'status.json']);
const CONFIG_FILE = GLib.build_filenamev([GLib.get_home_dir(), '.config', 'waid', 'config.yaml']);
const REPORT_INTERVAL_SECONDS = 30;

const TRACKER_IFACE = `
<node>
  <interface name="${TRACKER_BUS_NAME}">
    <method name="GetSnapshot">
      <arg name="revision" type="u" direction="out"/>
      <arg name="state_json" type="s" direction="out"/>
    </method>
    <signal name="StateChanged">
      <arg name="revision" type="u"/>
      <arg name="state_json" type="s"/>
    </signal>
  </interface>
</node>`;

const StatusIndicator = GObject.registerClass(
class StatusIndicator extends PanelMenu.Button {
    _init() {
        super._init(0.0, 'waid', false);
        this._box = new St.BoxLayout({style_class: 'panel-status-menu-box'});
        this._icon = new St.Icon({icon_name: DISCONNECTED_ICON, style_class: 'system-status-icon'});
        this._label = new St.Label({text: PANEL_KIND_DISCONNECTED, y_align: Clutter.ActorAlign.CENTER});
        this._box.add_child(this._icon);
        this._box.add_child(this._label);
        this.add_child(this._box);
        // Placeholder keeps the menu non-empty so GNOME Shell will open it.
        // It is replaced by _rebuildMenu() on every open.
        // Do NOT set sensitive=false — that makes the item invisible in GNOME Shell,
        // causing isEmpty()=true and the menu refusing to open.
        this._placeholder = new PopupMenu.PopupMenuItem('Loading…');
        this.menu.addMenuItem(this._placeholder);
    }

    setStatus(label, iconName) {
        this._icon.icon_name = iconName || DISCONNECTED_ICON;
        this._label.text = label || PANEL_KIND_DISCONNECTED;
        this._label.visible = true;
    }
});

export default class WaidExtension extends Extension {
    enable() {
        this._enabled = true;
        this._signals = [];
        this._daemonOnBus = false;
        this._daemonWatchId = 0;
        this._statusMonitor = null;
        this._statusMonitorSignalId = 0;
        this._reportSourceId = 0;
        this._currentStatus = null;
        this._trackerRevision = 0;
        this._trackerStateJson = '';
        this._titleWatchSignalId = null;
        this._titleWatchWindow = null;
        this._trackingEnabled = true;
        this._updateTrackerSnapshot({emitSignal: false});

        this._dbusImpl = Gio.DBusExportedObject.wrapJSObject(TRACKER_IFACE, this);
        this._dbusImpl.export(Gio.DBus.session, TRACKER_OBJECT_PATH);
        this._nameOwnerId = Gio.bus_own_name_on_connection(
            Gio.DBus.session,
            TRACKER_BUS_NAME,
            Gio.BusNameOwnerFlags.NONE,
            null,
            null
        );

        this._indicator = new StatusIndicator();
        Main.panel.addToStatusArea(this.uuid, this._indicator);
        this._setDisconnected();

        this._indicator.menu.connect('open-state-changed', (_menu, isOpen) => {
            if (isOpen) this._rebuildMenu();
        });

        this._signals.push([global.display, global.display.connect('notify::focus-window', () => {
            this._setupTitleWatcher();
            this._emitStateChanged();
        })]);
        this._signals.push([global.workspace_manager, global.workspace_manager.connect('active-workspace-changed', () => this._emitStateChanged())]);
        if (Main.screenShield) {
            this._signals.push([Main.screenShield, Main.screenShield.connect('notify::locked', () => this._emitStateChanged())]);
        }

        this._watchDaemon();
        this._startFileMonitoring();
        this._startPeriodicReporting();
        this._setupTitleWatcher();
    }

    disable() {
        this._enabled = false;
        this._cleanupTitleWatcher();
        if (this._signals) {
            for (const [obj, id] of this._signals) {
                try { obj.disconnect(id); } catch (_) {}
            }
        }
        this._signals = [];
        if (this._statusMonitor) {
            if (this._statusMonitorSignalId) {
                this._statusMonitor.disconnect(this._statusMonitorSignalId);
                this._statusMonitorSignalId = 0;
            }
            this._statusMonitor.cancel();
            this._statusMonitor = null;
        }
        if (this._reportSourceId) {
            GLib.source_remove(this._reportSourceId);
            this._reportSourceId = 0;
        }
        if (this._nameOwnerId) {
            Gio.bus_unown_name(this._nameOwnerId);
            this._nameOwnerId = null;
        }
        if (this._daemonWatchId) {
            Gio.bus_unwatch_name(this._daemonWatchId);
            this._daemonWatchId = 0;
        }
        if (this._dbusImpl) {
            this._dbusImpl.unexport();
            this._dbusImpl = null;
        }
        if (this._indicator) {
            this._indicator.destroy();
            this._indicator = null;
        }
    }

    // --- Title change tracking for focused window ---

    _setupTitleWatcher() {
        this._cleanupTitleWatcher();
        const focused = global.display.focus_window;
        if (!focused) return;
        this._titleWatchWindow = focused;
        this._titleWatchSignalId = focused.connect('notify::title', () => {
            this._emitStateChanged();
        });
    }

    _cleanupTitleWatcher() {
        if (this._titleWatchSignalId && this._titleWatchWindow) {
            try {
                this._titleWatchWindow.disconnect(this._titleWatchSignalId);
            } catch (_) {}
        }
        this._titleWatchSignalId = null;
        this._titleWatchWindow = null;
    }

    // --- Periodic reporting timer ---

    _startPeriodicReporting() {
        this._reportSourceId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, REPORT_INTERVAL_SECONDS, () => {
            if (!this._enabled) return GLib.SOURCE_REMOVE;
            this._emitStateChanged();
            return GLib.SOURCE_CONTINUE;
        });
    }

    // --- File monitoring ---

    _startFileMonitoring() {
        this._readStatusFile();
        try {
            const file = Gio.File.new_for_path(STATUS_FILE);
            this._statusMonitor = file.monitor_file(Gio.FileMonitorFlags.NONE, null);
            this._statusMonitorSignalId = this._statusMonitor.connect('changed', (monitor, f, otherFile, eventType) => {
                if (eventType === Gio.FileMonitorEvent.CHANGES_DONE_HINT ||
                    eventType === Gio.FileMonitorEvent.CREATED) {
                    this._readStatusFile();
                }
            });
        } catch (e) {
            logError(e, `${this.uuid}: failed to setup file monitor`);
        }
    }

    _readStatusFile() {
        try {
            const [ok, contents] = GLib.file_get_contents(STATUS_FILE);
            if (!ok) {
                this._setDisconnected();
                return;
            }
            const text = new TextDecoder().decode(contents);
            const status = JSON.parse(text);
            this._applyFileStatus(status);
        } catch (_) {
            this._setDisconnected();
        }
    }

    _applyFileStatus(status) {
        if (!status || !status.kind) {
            this._setDisconnected();
            return;
        }
        this._currentStatus = status;
        if (status.kind === PANEL_KIND_CLASSIFIED) {
            this._indicator.setStatus(
                status.display_label || status.path || PANEL_KIND_CLASSIFIED,
                status.icon_name
            );
        } else if (status.kind === PANEL_KIND_UNCLASSIFIED) {
            this._indicator.setStatus(status.display_label || PANEL_KIND_UNCLASSIFIED, status.icon_name || UNCLASSIFIED_ICON);
        } else if (status.kind === PANEL_KIND_PAUSED) {
            this._indicator.setStatus(status.display_label || PANEL_KIND_PAUSED, status.icon_name || PAUSED_ICON);
        } else {
            this._setDisconnected();
        }
    }

    _setDisconnected() {
        if (this._indicator) {
            this._indicator.setStatus(PANEL_KIND_DISCONNECTED, DISCONNECTED_ICON);
        }
    }

    // --- Daemon presence watch (lightweight, no proxy) ---

    _watchDaemon() {
        this._daemonWatchId = Gio.bus_watch_name(
            Gio.BusType.SESSION,
            DAEMON_BUS_NAME,
            Gio.BusNameWatcherFlags.NONE,
            () => { this._daemonOnBus = true; },
            () => {
                this._daemonOnBus = false;
                this._setDisconnected();
            }
        );
    }

    _requestRefresh() {
        this._callDaemon('ReloadConfig');
    }

    _setTracking(enabled) {
        const params = GLib.Variant.new_tuple([GLib.Variant.new_boolean(enabled)]);
        this._callDaemon('SetTracking', params);
    }

    _callDaemon(method, params = null) {
        Gio.DBus.session.call(
            DAEMON_BUS_NAME,
            DAEMON_OBJECT_PATH,
            DAEMON_INTERFACE,
            method,
            params,
            null,
            Gio.DBusCallFlags.NONE,
            -1,
            null,
            (connection, result) => {
                try { connection.call_finish(result); } catch (e) {
                    logError(e, `${this.uuid}: ${method} failed`);
                }
            }
        );
    }

    // --- Rich popup menu ---

    _rebuildMenu() {
        try {
            this._rebuildMenuImpl();
        } catch (err) {
            logError(err, `${this.uuid}: _rebuildMenu failed`);
            // Ensure menu is never left empty
            this._indicator.menu.removeAll();
            const errItem = new PopupMenu.PopupMenuItem(`Error: ${err.message}`);
            errItem.sensitive = false;
            this._indicator.menu.addMenuItem(errItem);
        }
    }

    _rebuildMenuImpl() {
        this._indicator.menu.removeAll();

        // Header: current activity
        const status = this._currentStatus;
        const headerItem = new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});
        const headerIcon = new St.Icon({
            icon_name: (status && status.icon_name) || DISCONNECTED_ICON,
            style_class: 'waid-header-icon',
        });
        const headerLabel = new St.Label({
            text: this._currentActivityLabel(),
            style_class: 'waid-header-label',
            x_expand: true,
            y_align: Clutter.ActorAlign.CENTER,
        });
        const headerBox = new St.BoxLayout({vertical: true, x_expand: true});
        headerBox.add_child(headerLabel);
        const taskLabelText = this._currentTaskLabel();
        if (taskLabelText) {
            headerBox.add_child(new St.Label({
                text: taskLabelText,
                style_class: 'waid-header-task-label',
                x_expand: true,
                y_align: Clutter.ActorAlign.CENTER,
            }));
        }
        headerItem.add_child(headerIcon);
        headerItem.add_child(headerBox);
        this._indicator.menu.addMenuItem(headerItem);

        // Today's stats from daemon payload
        this._indicator.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem('Today'));
        const rows = Array.isArray(this._currentStatus?.display_rows)
            ? this._currentStatus.display_rows
            : [];
        let total = 0;

        if (rows.length > 0) {
            for (const row of rows) {
                total += row.seconds || 0;
                this._addDisplayRow(row);
            }
        } else {
            const emptyItem = new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});
            emptyItem.add_child(new St.Label({
                text: 'No activities or tasks configured',
                y_align: Clutter.ActorAlign.CENTER,
            }));
            this._indicator.menu.addMenuItem(emptyItem);
        }
        
        // Total row
        const totalItem = new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});
        const totalLabel = new St.Label({
            text: 'Total',
            style_class: 'waid-total-label',
            x_expand: true,
            y_align: Clutter.ActorAlign.CENTER,
        });
        const totalDur = new St.Label({
            text: this._formatDuration(total),
            style_class: 'waid-total-duration',
            y_align: Clutter.ActorAlign.CENTER,
        });
        totalItem.add_child(totalLabel);
        totalItem.add_child(totalDur);
        this._indicator.menu.addMenuItem(totalItem);

        // Actions
        this._indicator.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        const refreshItem = new PopupMenu.PopupMenuItem('Reload Catalog');
        refreshItem.connect('activate', () => this._requestRefresh());
        this._indicator.menu.addMenuItem(refreshItem);

        const configItem = new PopupMenu.PopupMenuItem('Open Config');
        configItem.connect('activate', () => {
            try {
                const uri = GLib.filename_to_uri(CONFIG_FILE, null);
                Gio.AppInfo.launch_default_for_uri(uri, null);
            } catch (e) {
                logError(e, `${this.uuid}: failed to open config`);
            }
        });
        this._indicator.menu.addMenuItem(configItem);

        const isPaused = this._currentStatus && this._currentStatus.kind === PANEL_KIND_PAUSED;
        const trackingItem = new PopupMenu.PopupMenuItem(isPaused ? 'Resume Tracking' : 'Pause Tracking');
        trackingItem.connect('activate', () => this._setTracking(!isPaused));
        this._indicator.menu.addMenuItem(trackingItem);
    }

    _currentActivityLabel() {
        const s = this._currentStatus;
        if (!s) return PANEL_KIND_DISCONNECTED;
        if (s.path) return s.path;
        if (s.display_label) return s.display_label;
        if (s.kind === PANEL_KIND_CLASSIFIED) return s.path || PANEL_KIND_CLASSIFIED;
        if (s.kind === PANEL_KIND_UNCLASSIFIED) return PANEL_KIND_UNCLASSIFIED;
        if (s.kind === PANEL_KIND_PAUSED) return PANEL_KIND_PAUSED;
        return PANEL_KIND_DISCONNECTED;
    }

    _currentTaskLabel() {
        const s = this._currentStatus;
        return s && s.task_path ? s.task_path : '';
    }

    _addDisplayRow(row) {
        const item = new PopupMenu.PopupMenuItem('');
        item.add_style_class_name('waid-stat-row');
        item.sensitive = false;

        if (row.is_selected) {
            item.add_style_class_name('waid-selected-row');
        }

        if (row.is_legacy) {
            item.add_style_class_name('waid-legacy-row');
        }

        if (row.icon_name) {
            const catIcon = new St.Icon({
                icon_name: row.icon_name,
                style_class: 'waid-stat-icon popup-menu-icon',
            });
            item.add_child(catIcon);
        } else {
            item.add_child(new St.Widget({width: 20}));
        }
        
        const nameLabel = new St.Label({
            text: row.label || row.path || '',
            style_class: row.is_selected ? 'waid-selected-label' : '',
            x_expand: true,
            y_align: Clutter.ActorAlign.CENTER,
        });
        
        const durLabel = new St.Label({
            text: this._formatDuration(row.seconds || 0),
            style_class: 'waid-duration',
            y_align: Clutter.ActorAlign.CENTER,
        });
        
        item.add_child(nameLabel);
        item.add_child(durLabel);
        
        this._indicator.menu.addMenuItem(item);
    }

    _formatDuration(seconds) {
        const totalMinutes = Math.round(seconds / 60);
        if (totalMinutes < 1) return '<1m';
        const hours = Math.floor(totalMinutes / 60);
        const minutes = totalMinutes % 60;
        if (hours === 0) return `${minutes}m`;
        if (minutes === 0) return `${hours}h`;
        return `${hours}h ${minutes}m`;
    }


    // --- WindowTracker D-Bus service (unchanged) ---

    GetSnapshot() {
        return [this._trackerRevision, this._trackerStateJson];
    }

    _buildState() {
        const focused = global.display.focus_window;
        const activeWorkspace = global.workspace_manager.get_active_workspace();
        const windows = this._listWindows();

        let idleTimeMs = 0;
        try {
            const idleMonitor = Meta.IdleMonitor.get_core();
            idleTimeMs = idleMonitor.get_idletime() || 0;
        } catch (_) {
            idleTimeMs = 0;
        }

        return {
            focused_window: focused ? this._windowToJson(focused, 0) : null,
            open_windows: windows,
            active_workspace: activeWorkspace ? activeWorkspace.index() : null,
            active_workspace_name: activeWorkspace && typeof activeWorkspace.get_name === 'function'
                ? this._safeCall(() => activeWorkspace.get_name(), null)
                : null,
            workspace_count: global.workspace_manager.get_n_workspaces(),
            screen_locked: Main.screenShield ? Main.screenShield.locked : false,
            idle_time_seconds: idleTimeMs > 0 ? idleTimeMs / 1000 : 0,
            timestamp: GLib.DateTime.new_now_utc().format('%Y-%m-%dT%H:%M:%SZ')
        };
    }

    _listWindows() {
        const windows = new Set();
        try {
            const nWorkspaces = global.workspace_manager.get_n_workspaces();
            for (let i = 0; i < nWorkspaces; i++) {
                const ws = global.workspace_manager.get_workspace_by_index(i);
                if (ws) {
                    ws.list_windows().forEach(w => windows.add(w));
                }
            }
        } catch (e) {
            logError(e, `${this.uuid}: failed to list workspace windows`);
        }

        return Array.from(windows)
            .filter(win => win && !this._shouldSkipWindow(win))
            .map((win, index) => {
                try {
                    return this._windowToJson(win, index);
                } catch (error) {
                    logError(error, `${this.uuid}: failed to serialize window`);
                    return null;
                }
            })
            .filter(Boolean);
    }

    _shouldSkipWindow(win) {
        const skipTaskbar = typeof win.is_skip_taskbar === 'function'
            ? win.is_skip_taskbar()
            : Boolean(win.skip_taskbar);
        const overrideRedirect = typeof win.is_override_redirect === 'function'
            ? win.is_override_redirect()
            : false;
        return skipTaskbar || overrideRedirect;
    }

    _safeCall(fn, fallback = null) {
        try {
            return fn();
        } catch (_) {
            return fallback;
        }
    }

    _windowToJson(win, zOrder) {
        const rect = this._safeCall(() => win.get_frame_rect(), {x: 0, y: 0, width: 0, height: 0});
        const workspace = this._safeCall(() => win.get_workspace(), null);
        const workspaceName = workspace && typeof workspace.get_name === 'function'
            ? this._safeCall(() => workspace.get_name(), null)
            : null;
        const maximized = typeof win.is_maximized === 'function'
            ? this._safeCall(() => win.is_maximized(), false)
            : this._safeCall(() => win.get_maximized() !== Meta.MaximizeFlags.NONE, false);
        const monitorIndex = this._safeCall(() => win.get_monitor(), null);

        const app = this._safeCall(() => win.get_app(), null);
        const appId = app && typeof app.get_id === 'function'
            ? this._safeCall(() => app.get_id(), null)
            : null;

        const urgent = this._safeCall(() => {
            if ('urgent' in win) return Boolean(win.urgent);
            if (typeof win.is_urgent === 'function') return win.is_urgent();
            return false;
        }, false);

        const demandsAttention = this._safeCall(() => {
            if ('demands_attention' in win) return Boolean(win.demands_attention);
            if (typeof win.demands_attention === 'function') return win.demands_attention();
            return false;
        }, false);

        return {
            title: this._safeCall(() => win.get_title(), '') || '',
            wm_class: this._safeCall(() => win.get_wm_class(), '') || '',
            wm_class_instance: this._safeCall(() => win.get_wm_class_instance(), '') || '',
            pid: this._safeCall(() => win.get_pid(), null),
            app_id: appId,
            workspace: workspace ? workspace.index() : null,
            workspace_name: workspaceName,
            monitor: monitorIndex === null ? null : `${monitorIndex}`,
            monitor_index: monitorIndex,
            fullscreen: this._safeCall(() => win.is_fullscreen(), false),
            maximized,
            urgent,
            demands_attention: demandsAttention,
            z_order: zOrder,
            geometry: {
                x: rect.x,
                y: rect.y,
                width: rect.width,
                height: rect.height
            }
        };
    }

    _updateTrackerSnapshot({emitSignal}) {
        const payload = JSON.stringify(this._buildState());
        if (this._trackerRevision === 0) {
            this._trackerRevision = 1;
            this._trackerStateJson = payload;
            return;
        }
        if (payload === this._trackerStateJson) {
            return;
        }
        this._trackerRevision += 1;
        this._trackerStateJson = payload;
        if (emitSignal && this._enabled && this._dbusImpl) {
            this._dbusImpl.emit_signal('StateChanged', new GLib.Variant('(us)', [this._trackerRevision, payload]));
        }
    }

    _emitStateChanged() {
        if (!this._enabled || !this._dbusImpl) {
            return;
        }
        try {
            this._updateTrackerSnapshot({emitSignal: true});
        } catch (error) {
            logError(error, `${this.uuid}: failed to emit state change`);
        }
    }
}
