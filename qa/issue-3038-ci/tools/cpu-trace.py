import json
import os
import resource
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

root = Path(sys.argv[1]).resolve()
tools = Path(__file__).resolve().parent
dest = root / "results/cpu-trace"
dest.mkdir(parents=True, exist_ok=True)
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
for index, (version, cpu) in enumerate((("1.10.4", "IvyBridge"), ("1.11.0", "IvyBridge"),
                                        ("1.11.0", "Haswell"))):
    case = dest / f"{version}-{cpu}"
    case.mkdir(exist_ok=True)
    app = root / "downloads" / version / "deb/opt/OpenWhispr"
    binary = app / "open-whispr-app"
    env = os.environ.copy()
    env["ELECTRON_RUN_AS_NODE"] = "1"
    port = 12340 + index
    commands = case / "commands.gdb"
    commands.write_text(
        "set pagination off\nset confirm off\nset breakpoint pending on\n"
        f"file {binary}\ntarget remote 127.0.0.1:{port}\n"
        "handle SIGPIPE nostop noprint pass\ncontinue\n"
        "thread apply all bt 20\ninfo registers\nx/20i $pc-24\ninfo sharedlibrary\n"
        "detach\nquit\n"
    )
    with (case / "sqlite.log").open("w") as log:
        proc = subprocess.Popen(["qemu-x86_64", "-cpu", cpu, "-g", str(port),
                                 str(binary), str(tools / "sqlite-probe.cjs"), str(app)],
                                env=env, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True)
        time.sleep(1)
        with (case / "gdb.log").open("w") as trace:
            debugger = subprocess.Popen(["gdb", "-q", "-batch", "-x", str(commands)],
                                        stdout=trace, stderr=subprocess.STDOUT,
                                        start_new_session=True)
            def interrupt():
                try:
                    os.killpg(debugger.pid, signal.SIGINT)
                except ProcessLookupError:
                    pass
            timer = threading.Timer(20, interrupt)
            timer.start()
            try:
                gdb_code = debugger.wait(timeout=40)
            except subprocess.TimeoutExpired:
                os.killpg(debugger.pid, signal.SIGKILL)
                debugger.wait()
                gdb_code = "timeout"
            finally:
                timer.cancel()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        exit_before_cleanup = proc.poll()
        if exit_before_cleanup is None:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
        result = {"version": version, "cpu": cpu, "gdb_exit": gdb_code,
                  "qemu_exit_before_cleanup": exit_before_cleanup, "qemu_exit": proc.poll()}
        (case / "result.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result), flush=True)
