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
const UNCLASSIFIED_ICON = 'help-about-symbolic';
const DISCONNECTED_ICON = 'network-offline-symbolic';

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

        this._refreshItem = new PopupMenu.PopupMenuItem('Refresh Categories');
        this.menu.addMenuItem(this._refreshItem);
    }

    setStatus(label, iconName) {
        this._icon.icon_name = iconName || DISCONNECTED_ICON;
        this._label.text = label || PANEL_KIND_DISCONNECTED;
        this._label.visible = true;
    }

    onRefresh(callback) {
        this._refreshItem.connect('activate', callback);
    }
});

export default class WaidExtension extends Extension {
    enable() {
        this._enabled = true;
        this._signals = [];
        this._daemonProxy = null;
        this._daemonPropertiesId = 0;
        this._daemonWatchId = 0;
        this._connectingDaemon = false;
        this._proxyGeneration = 0;
        this._trackerRevision = 0;
        this._trackerStateJson = '';
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
        this._indicator.onRefresh(() => this._requestRefresh());
        Main.panel.addToStatusArea(this.uuid, this._indicator);
        this._setDisconnected();

        this._signals.push([global.display, global.display.connect('notify::focus-window', () => this._emitStateChanged())]);
        this._signals.push([global.workspace_manager, global.workspace_manager.connect('active-workspace-changed', () => this._emitStateChanged())]);
        if (Main.screenShield) {
            this._signals.push([Main.screenShield, Main.screenShield.connect('notify::locked', () => this._emitStateChanged())]);
        }

        this._watchDaemon();
    }

    disable() {
        this._enabled = false;
        if (this._signals) {
            for (const [obj, id] of this._signals) {
                try {
                    obj.disconnect(id);
                } catch (_) {
                }
            }
        }
        this._signals = [];
        if (this._nameOwnerId) {
            Gio.bus_unown_name(this._nameOwnerId);
            this._nameOwnerId = null;
        }
        if (this._daemonWatchId) {
            Gio.bus_unwatch_name(this._daemonWatchId);
            this._daemonWatchId = 0;
        }
        this._teardownDaemonProxy();
        if (this._dbusImpl) {
            this._dbusImpl.unexport();
            this._dbusImpl = null;
        }
        if (this._indicator) {
            this._indicator.destroy();
            this._indicator = null;
        }
    }

    GetSnapshot() {
        return [this._trackerRevision, this._trackerStateJson];
    }

    _buildState() {
        const focused = global.display.focus_window;
        const activeWorkspace = global.workspace_manager.get_active_workspace();
        const windows = this._listWindows();

        return {
            focused_window: focused ? this._windowToJson(focused) : null,
            open_windows: windows,
            active_workspace: activeWorkspace ? activeWorkspace.index() : null,
            workspace_count: global.workspace_manager.get_n_workspaces(),
            screen_locked: Main.screenShield ? Main.screenShield.locked : false,
            timestamp: GLib.DateTime.new_now_utc().format('%Y-%m-%dT%H:%M:%SZ')
        };
    }

    _listWindows() {
        const actors = typeof global.get_window_actors === 'function'
            ? global.get_window_actors()
            : [];
        return actors
            .map(actor => actor.meta_window)
            .filter(win => win && !this._shouldSkipWindow(win))
            .map(win => {
                try {
                    return this._windowToJson(win);
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

    _windowToJson(win) {
        const rect = this._safeCall(() => win.get_frame_rect(), {x: 0, y: 0, width: 0, height: 0});
        const workspace = this._safeCall(() => win.get_workspace(), null);
        const workspaceName = workspace && typeof workspace.get_name === 'function'
            ? this._safeCall(() => workspace.get_name(), null)
            : null;
        const maximized = typeof win.is_maximized === 'function'
            ? this._safeCall(() => win.is_maximized(), false)
            : this._safeCall(() => win.get_maximized() !== Meta.MaximizeFlags.NONE, false);
        const monitorIndex = this._safeCall(() => win.get_monitor(), null);
        return {
            title: this._safeCall(() => win.get_title(), '') || '',
            wm_class: this._safeCall(() => win.get_wm_class(), '') || '',
            wm_class_instance: this._safeCall(() => win.get_wm_class_instance(), '') || '',
            pid: this._safeCall(() => win.get_pid(), null),
            workspace: workspace ? workspace.index() : null,
            workspace_name: workspaceName,
            monitor: monitorIndex === null ? null : `${monitorIndex}`,
            monitor_index: monitorIndex,
            fullscreen: this._safeCall(() => win.is_fullscreen(), false),
            maximized,
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

    _watchDaemon() {
        this._daemonWatchId = Gio.bus_watch_name(
            Gio.BusType.SESSION,
            DAEMON_BUS_NAME,
            Gio.BusNameWatcherFlags.NONE,
            (_connection, _name, _owner) => this._setupDaemonProxy(),
            () => this._handleDaemonVanished()
        );
    }

    _setupDaemonProxy() {
        if (this._connectingDaemon) {
            return;
        }
        this._connectingDaemon = true;
        const generation = ++this._proxyGeneration;
        Gio.DBusProxy.new_for_bus(
            Gio.BusType.SESSION,
            Gio.DBusProxyFlags.NONE,
            null,
            DAEMON_BUS_NAME,
            DAEMON_OBJECT_PATH,
            DAEMON_INTERFACE,
            null,
            (_source, result) => {
                this._connectingDaemon = false;
                if (!this._enabled || generation !== this._proxyGeneration) {
                    return;
                }
                try {
                    const proxy = Gio.DBusProxy.new_for_bus_finish(result);
                    this._teardownDaemonProxy();
                    this._daemonProxy = proxy;
                    this._daemonPropertiesId = proxy.connect('g-properties-changed', () => {
                        this._applyCachedPanelState();
                    });
                    this._applyCachedPanelState();
                } catch (error) {
                    logError(error, `${this.uuid}: failed to connect to daemon`);
                    this._handleDaemonVanished();
                }
            }
        );
    }

    _teardownDaemonProxy() {
        if (this._daemonProxy && this._daemonPropertiesId) {
            try {
                this._daemonProxy.disconnect(this._daemonPropertiesId);
            } catch (_) {
            }
        }
        this._daemonPropertiesId = 0;
        this._daemonProxy = null;
    }

    _handleDaemonVanished() {
        this._proxyGeneration += 1;
        this._connectingDaemon = false;
        this._teardownDaemonProxy();
        this._setDisconnected();
    }

    _cachedStringProperty(name) {
        if (!this._daemonProxy) {
            return '';
        }
        const value = this._daemonProxy.get_cached_property(name);
        return value ? value.deepUnpack() : '';
    }

    _cachedUintProperty(name) {
        if (!this._daemonProxy) {
            return 0;
        }
        const value = this._daemonProxy.get_cached_property(name);
        return value ? Number(value.deepUnpack()) : 0;
    }

    _applyCachedPanelState() {
        const kind = this._cachedStringProperty('PanelKind');
        const label = this._cachedStringProperty('PanelTopLevelLabel');
        const topLevelId = this._cachedStringProperty('PanelTopLevelId');
        const iconName = this._cachedStringProperty('PanelIconName');
        const publishedAt = this._cachedStringProperty('PanelPublishedAt');
        this._panelRevision = this._cachedUintProperty('PanelRevision');

        if (!kind || !iconName || !publishedAt) {
            this._setDisconnected();
            return;
        }
        if (kind === PANEL_KIND_CLASSIFIED) {
            this._indicator.setStatus(label || topLevelId || PANEL_KIND_CLASSIFIED, iconName);
            return;
        }
        if (kind === PANEL_KIND_UNCLASSIFIED) {
            this._indicator.setStatus(PANEL_KIND_UNCLASSIFIED, iconName || UNCLASSIFIED_ICON);
            return;
        }
        if (kind === PANEL_KIND_DISCONNECTED) {
            this._indicator.setStatus(PANEL_KIND_DISCONNECTED, iconName || DISCONNECTED_ICON);
            return;
        }
        this._setDisconnected();
    }

    _setDisconnected() {
        if (this._indicator) {
            this._indicator.setStatus(PANEL_KIND_DISCONNECTED, DISCONNECTED_ICON);
        }
    }

    _requestRefresh() {
        if (!this._daemonProxy) {
            return;
        }
        this._daemonProxy.call(
            'RefreshTaxonomy',
            null,
            Gio.DBusCallFlags.NONE,
            -1,
            null,
            (_proxy, result) => {
                try {
                    this._daemonProxy.call_finish(result);
                } catch (error) {
                    logError(error, `${this.uuid}: failed to refresh taxonomy`);
                }
            }
        );
    }
}
