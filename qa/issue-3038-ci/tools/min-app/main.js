// Smallest Electron app: open a window, print versions, quit. Tells an Electron/Rosetta crash apart from an OpenWhispr one.
const { app, BrowserWindow } = require("electron");
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 300, height: 200, show: true });
  await win.loadURL("data:text/html,<h1>ok</h1>");
  console.log("MINAPP_OK", JSON.stringify(process.versions));
  setTimeout(() => app.quit(), 1500);
});
