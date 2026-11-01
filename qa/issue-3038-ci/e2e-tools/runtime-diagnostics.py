import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

app = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()
out.mkdir(parents=True, exist_ok=True)
binary = app / 'open-whispr-app'
sqlite = app / 'resources/app.asar/node_modules/better-sqlite3'
env = {**os.environ, 'ELECTRON_RUN_AS_NODE': '1'}
with (out/'environment.log').open('w') as log:
    for command in [['uname','-a'], ['ldd','--version'], ['qemu-x86_64','--version'], ['ldd',binary]]:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=15)
records = []
for cpu in ['Nehalem', 'IvyBridge', 'Haswell,-avx2', 'Haswell']:
    for label, args in [('system-true', ['/usr/bin/true']),
                        ('bare-electron', [binary,'-e',"console.log('BARE_ELECTRON_OK')"])]:
        with (out/f'{cpu}-{label}.log').open('w') as log:
            try:
                result = subprocess.run(['qemu-x86_64','-cpu',cpu,*args],env=env,
                                        stdout=log,stderr=subprocess.STDOUT,timeout=20)
                code = result.returncode
            except subprocess.TimeoutExpired:
                code = 'timeout'
        records.append({'cpu':cpu,'test':label,'exit':code})
(out/'controls.json').write_text(json.dumps(records,indent=2))
expression = "console.log('ELECTRON_OK'); const D=require(process.argv[1]); console.log('SQLITE_LOADED'); const db=new D(':memory:'); console.log('DATABASE_OPENED'); db.close();"
commands = out/'commands.gdb'
commands.write_text(f'set pagination off\nset confirm off\nfile {binary}\n'
                    'target remote 127.0.0.1:12450\nhandle SIGPIPE nostop noprint pass\ncontinue\n'
                    'thread apply all bt 15\ninfo registers rip\nx/16i $pc-16\ninfo sharedlibrary\ninfo files\ndetach\nquit\n')
with (out/'target.log').open('w') as log:
    proc = subprocess.Popen(['qemu-x86_64','-cpu','Nehalem','-g','12450',binary,'-e',expression,sqlite],
                            env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    try:
        time.sleep(1)
        with (out/'gdb.log').open('w') as trace:
            try:
                result = subprocess.run(['gdb','-q','-batch','-x',commands],stdout=trace,
                                        stderr=subprocess.STDOUT,timeout=35)
                (out/'gdb-exit.json').write_text(json.dumps({'exit':result.returncode}))
            except subprocess.TimeoutExpired:
                (out/'gdb-exit.json').write_text(json.dumps({'exit':'timeout'}))
    finally:
        try:
            os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
print(json.dumps(records),flush=True)
