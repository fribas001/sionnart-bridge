"""Build/install a strictly scoped Windows CPU compatibility adapter.

Default is a read-only preflight. Use --apply to change a dedicated runtime,
or --restore to restore its original Dr.Jit initializer. No solver changes.
"""
import argparse
from datetime import datetime,timezone
import hashlib,json,os,re,shutil,subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent
LLVM_SHA='4f0b315747bd0249541eb7f6488358fc414b4e00d64e682ec0545f51e59ce9d0'
CORE_SHA='a45687435dd75f57870e19cc717c6d6a0eb062687a80875c03660a5e7a69adc6'
INIT_SHA='840c308340e4734a157a6580e53c3073c335210a0630a1311f9f28dddc90e5f9'
ADAPTER_SHA='9b882e23c74cc9d078c22b086a9ee59da301bbee9fb9830194776a653da2726d'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def preflight(python,llvm):
    if os.name!='nt':raise RuntimeError('This adapter is scoped to Windows x64.')
    code='import json,sysconfig,platform,importlib.metadata as m;print(json.dumps(dict(site=sysconfig.get_path("purelib"),machine=platform.machine(),versions={n:m.version(n) for n in ("sionna-rt","mitsuba","drjit")})))'
    info=json.loads(subprocess.check_output([str(python),'-B','-c',code],text=True))
    if info['machine'].lower() not in ('amd64','x86_64'):raise RuntimeError('Windows x64 is required.')
    if info['versions']!={'sionna-rt':'2.1.0','mitsuba':'3.9.1','drjit':'1.5.0'}:raise RuntimeError('Unsupported package versions: '+str(info['versions']))
    package=Path(info['site'])/'drjit'
    for path,expected in [(llvm/'LLVM-C.dll',LLVM_SHA),(package/'drjit-core.dll',CORE_SHA)]:
        if sha(path)!=expected:raise RuntimeError('Unsupported binary hash: '+str(path))
    return package,info

def build(llvm,package,out):
    out.mkdir(parents=True,exist_ok=True)
    names=re.findall(r'^  Name: (.+)$',subprocess.check_output([str(llvm/'llvm-readobj.exe'),'--coff-exports',str(llvm/'LLVM-C.dll')],text=True),re.M)
    if len(names)!=1227 or 'LLVMGetDefaultTargetTriple' not in names:raise RuntimeError('Unexpected LLVM exports.')
    shutil.copyfile(HERE/'sionna_llvm_elf.c',out/'bridge.c')
    (out/'original.def').write_text('LIBRARY LLVM-C.dll\nEXPORTS\nLLVMCreateMessage\n')
    (out/'bridge.def').write_text('LIBRARY SionnaLLVM.dll\nEXPORTS\n'+'\n'.join(n+'='+('bridge_GetDefaultTargetTriple' if n=='LLVMGetDefaultTargetTriple' else 'LLVM-C.'+n) for n in names)+'\n')
    commands=[['llvm-dlltool.exe','-d','original.def','-l','llvm-original.lib','-m','i386:x86-64'],
              ['clang-cl.exe','/c','/O2','/GS-','/Zl','bridge.c','/Fobridge.obj'],
              ['lld-link.exe','/dll','/noentry','/nodefaultlib','/Brepro','/machine:x64','/def:bridge.def','/out:SionnaLLVM.dll','bridge.obj','llvm-original.lib']]
    for command in commands:subprocess.run([str(llvm/command[0]),*command[1:]],cwd=out,check=True)
    if sha(out/'SionnaLLVM.dll')!=ADAPTER_SHA:raise RuntimeError('Build differs from the stress-tested adapter; refusing installation.')
    meta=dict(schema='sionna_llvm_elf_v1',drjit='1.5.0',mitsuba='3.9.1',llvm_version=[22,1,8],
              original_llvm=str(llvm/'LLVM-C.dll'),original_llvm_sha256=LLVM_SHA,core_sha256=CORE_SHA,
              adapter_sha256=ADAPTER_SHA,source_sha256=sha(out/'bridge.c'),exports=len(names),
              target='x86_64-pc-windows-msvc-elf',commands=commands)
    (out/'manifest.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--python',required=True,type=Path,help='Python executable in the dedicated Sionna runtime')
    ap.add_argument('--llvm-bin',required=True,type=Path,help='LLVM 22.1.8 bin directory (including build tools)')
    ap.add_argument('--build-dir',type=Path,default=Path('build/windows_llvm_adapter'))
    mode=ap.add_mutually_exclusive_group();mode.add_argument('--apply',action='store_true');mode.add_argument('--restore',action='store_true')
    args=ap.parse_args();python=args.python.resolve();llvm=args.llvm_bin.resolve()
    package,info=preflight(python,llvm);init=package/'__init__.py';bundle=package/'_bridge_llvm'
    receipt_path=bundle/'installation.json'
    if args.restore:
        receipt=json.loads(receipt_path.read_text());backup=bundle/'drjit_init.before.py'
        if receipt.get('restored'):raise RuntimeError('This installation is already restored.')
        if sha(init)!=receipt['after'] or sha(backup)!=receipt['before']:raise RuntimeError('Runtime or backup changed; refusing to overwrite it.')
        init.write_bytes(backup.read_bytes());receipt['restored']=datetime.now(timezone.utc).isoformat()
        receipt_path.write_text(json.dumps(receipt,indent=2));print('Original initializer restored; inert adapter and backup retained.');return
    if sha(init)!=INIT_SHA:raise RuntimeError('Expected an unmodified Dr.Jit 1.5.0 initializer; use a fresh dedicated environment.')
    if bundle.exists() or (package/'_bridge_llvm_batch.py').exists():raise RuntimeError('Adapter files already exist; refusing to overwrite them.')
    info.update(runtime=str(python),llvm=str(llvm),scope='Windows x64 CPU only; LLVM object format and module lifetime; no physics changes')
    print(json.dumps(info,indent=2))
    if not args.apply:print('Preflight passed. No files changed. Add --apply to build and install.');return
    build(llvm,package,args.build_dir.resolve())
    before=init.read_bytes();newline=b'\r\n' if b'\r\n' in before else b'\n'
    marker=b'from __future__ import annotations'+newline
    if before.count(marker)!=1:raise RuntimeError('Unexpected initializer layout.')
    hook=newline.join((b'',b'from ._bridge_llvm_batch import configure as _bridge_configure_llvm',b'_bridge_llvm_batch_status = _bridge_configure_llvm()',b''))
    after=before.replace(marker,marker+hook,1)
    bundle.mkdir()
    for name in ('manifest.json','SionnaLLVM.dll'):shutil.copyfile(args.build_dir/name,bundle/name)
    (bundle/'drjit_init.before.py').write_bytes(before)
    helper=package/'_bridge_llvm_batch.py';shutil.copyfile(HERE/'sionna_llvm_batch.py',helper)
    receipt=dict(before=INIT_SHA,after=hashlib.sha256(after).hexdigest(),helper_sha256=sha(helper),adapter_sha256=ADAPTER_SHA,
                 installed_utc=datetime.now(timezone.utc).isoformat(),versions=info['versions'])
    receipt_path.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    init.write_bytes(after)
    print('Adapter installed. Start a new Python/Blender worker and run the validation probe.')

if __name__=='__main__':main()
