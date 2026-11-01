import json
from pathlib import Path
import resource
import subprocess
import sys

root = Path(sys.argv[1]).resolve()
source = Path(sys.argv[2]).resolve()
out = root / "results/packaged-probe"
out.mkdir(parents=True, exist_ok=True)
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
specs = json.loads((root / "manifest.json").read_text())
for label in ("base-deb", "head-deb", "head-rpm", "head-tar", "head-appimage"):
    with (out / f"{label}.log").open("w") as log:
        result = subprocess.run(["node", source / "scripts/verify-linux-sqlite.js", root / specs[label]["app"]],
                                stdout=log, stderr=subprocess.STDOUT, timeout=160)
    text = (out / f"{label}.log").read_text()
    if label == "base-deb":
        passed = result.returncode != 0 and "uncaught target signal 4" in text
    else:
        passed = result.returncode == 0
    print(json.dumps({"label": label, "exit": result.returncode, "passed": passed}), flush=True)
    if not passed:
        raise RuntimeError(f"Wrong packaged CPU probe result for {label}")
