import datetime
import json
import os
import resource
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import urllib.request

root = Path(sys.argv[1]).resolve()
platform_name = sys.argv[2]
plan = sys.argv[3] if len(sys.argv) > 3 else "standard"
tools = Path(__file__).resolve().parent
out = root / "results" / (platform_name + ("-extended" if plan == "extended" else ""))
out.mkdir(parents=True, exist_ok=True)
scratch = root / "scratch" / platform_name
scratch.mkdir(parents=True, exist_ok=True)
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def run(command, dest, env=None, timeout=40):
    with dest.open("w") as log:
        proc = subprocess.Popen([str(x) for x in command], env=env, stdout=log,
                                stderr=subprocess.STDOUT, start_new_session=True)
        try:
            return proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            return "timeout"


def get_json(port, path="/json"):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=1) as response:
            return json.load(response)
    except (OSError, ValueError):
        return None


def cdp(command, dest, timeout=25):
    return run(["node", tools / "cdp.mjs", *command], dest, timeout=timeout)


def base_env(dest):
    dest.mkdir(parents=True, exist_ok=True)
    home = dest / "home"
    home.mkdir(exist_ok=True)
    env = os.environ.copy()
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"),
               XDG_CACHE_HOME=str(home / ".cache"), XDG_SESSION_TYPE="x11",
               XDG_CURRENT_DESKTOP="GNOME", OPENWHISPR_LOG_LEVEL="debug")
    return env


def payload(version, kind):
    if kind == "deb":
        app_root = root / "downloads" / version / "deb/opt/OpenWhispr"
        return app_root, app_root / "open-whispr"
    if kind == "tar":
        app_root = root / "downloads" / version / "tar" / f"OpenWhispr-{version}-linux-x64"
        return app_root, app_root / "open-whispr"
    app_root = root / "downloads" / version / "appimage/squashfs-root"
    if kind == "appimage-runtime":
        return app_root, root / "downloads" / version / f"OpenWhispr-{version}-linux-x86_64.AppImage"
    return app_root, app_root / "AppRun"


def stop(proc):
    if proc.poll() is None:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
    else:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def native_trial(version, kind, upgrade=False, cpu=None):
    label = f"{version}-{kind}" + ("-upgrade" if upgrade else "") + (f"-cpu-{cpu}" if cpu else "")
    dest = out / label
    dest.mkdir(exist_ok=True)
    app_root, launcher = payload(version, kind)
    binary = app_root / "open-whispr-app"
    runtime_dir = scratch / ("upgrade-Grüße" if upgrade else label)
    env = base_env(runtime_dir)
    if kind == "appimage-runtime":
        env["APPIMAGE_EXTRACT_AND_RUN"] = "1"
    port = 9300 + (40 if version == "1.11.0" else 0) + {"deb": 0, "appimage": 10, "tar": 20, "appimage-runtime": 30}[kind]
    inspector = port + 1
    cdp_ports = ["--port", str(port), "--inspect-port", str(inspector)]
    args = ["--no-sandbox", "--ozone-platform=x11", "--log-level=debug",
            f"--user-data-dir={runtime_dir / 'profile'}", f"--remote-debugging-port={port}",
            f"--inspect={inspector}"]
    summary = {"version": version, "format": kind, "start_utc": datetime.datetime.now(
        datetime.timezone.utc).isoformat(), "launch": str(launcher), "args": args, "cpu": cpu}
    with (dest / "stdout.log").open("w") as log:
        command = (["qemu-x86_64", "-cpu", cpu, str(binary)] if cpu else [str(launcher)])
        proc = subprocess.Popen([*command, *args], env=env, stdout=log,
                                stderr=subprocess.STDOUT, start_new_session=True)
        updates_off = False
        deadline = time.monotonic() + (120 if cpu else 90)
        while proc.poll() is None and time.monotonic() < deadline:
            if not updates_off and get_json(inspector, "/json/list"):
                cdp(["main", str(tools / "updates-off.js"), *cdp_ports], dest / "updates-off.json")
                updates_off = True
            pages = get_json(port)
            if pages and any("panel=true" in p.get("url", "") for p in pages):
                time.sleep(3)
                break
            time.sleep(0.5)
        pages = get_json(port)
        (dest / "targets.json").write_text(json.dumps(pages, indent=2))
        if pages:
            summary["runtime_probe_exit"] = cdp(
                ["main", str(tools / "runtime.js"), *cdp_ports], dest / "runtime.json")
            cdp(["windows", *cdp_ports], dest / "windows.json")
            summary["renderer_probe_exit"] = cdp(
                ["run", "panel", str(tools / "renderer.js"), *cdp_ports], dest / "renderer.json")
            if summary["renderer_probe_exit"] == 0:
                renderer = json.loads((dest / "renderer.json").read_text())
                summary["rendered_text"] = bool(renderer.get("text", "").strip())
            if summary["runtime_probe_exit"] == 0:
                runtime = json.loads((dest / "runtime.json").read_text())
                summary["runtime_version_matches"] = runtime.get("version") == version
            if upgrade:
                script = "seed-upgrade.js" if version == "1.10.4" else "check-upgrade.js"
                summary["upgrade_probe_exit"] = cdp(
                    ["run", "panel", str(tools / script), *cdp_ports], dest / "upgrade.json")
                summary["upgrade_marker_present"] = (
                    "ISSUE3038_UPGRADE" in (dest / "upgrade.json").read_text())
            run(["scrot", dest / "desktop.png"], dest / "screenshot.log", timeout=10)
            time.sleep(12)
        summary.update(pages_available=bool(pages), updates_disabled=updates_off,
                       alive_before_stop=proc.poll() is None, exit_before_stop=proc.poll())
        if upgrade and pages:
            cdp(["main", "setTimeout(() => process.mainModule.require('electron').app.quit(), 100); true",
                 *cdp_ports], dest / "quit.log")
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        stop(proc)
    profile_logs = runtime_dir / "profile/logs"
    if profile_logs.exists():
        shutil.copytree(profile_logs, dest / "debug-logs", dirs_exist_ok=True)
    if not summary["pages_available"] and binary.exists() and not cpu:
        commands = dest / "gdb-commands.txt"
        commands.write_text("set pagination off\nset confirm off\n"
                            "handle SIGPIPE nostop noprint pass\n"
                            "handle SIGCHLD nostop noprint pass\nrun\n"
                            "thread apply all bt 12\ninfo registers\n"
                            "x/16i $pc-24\ninfo sharedlibrary\n")
        summary["gdb_exit"] = run(["gdb", "-q", "-batch", "-x", commands, "--args", binary,
                                   "--no-sandbox", "--ozone-platform=x11", "--log-level=debug",
                                   f"--user-data-dir={runtime_dir / 'gdb-profile'}"],
                                  dest / "gdb.log", env=env, timeout=100)
    (dest / "result.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)


def cpu_trials():
    for version in ("1.10.4", "1.11.0"):
        app_root, _ = payload(version, "deb")
        for cpu in ("Nehalem", "SandyBridge", "IvyBridge", "Haswell"):
            dest = out / f"{version}-cpu-{cpu}"
            dest.mkdir(exist_ok=True)
            env = base_env(scratch / f"{version}-cpu-{cpu}")
            env["ELECTRON_RUN_AS_NODE"] = "1"
            summary = {"version": version, "cpu": cpu}
            prefix = ["qemu-x86_64", "-cpu", cpu, app_root / "open-whispr-app"]
            summary["versions_exit"] = run([*prefix, "-e", "console.log(process.versions)"],
                                            dest / "versions.log", env=env, timeout=45)
            summary["sqlite_exit"] = run([*prefix, tools / "sqlite-probe.cjs", app_root],
                                          dest / "sqlite.log", env=env, timeout=60)
            (dest / "result.json").write_text(json.dumps(summary, indent=2))
            print(json.dumps(summary), flush=True)


run(["sh", "-c", "uname -a; lscpu; cat /etc/os-release; ldd --version; node --version"],
    out / "environment.txt")
if plan == "extended":
    for version in ("1.10.4", "1.11.0"):
        native_trial(version, "deb", upgrade=True)
    for version in ("1.10.4", "1.11.0"):
        native_trial(version, "appimage-runtime")
    subprocess.run([sys.executable, tools / "cpu-trace.py", root], check=True)
    for version in ("1.10.4", "1.11.0"):
        native_trial(version, "deb", cpu="IvyBridge")
else:
    for version in ("1.10.4", "1.11.0"):
        for kind in (("deb", "appimage") if platform_name == "ubuntu" else ("appimage", "tar")):
            native_trial(version, kind)
    if platform_name == "ubuntu":
        cpu_trials()
