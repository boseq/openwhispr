import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path(sys.argv[1]).resolve()
formats = sys.argv[2:]
for version in ("1.10.4", "1.11.0"):
    dest = root / version
    dest.mkdir(parents=True, exist_ok=True)
    release = json.loads(subprocess.check_output(
        ["gh", "api", f"repos/OpenWhispr/openwhispr/releases/tags/v{version}"], text=True, timeout=60))
    (dest / "release.json").write_text(json.dumps(release, indent=2))
    names = {
        "deb": f"OpenWhispr-{version}-linux-amd64.deb",
        "appimage": f"OpenWhispr-{version}-linux-x86_64.AppImage",
        "tar": f"OpenWhispr-{version}-linux-x64.tar.gz",
    }
    for kind in formats:
        asset = next(item for item in release["assets"] if item["name"] == names[kind])
        path = dest / asset["name"]
        subprocess.run(["curl", "-fL", "--retry", "3", "--output", str(path),
                        asset["browser_download_url"]], check=True)
        digest = "sha256:" + hashlib.file_digest(path.open("rb"), "sha256").hexdigest()
        if digest != asset["digest"]:
            raise RuntimeError(f"Checksum mismatch for {path.name}: {digest}")
        print(json.dumps({"asset": path.name, "digest": digest, "verified": True}), flush=True)
        if kind == "deb":
            unpacked = dest / "deb"
            subprocess.run(["dpkg-deb", "-x", str(path), str(unpacked)], check=True)
        elif kind == "appimage":
            path.chmod(0o755)
            unpacked = dest / "appimage"
            unpacked.mkdir(exist_ok=True)
            with (dest / "extract.log").open("w") as log:
                subprocess.run([str(path), "--appimage-extract"], cwd=unpacked,
                               stdout=log, stderr=subprocess.STDOUT, check=True)
        else:
            unpacked = dest / "tar"
            unpacked.mkdir(exist_ok=True)
            subprocess.run(["tar", "-xzf", str(path), "-C", str(unpacked)], check=True)
