// Drive a running OpenWhispr build over the DevTools protocols. Node 22+ (global fetch/WebSocket).
// Runs wherever the app runs: on the Mac host, or inside a Parallels guest (the app's debug ports
// listen on the guest's loopback only).
//
// The app must be started with --remote-debugging-port=<port> (renderer) and, for `main` and
// `windows`, --inspect=<inspect-port> (main process).
//
//   node cdp.mjs targets                          list renderer pages
//   node cdp.mjs run <target> <file.js | js>      evaluate in a window, awaiting promises; prints JSON
//   node cdp.mjs main <file.js | js>              evaluate in the main process; use
//                                                 process.mainModule.require("electron")
//   node cdp.mjs windows                          every BrowserWindow: title, url, bounds, visible,
//                                                 focused, display scale factor, native window id
//   node cdp.mjs shot <target> <out.png>          renderer-only capture (see SKILL.md: this never
//                                                 shows window clipping, DPI or native menus)
//
//   --port N          renderer port (default 9222)
//   --inspect-port N  main-process inspector port (default 9229)
//
// <target>: "dictation" (the pill window), "panel" (control panel), or a substring of the URL.
// Pass JavaScript as a file whenever the command crosses prlctl exec: Windows quoting mangles it.
import fs from "node:fs";

const positional = [];
const opts = {};
const argv = process.argv.slice(2);
for (let i = 0; i < argv.length; i++) {
  if (argv[i].startsWith("--")) opts[argv[i].slice(2)] = argv[++i];
  else positional.push(argv[i]);
}
const [cmd, ...rest] = positional;
const port = Number(opts.port || 9222);
const inspectPort = Number(opts["inspect-port"] || 9229);

const getJson = (url) =>
  fetch(url, { signal: AbortSignal.timeout(5000) }).then((res) => {
    if (!res.ok) throw new Error(`${url} answered ${res.status}`);
    return res.json();
  });

async function connect(webSocketUrl) {
  const ws = new WebSocket(webSocketUrl);
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      ws.close();
      reject(new Error(`connecting to ${webSocketUrl} timed out`));
    }, 5000);
    ws.addEventListener("open", () => {
      clearTimeout(timer);
      resolve();
    }, { once: true });
    ws.addEventListener("error", () => {
      clearTimeout(timer);
      reject(new Error(`cannot connect to ${webSocketUrl}`));
    }, { once: true });
  });
  let nextId = 1;
  const pending = new Map();
  ws.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    const waiter = pending.get(message.id);
    if (!waiter) return;
    pending.delete(message.id);
    if (message.error) waiter.reject(new Error(message.error.message));
    else waiter.resolve(message.result);
  });
  const send = (method, params = {}) =>
    new Promise((resolve, reject) => {
      const id = nextId++;
      pending.set(id, { resolve, reject });
      ws.send(JSON.stringify({ id, method, params }));
      // Never hang a repro run on a target that connects but never answers.
      setTimeout(() => {
        if (pending.delete(id)) reject(new Error(`${method} timed out`));
      }, 20000).unref();
    });
  return { send, close: () => ws.close() };
}

async function pageTarget(match) {
  const pages = (await getJson(`http://127.0.0.1:${port}/json`)).filter((t) => t.type === "page");
  // Both windows load index.html; the control panel is the one with ?panel=true.
  const found =
    match === "dictation"
      ? pages.find((t) => !t.url.includes("panel=true") && !t.url.startsWith("devtools:"))
      : match === "panel"
        ? pages.find((t) => t.url.includes("panel=true"))
        : pages.find((t) => t.url.includes(match));
  if (!found) throw new Error(`no page matching "${match}" in: ${pages.map((p) => p.url).join(", ")}`);
  return found;
}

async function mainTarget() {
  const list = await getJson(`http://127.0.0.1:${inspectPort}/json/list`);
  if (!list.length) throw new Error("the main-process inspector has no targets");
  return list[0];
}

const source = (arg) => (arg && fs.existsSync(arg) ? fs.readFileSync(arg, "utf8") : arg);

async function evaluate(target, expression) {
  const session = await connect(target.webSocketDebuggerUrl);
  try {
    const { result, exceptionDetails } = await session.send("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise: true,
      includeCommandLineAPI: true,
    });
    if (exceptionDetails) {
      throw new Error(exceptionDetails.exception?.description || exceptionDetails.text);
    }
    return result.value;
  } finally {
    session.close();
  }
}

const WINDOWS_EXPRESSION = `(() => {
  const { BrowserWindow, screen } = process.mainModule.require("electron");
  return BrowserWindow.getAllWindows().map((w) => {
    const bounds = w.getBounds();
    return {
      id: w.id,
      title: w.getTitle(),
      url: w.webContents.getURL(),
      bounds,
      contentBounds: w.getContentBounds(),
      visible: w.isVisible(),
      focused: w.isFocused(),
      alwaysOnTop: w.isAlwaysOnTop(),
      displayScaleFactor: screen.getDisplayMatching(bounds).scaleFactor,
      // "window:<id>:0": the CGWindowID on macOS (screencapture -l), the HWND on Windows.
      mediaSourceId: w.getMediaSourceId(),
    };
  });
})()`;

const print = (value) => console.log(JSON.stringify(value, null, 2));

if (cmd === "targets") {
  const pages = await getJson(`http://127.0.0.1:${port}/json`);
  for (const t of pages) console.log(`${t.type}\t${t.url}`);
} else if (cmd === "run") {
  print(await evaluate(await pageTarget(rest[0]), source(rest[1])));
} else if (cmd === "main") {
  print(await evaluate(await mainTarget(), source(rest[0])));
} else if (cmd === "windows") {
  print(await evaluate(await mainTarget(), WINDOWS_EXPRESSION));
} else if (cmd === "shot") {
  const session = await connect((await pageTarget(rest[0])).webSocketDebuggerUrl);
  const { data } = await session.send("Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(rest[1], Buffer.from(data, "base64"));
  session.close();
  console.log(rest[1]);
} else {
  console.log(fs.readFileSync(new URL(import.meta.url), "utf8").split("\nimport ")[0]);
  process.exit(2);
}
