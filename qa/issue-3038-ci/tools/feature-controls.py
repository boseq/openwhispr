import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys

root = Path(sys.argv[1]).resolve()
tools = Path(__file__).resolve().parent
out = root / "results/feature-controls"
out.mkdir(parents=True, exist_ok=True)
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
for version in ("1.10.4", "1.11.0"):
    app = root / "downloads" / version / "deb/opt/OpenWhispr"
    bindings = []
    for binding in (root / "downloads" / version).rglob("better_sqlite3.node"):
        bindings.append({"path": str(binding.relative_to(root)),
                         "sha256": hashlib.file_digest(binding.open("rb"), "sha256").hexdigest()})
    (out / f"bindings-{version}.json").write_text(json.dumps(bindings, indent=2))
    for index, cpu in enumerate(("Haswell", "Haswell,-avx2")):
        case = out / f"{version}-{index}"
        case.mkdir(exist_ok=True)
        env = os.environ.copy()
        env["ELECTRON_RUN_AS_NODE"] = "1"
        command = ["qemu-x86_64", "-cpu", cpu, str(app / "open-whispr-app"),
                   str(tools / "sqlite-probe.cjs"), str(app)]
        with (case / "sqlite.log").open("w") as log:
            proc = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT,
                                    start_new_session=True)
            try:
                code = proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
                code = "timeout"
        result = {"version": version, "cpu": cpu, "sqlite_exit": code}
        (case / "result.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result), flush=True)
