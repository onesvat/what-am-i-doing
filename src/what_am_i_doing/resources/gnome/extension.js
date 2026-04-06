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
const FALLBACK_TOP_LEVEL = 'unknown';
const FALLBACK_ICON = 'help-about-symbolic';

const TRACKER_IFACE = `
<node>
  <interface name="${TRACKER_BUS_NAME}">
    <method name="GetCurrentState">
      <arg name="state_json" type="s" direction="out"/>
    </method>
    <signal name="StateChanged">
      <arg name="state_json" type="s"/>
    </signal>
  </interface>
</node>`;

const StatusIndicator = GObject.registerClass(
class StatusIndicator extends PanelMenu.Button {
    _init() {
        super._init(0.0, 'waid', false);
        this._box = new St.BoxLayout({style_class: 'panel-status-menu-box'});
        this._icon = new St.Icon({icon_name: 'help-about-symbolic', style_class: 'system-status-icon'});
        this._label = new St.Label({text: 'unknown', y_align: Clutter.ActorAlign.CENTER});
        this._box.add_child(this._icon);
        this._box.add_child(this._label);
        this.add_child(this._box);

        this._refreshItem = new PopupMenu.PopupMenuItem('Refresh Categories');
        this.menu.addMenuItem(this._refreshItem);
    }

    setStatus(topLevel, iconName) {
        this._icon.icon_name = iconName || 'help-about-symbolic';
        this._label.text = topLevel || 'unknown';
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
        this._daemonSignalId = 0;
        this._daemonWatchId = 0;
        this._proxyGeneration = 0;
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
        this._indicator.setStatus(FALLBACK_TOP_LEVEL, FALLBACK_ICON);

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

    GetCurrentState() {
        return JSON.stringify(this._buildState());
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

    _emitStateChanged() {
        if (!this._enabled || !this._dbusImpl) {
            return;
        }
        try {
            const payload = JSON.stringify(this._buildState());
            this._dbusImpl.emit_signal('StateChanged', new GLib.Variant('(s)', [payload]));
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
                if (!this._enabled || generation !== this._proxyGeneration) {
                    return;
                }
                try {
                    const proxy = Gio.DBusProxy.new_for_bus_finish(result);
                    this._teardownDaemonProxy();
                    this._daemonProxy = proxy;
                    this._daemonSignalId = proxy.connectSignal('StatusChanged', (_proxy, _sender, params) => {
                        const statusJson = params.deepUnpack()[0];
                        this._applyStatus(statusJson);
                    });
                    this._updateIndicatorFromDaemon();
                } catch (error) {
                    logError(error, `${this.uuid}: failed to connect to daemon`);
                    this._handleDaemonVanished();
                }
            }
        );
    }

    _teardownDaemonProxy() {
        if (this._daemonProxy && this._daemonSignalId) {
            try {
                this._daemonProxy.disconnectSignal(this._daemonSignalId);
            } catch (_) {
            }
        }
        this._daemonSignalId = 0;
        this._daemonProxy = null;
    }

    _handleDaemonVanished() {
        this._proxyGeneration += 1;
        this._teardownDaemonProxy();
        if (this._indicator) {
            this._indicator.setStatus(FALLBACK_TOP_LEVEL, FALLBACK_ICON);
        }
    }

    _updateIndicatorFromDaemon() {
        if (!this._daemonProxy) {
            return;
        }
        this._daemonProxy.call(
            'GetStatus',
            null,
            Gio.DBusCallFlags.NONE,
            -1,
            null,
            (_proxy, result) => {
                try {
                    const value = this._daemonProxy.call_finish(result);
                    const statusJson = value.deepUnpack()[0];
                    this._applyStatus(statusJson);
                } catch (error) {
                    logError(error, `${this.uuid}: failed to fetch daemon status`);
                    this._handleDaemonVanished();
                }
            }
        );
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

    _applyStatus(statusJson) {
        if (!this._indicator) {
            return;
        }
        let parsed = null;
        try {
            parsed = JSON.parse(statusJson);
        } catch (_) {
            return;
        }
        this._indicator.setStatus(parsed.top_level || FALLBACK_TOP_LEVEL, parsed.icon || FALLBACK_ICON);
    }
}
