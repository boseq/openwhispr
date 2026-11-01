import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request

root = Path(sys.argv[1]).resolve()
vm = root.parent / "issue3038-vm"
vm.mkdir(exist_ok=True)
evidence = root / "results/full-vm-host"
evidence.mkdir(parents=True, exist_ok=True)
base_url = "https://cloud-images.ubuntu.com/noble/current/"
name = "noble-server-cloudimg-amd64.img"
with urllib.request.urlopen(base_url + "SHA256SUMS", timeout=60) as response:
    checksums = response.read().decode()
expected = next(line.split()[0] for line in checksums.splitlines() if line.split()[-1].lstrip("*") == name)
image = vm / name
subprocess.run(["curl", "-fL", "--retry", "3", "-o", image, base_url + name], check=True)
actual = hashlib.file_digest(image.open("rb"), "sha256").hexdigest()
if actual != expected:
    raise RuntimeError("Ubuntu cloud image checksum mismatch")
(evidence / "image.json").write_text(json.dumps({"url": base_url + name, "sha256": actual}, indent=2))
key = vm / "key"
subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", key], check=True)
public_key = key.with_suffix(".pub").read_text().strip()
config = vm / "user-data"
config.write_text("""#cloud-config
ssh_authorized_keys:
  - """ + public_key + """
package_update: true
packages:
  - dbus-x11
  - xvfb
  - xauth
  - scrot
  - openbox
  - libgtk-3-0t64
  - libnss3
  - libasound2t64
  - libgbm1
  - libxss1
  - libxshmfence1
  - libxkbfile1
  - libpulse0
  - libpipewire-0.3-0t64
  - libfuse2t64
  - fuse
runcmd:
  - touch /var/tmp/issue3038-ready
""")
metadata = vm / "meta-data"
metadata.write_text("instance-id: issue3038-e2e\nlocal-hostname: issue3038-e2e\n")
seed = vm / "seed.img"
subprocess.run(["cloud-localds", seed, config, metadata], check=True)
disk = vm / "guest.qcow2"
subprocess.run(["qemu-img", "create", "-f", "qcow2", "-F", "qcow2", "-b", image, disk, "20G"], check=True)
variables = vm / "OVMF_VARS.fd"
shutil.copy2("/usr/share/OVMF/OVMF_VARS_4M.fd", variables)
subprocess.run(["chmod", "-R", "a+rwX", root], check=True)
command = ["qemu-system-x86_64", "-machine", "q35", "-accel", "tcg,thread=multi",
           "-cpu", "IvyBridge", "-smp", "4", "-m", "6144", "-display", "none", "-monitor", "none",
           "-serial", f"file:{evidence / 'serial.log'}",
           "-drive", "if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd",
           "-drive", f"if=pflash,format=raw,file={variables}",
           "-drive", f"file={disk},if=virtio,format=qcow2",
           "-drive", f"file={seed},if=virtio,format=raw",
           "-netdev", "user,id=net0,hostfwd=tcp:127.0.0.1:2222-:22",
           "-device", "virtio-net-pci,netdev=net0",
           "-virtfs", f"local,path={root},mount_tag=qa,security_model=mapped-xattr,id=qa"]
(evidence / "qemu-command.json").write_text(json.dumps(command, indent=2))
ssh = ["ssh", "-i", str(key), "-p", "2222", "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=accept-new",
       "-o", f"UserKnownHostsFile={vm / 'known_hosts'}", "-o", "ConnectTimeout=4", "ubuntu@127.0.0.1"]
with (evidence / "qemu.log").open("w") as log:
    guest = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
    try:
        ready = False
        for attempt in range(90):
            if guest.poll() is not None:
                raise RuntimeError(f"QEMU exited: {guest.returncode}")
            try:
                check = subprocess.run([*ssh, "test -f /var/tmp/issue3038-ready"], stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, timeout=8)
                ready = check.returncode == 0
            except subprocess.TimeoutExpired:
                ready = False
            if ready:
                ready = True
                break
            if attempt % 6 == 0:
                print(f"Waiting for full IvyBridge guest/cloud-init ({attempt * 10}s)", flush=True)
            time.sleep(10)
        if not ready:
            raise RuntimeError("Guest/cloud-init did not become ready")
        script = """set -e
sudo mkdir -p /mnt/qa
sudo mount -t 9p -o trans=virtio,version=9p2000.L qa /mnt/qa
sudo modprobe fuse
mkdir /mnt/qa/results/share-preflight
printf ok > /mnt/qa/results/share-preflight/probe
ulimit -c 0
E2E_SCRATCH=/var/tmp/issue3038 dbus-run-session -- xvfb-run -a -s '-screen 0 1280x900x24' /usr/bin/python3 /mnt/qa/tools/e2e.py /mnt/qa cpu-vm
"""
        with (evidence / "guest-test.log").open("w") as output:
            result = subprocess.run([*ssh, "bash -s"], input=script, text=True, stdout=output,
                                    stderr=subprocess.STDOUT, timeout=1500)
        if result.returncode:
            raise RuntimeError(f"Guest E2E failed: {result.returncode}")
    finally:
        guest.terminate()
        try:
            guest.wait(timeout=15)
        except subprocess.TimeoutExpired:
            guest.kill()
            guest.wait()
