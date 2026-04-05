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

const TRACKER_IFACE = `
<node>
  <interface name="org.waid.WindowTracker">
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
        this._signals = [];
        this._dbusImpl = Gio.DBusExportedObject.wrapJSObject(TRACKER_IFACE, this);
        this._dbusImpl.export(Gio.DBus.session, '/org/waid/WindowTracker');
        this._nameOwnerId = Gio.bus_own_name_on_connection(
            Gio.DBus.session,
            'org.waid.WindowTracker',
            Gio.BusNameOwnerFlags.NONE,
            null,
            null
        );

        this._indicator = new StatusIndicator();
        this._indicator.onRefresh(() => this._requestRefresh());
        Main.panel.addToStatusArea(this.uuid, this._indicator);

        this._signals.push([global.display, global.display.connect('notify::focus-window', () => this._emitStateChanged())]);
        this._signals.push([global.workspace_manager, global.workspace_manager.connect('active-workspace-changed', () => this._emitStateChanged())]);
        if (Main.screenShield) {
            this._signals.push([Main.screenShield, Main.screenShield.connect('notify::locked', () => this._emitStateChanged())]);
        }

        this._setupDaemonProxy();
        this._updateIndicatorFromDaemon();
    }

    disable() {
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
        const windows = global.get_window_actors()
            .map(actor => actor.meta_window)
            .filter(win => win && !win.skip_taskbar)
            .map(win => this._windowToJson(win));

        return {
            focused_window: focused ? this._windowToJson(focused) : null,
            open_windows: windows,
            active_workspace: activeWorkspace ? activeWorkspace.index() : null,
            workspace_count: global.workspace_manager.get_n_workspaces(),
            screen_locked: Main.screenShield ? Main.screenShield.locked : false,
            timestamp: GLib.DateTime.new_now_utc().format('%Y-%m-%dT%H:%M:%SZ')
        };
    }

    _windowToJson(win) {
        const rect = win.get_frame_rect();
        const workspace = win.get_workspace();
        const workspaceName = workspace && typeof workspace.get_name === 'function'
            ? workspace.get_name()
            : null;
        const maximized = typeof win.is_maximized === 'function'
            ? win.is_maximized()
            : win.get_maximized() !== Meta.MaximizeFlags.NONE;
        return {
            title: win.get_title() || '',
            wm_class: win.get_wm_class() || '',
            wm_class_instance: win.get_wm_class_instance() || '',
            pid: win.get_pid(),
            workspace: workspace ? workspace.index() : null,
            workspace_name: workspaceName,
            monitor: `${win.get_monitor()}`,
            monitor_index: win.get_monitor(),
            fullscreen: win.is_fullscreen(),
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
        const payload = JSON.stringify(this._buildState());
        this._dbusImpl.emit_signal('StateChanged', new GLib.Variant('(s)', [payload]));
    }

    _setupDaemonProxy() {
        this._daemonProxy = null;
        Gio.DBusProxy.new_for_bus(
            Gio.BusType.SESSION,
            Gio.DBusProxyFlags.NONE,
            null,
            'org.waid.Daemon',
            '/org/waid/Daemon',
            'org.waid.Daemon',
            null,
            (source, result) => {
                try {
                    this._daemonProxy = Gio.DBusProxy.new_for_bus_finish(result);
                    this._daemonProxy.connectSignal('StatusChanged', (_proxy, _sender, params) => {
                        const statusJson = params.deepUnpack()[0];
                        this._applyStatus(statusJson);
                    });
                    this._updateIndicatorFromDaemon();
                } catch (_) {
                }
            }
        );
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
                } catch (_) {
                }
            }
        );
    }

    _requestRefresh() {
        if (!this._daemonProxy) {
            return;
        }
        this._daemonProxy.call('RefreshTaxonomy', null, Gio.DBusCallFlags.NONE, -1, null, null);
    }

    _applyStatus(statusJson) {
        let parsed = null;
        try {
            parsed = JSON.parse(statusJson);
        } catch (_) {
            return;
        }
        this._indicator.setStatus(parsed.top_level, parsed.icon);
    }
}
