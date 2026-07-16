const test = require("node:test");
const assert = require("node:assert/strict");

const load = () => import("../../src/helpers/dockPolicy.js");

test("the Dock icon follows the control panel when the setting is on", async () => {
  const { resolveDockVisibility } = await load();

  assert.equal(
    resolveDockVisibility({ platform: "darwin", showDockIcon: true, controlPanelVisible: true }),
    true
  );
  assert.equal(
    resolveDockVisibility({ platform: "darwin", showDockIcon: true, controlPanelVisible: false }),
    false
  );
});

test("the setting overrides an open control panel", async () => {
  const { resolveDockVisibility } = await load();

  // Opening the control panel from the tray or clicking the Dock icon would
  // normally surface the icon; with the setting off the app stays menu-bar-only.
  assert.equal(
    resolveDockVisibility({ platform: "darwin", showDockIcon: false, controlPanelVisible: true }),
    false
  );
});

test("re-enabling the setting with the control panel open restores the icon", async () => {
  const { resolveDockVisibility } = await load();

  // The toggle lives in the control panel, so the panel is open whenever the
  // setting can be switched back on and the icon must come back. This holds
  // only as long as every path that surfaces the panel reports it, including
  // the one that reuses an already-created window.
  assert.equal(
    resolveDockVisibility({ platform: "darwin", showDockIcon: true, controlPanelVisible: true }),
    true
  );
});

test("hiding the dictation panel cannot resurrect the Dock icon", async () => {
  const { resolveDockVisibility } = await load();

  // Regression guard for #428: the auto-hide-when-idle cycle ended every
  // dictation with an app.dock.show(), a leftover from when the macOS branch
  // minimized the panel into the Dock instead of hiding it. The dictation panel
  // is not the control panel, so it cannot affect the icon either way.
  const dockHiddenByClosingControlPanel = {
    platform: "darwin",
    showDockIcon: true,
    controlPanelVisible: false,
  };
  assert.equal(resolveDockVisibility(dockHiddenByClosingControlPanel), false);
});

test("there is no Dock to act on outside macOS", async () => {
  const { resolveDockVisibility, resolveActivationPolicy } = await load();

  for (const platform of ["win32", "linux"]) {
    assert.equal(
      resolveDockVisibility({ platform, showDockIcon: true, controlPanelVisible: true }),
      null
    );
    assert.equal(resolveActivationPolicy({ platform, showDockIcon: true }), null);
  }
});

test("activation policy mirrors the setting", async () => {
  const { resolveActivationPolicy } = await load();

  assert.equal(resolveActivationPolicy({ platform: "darwin", showDockIcon: true }), "regular");
  assert.equal(resolveActivationPolicy({ platform: "darwin", showDockIcon: false }), "accessory");
});
