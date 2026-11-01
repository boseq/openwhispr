import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(sys.argv[1]).resolve()
artifacts = Path(sys.argv[2]).resolve()
payloads = root / "payloads"
payloads.mkdir(exist_ok=True)
# Only archives are consumed below; discard the unused duplicate app first.
unpacked = artifacts / "linux-unpacked"
if unpacked.exists():
    shutil.rmtree(unpacked)

def app_under(directory):
    candidates = list(directory.rglob("open-whispr-app"))
    if len(candidates) != 1:
        raise RuntimeError(f"Expected one app in {directory}, got {candidates}")
    return candidates[0].parent

specs = {}
for label, version in (("old", "1.10.4"), ("base", "1.11.0")):
    app = app_under(root / "downloads" / version / "deb")
    specs[f"{label}-deb"] = {"app": str(app.relative_to(root)),
                             "launcher": str((app / "open-whispr").relative_to(root)),
                             "version": version}

hashes = []
for kind, pattern in (("deb", "*.deb"), ("rpm", "*.rpm"), ("tar", "*.tar.gz"),
                      ("appimage", "*.AppImage")):
    matches = list(artifacts.glob(pattern))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {kind} artifact, got {matches}")
    archive = matches[0]
    dest = payloads / kind
    dest.mkdir(exist_ok=True)
    if kind == "deb":
        subprocess.run(["dpkg-deb", "-x", str(archive), str(dest)], check=True)
    elif kind == "rpm":
        with subprocess.Popen(["rpm2cpio", str(archive)], stdout=subprocess.PIPE) as converted:
            subprocess.run(["cpio", "-idm", "--quiet", "--no-preserve-owner"], stdin=converted.stdout, cwd=dest, check=True)
            converted.stdout.close()
            if converted.wait():
                raise RuntimeError("rpm2cpio failed")
    elif kind == "tar":
        subprocess.run(["tar", "-xzf", str(archive), "-C", str(dest)], check=True)
    else:
        archive.chmod(0o755)
        with (root / "appimage-extract.log").open("w") as log:
            subprocess.run([str(archive), "--appimage-extract"], cwd=dest, stdout=log,
                           stderr=subprocess.STDOUT, check=True)
    app = app_under(dest)
    launcher = app / ("AppRun" if kind == "appimage" else "open-whispr")
    specs[f"head-{kind}"] = {"app": str(app.relative_to(root)),
                             "launcher": str(launcher.relative_to(root)), "version": "1.11.0"}
    binding = next(app.rglob("better_sqlite3.node"))
    hashes.append({"format": kind, "archive": archive.name,
                   "archive_sha256": hashlib.file_digest(archive.open("rb"), "sha256").hexdigest(),
                   "binding_sha256": hashlib.file_digest(binding.open("rb"), "sha256").hexdigest()})
    if kind == "appimage":
        runtime = root / "head.AppImage"
        shutil.copy2(archive, runtime)
        specs["head-appimage-runtime"] = {**specs["head-appimage"], "launcher": "head.AppImage"}
    archive.unlink()

if len({item["binding_sha256"] for item in hashes}) != 1:
    raise RuntimeError("Head formats contain different SQLite bindings")
(root / "manifest.json").write_text(json.dumps(specs, indent=2))
(root / "package-hashes.json").write_text(json.dumps(hashes, indent=2))
shutil.copy2(shutil.which("node"), root / "tools/node")
print(json.dumps(hashes), flush=True)
