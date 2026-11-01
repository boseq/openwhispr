(() => {
  const { app } = process.mainModule.require("electron");
  return { version: app.getVersion(), versions: process.versions, platform: process.platform,
    arch: process.arch, userData: app.getPath("userData"), executable: process.execPath };
})()
