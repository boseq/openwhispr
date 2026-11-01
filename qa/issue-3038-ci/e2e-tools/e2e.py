import datetime
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import time
import urllib.request

root = Path(sys.argv[1]).resolve()
mode = sys.argv[2]
tools = root / "tools"
out = root / "results" / mode
out.mkdir(parents=True, exist_ok=True)
specs = json.loads((root / "manifest.json").read_text())
node = str(tools / "node")
scratch = Path(os.environ.get("E2E_SCRATCH", root / "scratch"))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
results = []

def call(command, log, timeout=60):
    with log.open("w") as output:
        return subprocess.run([str(x) for x in command], stdout=output,
                              stderr=subprocess.STDOUT, timeout=timeout).returncode

def endpoint(port, url="/json"):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{url}", timeout=1) as response:
            return json.load(response)
    except (OSError, ValueError):
        return None

def trial(label, package, profile, action="seed", expect_sigill=False):
    spec = specs[package]
    dest = out / label
    dest.mkdir(exist_ok=True)
    profile = scratch / mode / profile
    profile.mkdir(parents=True, exist_ok=True)
    home = profile / "home"
    home.mkdir(exist_ok=True)
    env = {**os.environ, "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"),
           "XDG_CACHE_HOME": str(home / ".cache"), "XDG_SESSION_TYPE": "x11",
           "XDG_CURRENT_DESKTOP": "GNOME", "OPENWHISPR_LOG_LEVEL": "debug"}
    port = 9600 + len(results) * 2
    ports = ["--port", str(port), "--inspect-port", str(port + 1)]
    args = ["--no-sandbox", "--ozone-platform=x11", "--log-level=debug",
            f"--user-data-dir={profile / 'data'}", f"--remote-debugging-port={port}",
            f"--inspect={port + 1}"]
    summary = {"label": label, "package": package, "start_utc": datetime.datetime.now(
        datetime.timezone.utc).isoformat(), "profile": str(profile), "args": args}
    def cdp(args, name):
        code = call([node, tools / "cdp.mjs", *args, *ports], dest / name, timeout=80)
        if code:
            raise RuntimeError(f"CDP {name} failed: {code}")
        return json.loads((dest / name).read_text())
    proc = None
    try:
        with (dest / "stdout.log").open("w") as log:
            proc = subprocess.Popen([str(root / spec["launcher"]), *args], env=env,
                                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            updates_off = False
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                if not expect_sigill and not updates_off and endpoint(port + 1, "/json/list"):
                    attempt = summary.get("update_attempts", 0) + 1
                    summary["update_attempts"] = attempt
                    try:
                        cdp(["main", str(tools / "updates-off.js")], f"updates-off-{attempt}.json")
                        updates_off = True
                    except RuntimeError:
                        # The inspector can publish a target before the app context exists.
                        pass
                pages = endpoint(port)
                if updates_off and pages and any("panel=true" in page.get("url", "") for page in pages):
                    break
                if proc.poll() is not None:
                    break
                time.sleep(0.5)
            summary.update(exit_before_checks=proc.poll(), updates_disabled=updates_off)
            if expect_sigill:
                summary["passed"] = proc.poll() in (-4, 132)
                summary["expected"] = "SIGILL before renderer"
                if not summary["passed"]:
                    raise RuntimeError("Base did not terminate with SIGILL")
            else:
                if not updates_off:
                    raise RuntimeError("Could not disable updates in the app context")
                if not endpoint(port):
                    raise RuntimeError("No renderer reached")
                runtime = cdp(["main", str(tools / "runtime.js")], "runtime.json")
                if runtime["version"] != spec["version"] or runtime["userData"] != str(profile / "data"):
                    raise RuntimeError(f"Wrong instance: {runtime}")
                deadline = time.monotonic() + 90
                while time.monotonic() < deadline:
                    renderer = cdp(["run", "panel", str(tools / "renderer.js")], "renderer.json")
                    windows = cdp(["windows"], "windows.json")
                    visible = any(window["visible"] and "panel=true" in window["url"] for window in windows)
                    if renderer["ready"] and visible:
                        break
                    if proc.poll() is not None:
                        raise RuntimeError("App exited while waiting for the welcome window")
                    time.sleep(0.5)
                else:
                    raise RuntimeError("Welcome renderer and visible control panel did not become ready")
                if action == "seed":
                    cdp(["run", "panel", str(tools / "db-seed.js")], "seed.json")
                cdp(["run", "panel", str(tools / "db-check.js")], "database-check.json")
                call(["scrot", dest / "desktop.png"], dest / "screenshot.log")
                time.sleep(5)
                if proc.poll() is not None:
                    raise RuntimeError("App exited after IPC checks")
                summary["passed"] = True
                cdp(["main", "setTimeout(() => process.mainModule.require('electron').app.quit(), 100); true"], "quit.json")
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    pass
    except Exception as error:
        summary.update(passed=False, error=str(error))
    finally:
        if proc is not None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
        logs = profile / "data/logs"
        if logs.exists():
            shutil.copytree(logs, dest / "debug-logs", dirs_exist_ok=True)
        (dest / "result.json").write_text(json.dumps(summary, indent=2))
        results.append(summary)
        print(json.dumps(summary), flush=True)

call(["sh", "-c", "uname -a; lscpu; cat /etc/os-release"], out / "environment.txt")
if mode == "cpu-vm":
    trial("base-startup", "base-deb", "base", expect_sigill=True)
    trial("head-startup", "head-deb", "head", "seed")
    trial("head-restart", "head-deb", "head", "check")
    trial("old-before-upgrade", "old-deb", "upgrade-Grüße", "seed")
    trial("head-after-upgrade", "head-deb", "upgrade-Grüße", "check")
    trial("head-appimage-runtime", "head-appimage-runtime", "image", "seed")
else:
    trial("base-startup", "base-deb", "base", "seed")
    for kind in ("deb", "rpm", "tar", "appimage"):
        trial(f"head-{kind}", f"head-{kind}", kind, "seed")
    trial("head-restart", "head-deb", "deb", "check")
    trial("old-before-upgrade", "old-deb", "upgrade-Grüße", "seed")
    trial("head-after-upgrade", "head-deb", "upgrade-Grüße", "check")
(out / "summary.json").write_text(json.dumps(results, indent=2))
sys.exit(0 if all(result["passed"] for result in results) else 1)
