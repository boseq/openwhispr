import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys

root=Path(sys.argv[1]).resolve()
source=Path(sys.argv[2]).resolve()
out=root/'results/compiler-controls'
out.mkdir(parents=True,exist_ok=True)
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
specs=json.loads((root/'manifest.json').read_text())
app=root/specs['head-deb']['app']
binding=next(app.rglob('better_sqlite3.node'))
original=binding.read_bytes()
with (out/'preflight.log').open('w') as log:
    preflight=subprocess.run(['node',source/'scripts/verify-linux-sqlite.js',app],stdout=log,
                             stderr=subprocess.STDOUT,timeout=160)
(out/'preflight.json').write_text(json.dumps({'exit':preflight.returncode,
    'binding_sha256':hashlib.sha256(original).hexdigest()},indent=2))
if preflight.returncode:
    subprocess.run(['python3',Path(__file__).with_name('runtime-diagnostics.py'),app,out/'runtime'],
                   check=True,timeout=240)
    raise RuntimeError('Original packaged binding preflight failed; do not interpret compiler controls')
package=json.loads((source/'package.json').read_text())
electron=package['devDependencies']['electron'].lstrip('^~')
assert subprocess.check_output(['gcc-15','-dumpversion'],text=True).strip()=='15'
assert subprocess.check_output(['g++-15','-dumpversion'],text=True).strip()=='15'
with (out/'compiler-config.log').open('w') as log:
    for command in [['g++-15','-v'],['g++-15','-Q','--help=target']]:
        subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
records=[]
try:
    for label,flags in [('default',None),('avx2-control','-march=x86-64-v3 -mtune=generic'),
                        ('baseline','-march=x86-64 -mtune=generic -mno-avx -mno-avx2')]:
        dest=out/label
        dest.mkdir(exist_ok=True)
        env={**os.environ,'CC':'gcc-15','CXX':'g++-15','DEBUG':'electron-rebuild'}
        env.pop('CFLAGS',None)
        env.pop('CXXFLAGS',None)
        if flags is not None:
            env.update(CFLAGS=flags,CXXFLAGS=flags)
        with (dest/'build.log').open('w') as log:
            subprocess.run(['node',source/'node_modules/@electron/rebuild/lib/cli.js','--force',
                            '--only','better-sqlite3','--build-from-source','--arch','x64',
                            '--version',electron,'--module-dir',source],env=env,cwd=source,
                           stdout=log,stderr=subprocess.STDOUT,check=True,timeout=360)
        built=source/'node_modules/better-sqlite3/build/Release/better_sqlite3.node'
        shutil.copy2(built,binding)
        shutil.copy2(built,dest/'better_sqlite3.node')
        with (dest/'compiler.txt').open('w') as log:
            subprocess.run(['objdump','-s','-j','.comment',built],stdout=log,check=True)
        assembly=subprocess.check_output(['objdump','-d','--no-show-raw-insn',built],text=True)
        vex=[line for line in assembly.splitlines() if re.match(r'^\s*[0-9a-f]+:\s+v[a-z][a-z0-9]*\b',line)]
        with (dest/'probe.log').open('w') as log:
            result=subprocess.run(['node',source/'scripts/verify-linux-sqlite.js',app],stdout=log,
                                  stderr=subprocess.STDOUT,timeout=160)
        text=(dest/'probe.log').read_text()
        sigill=result.returncode!=0 and 'uncaught target signal 4' in text
        if label=='baseline':
            passed=result.returncode==0 and not vex
        elif label=='avx2-control':
            passed=sigill and bool(vex)
        else:
            passed=result.returncode==0 or sigill
        record={'label':label,'compiler':'GCC 15','cflags':flags,'electron':electron,
                'binding_sha256':hashlib.sha256(built.read_bytes()).hexdigest(),
                'v_mnemonic_count':len(vex),'probe_exit':result.returncode,'sigill':sigill,'passed':passed}
        records.append(record)
        (out/'summary.json').write_text(json.dumps(records,indent=2))
        print(json.dumps(record),flush=True)
        if not passed: raise RuntimeError(f'GCC15 control failed: {label}')
finally:
    binding.write_bytes(original)
