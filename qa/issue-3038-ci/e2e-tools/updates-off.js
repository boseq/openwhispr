// Main-process expression (cdp.mjs main): keep the build under test at the version under test.
// A fresh profile has automatic updates on, so an old release downloads the latest one within
// seconds. On Windows the install happens at quit only while autoInstallOnAppQuit is true; on
// macOS Squirrel.Mac stages the update as soon as the download finishes with it true, and installs
// it on quit regardless, so run this right after launch, before that download can complete.
(() => {
  const { autoUpdater } = process.mainModule.require("electron-updater");
  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = false;
  const { app } = process.mainModule.require("electron");
  return {
    version: app.getVersion(),
    autoDownload: autoUpdater.autoDownload,
    autoInstallOnAppQuit: autoUpdater.autoInstallOnAppQuit,
  };
})()
