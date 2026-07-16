// macOS Dock icon policy.
//
// The Dock icon follows the control panel: it appears when the control panel
// opens and goes away when the panel is closed to the tray. The user-facing
// "Show Dock Icon" setting overrides that — with it off, OpenWhispr stays a
// menu-bar-only app and no caller may bring the icon back.
//
// Hiding the dictation panel must never touch the Dock. The panel is hidden
// outright rather than minimized into the Dock, so there is nothing to restore
// from there.

// Whether the Dock icon should be visible right now.
// Returns null off macOS, where there is no Dock to act on.
export function resolveDockVisibility({ platform, showDockIcon, controlPanelVisible }) {
  if (platform !== "darwin") return null;
  if (!showDockIcon) return false;
  return !!controlPanelVisible;
}

// The launch activation policy. "accessory" is the runtime equivalent of
// LSUIElement: no Dock icon and no menu bar.
export function resolveActivationPolicy({ platform, showDockIcon }) {
  if (platform !== "darwin") return null;
  return showDockIcon ? "regular" : "accessory";
}
