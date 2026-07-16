const { app } = require("electron");
const { resolveDockVisibility, resolveActivationPolicy } = require("./dockPolicy");

// Single owner of the macOS Dock icon. Every caller that wants the icon shown
// or hidden goes through here so the "Show Dock Icon" setting can veto it.
//
// The icon tracks the control panel, and callers report that state explicitly.
// The window's own "show"/"hide" events look like the obvious source to derive
// it from, but on macOS they are occlusion events: Electron only emits them
// from windowDidChangeOcclusionState, so they also fire when the panel is
// merely covered by another window, minimized, or on another Space. Deriving
// from them makes the icon flicker as the user switches windows.
class DockManager {
  constructor() {
    this._showDockIcon = true;
    this._controlPanelVisible = false;
  }

  // Applies the launch activation policy. Called once at startup, before any
  // window exists, so there is no visibility to apply yet.
  init(showDockIcon) {
    this._showDockIcon = showDockIcon !== false;
    this._controlPanelVisible = false;
    this._applyActivationPolicy();
  }

  // Reacts to the user toggling the setting. Turning it off drops the icon
  // immediately; turning it back on restores it if the control panel is open,
  // which it must be for the toggle to have been clicked.
  setShowDockIcon(enabled) {
    this._showDockIcon = enabled !== false;
    // "regular" reveals the icon on its own, so the policy has to be applied
    // before the visibility check that may hide it again.
    this._applyActivationPolicy();
    this._applyVisibility();
  }

  // Reported by every path that surfaces or hides the control panel.
  setControlPanelVisible(visible) {
    this._controlPanelVisible = !!visible;
    this._applyVisibility();
  }

  _applyActivationPolicy() {
    const policy = resolveActivationPolicy({
      platform: process.platform,
      showDockIcon: this._showDockIcon,
    });
    if (policy) {
      app.setActivationPolicy(policy);
    }
  }

  _applyVisibility() {
    const visible = resolveDockVisibility({
      platform: process.platform,
      showDockIcon: this._showDockIcon,
      controlPanelVisible: this._controlPanelVisible,
    });
    if (visible === null || !app.dock) return;

    if (visible) {
      app.dock.show();
    } else {
      // Electron swallows dock.hide() within 1s of a dock.show() (see DockHide
      // in browser_mac.mm), so closing the control panel right after opening it
      // leaves the icon up until the next hide. Working around that throttle
      // risks the macOS bug it exists to prevent: duplicate Dock icons.
      app.dock.hide();
    }
  }
}

module.exports = new DockManager();
