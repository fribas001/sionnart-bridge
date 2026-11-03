"""Scoped Windows x64 JIT object-format adapter for this Sionna runtime.

Loaded before Dr.Jit's native extension. A version/hash mismatch fails clearly.
SIONNA_LLVM_BATCH_ADAPTER=off is for controlled baseline tests or rollback.
No geometry, coefficients, optimization flags or numeric types are modified.
"""
import os


def configure():
    if os.name != 'nt':
        return {'status':'not_applicable'}
    if os.environ.get('SIONNA_LLVM_BATCH_ADAPTER','on') == 'off':
        return {'status':'disabled_for_diagnostic'}
    import ctypes
    from ctypes import wintypes
    import hashlib,json,platform,tempfile
    from importlib.metadata import version
    from pathlib import Path
    if platform.machine().lower() not in ('amd64','x86_64'):
        raise RuntimeError('The Sionna LLVM adapter is validated only on Windows x64.')
    base=Path(__file__).resolve().parent
    bundle=base/'_bridge_llvm';meta=json.loads((bundle/'manifest.json').read_text())
    for name in ('drjit','mitsuba'):
        if version(name)!=meta[name]:
            raise RuntimeError('Sionna LLVM adapter package version mismatch: '+name)
    original=Path(meta['original_llvm']);adapter=bundle/'SionnaLLVM.dll'
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    for path,key in [(original,'original_llvm_sha256'),(adapter,'adapter_sha256'),(base/'drjit-core.dll','core_sha256')]:
        if sha(path)!=meta[key]:
            raise RuntimeError('Sionna LLVM adapter binary changed; revalidate before use: '+str(path))
    configured=os.environ.get('DRJIT_LIBLLVM_PATH')
    if configured and Path(configured).resolve() not in (original.resolve(),adapter.resolve()):
        raise RuntimeError('A different LLVM was requested. Disable the local Sionna adapter explicitly before testing another compiler.')
    # The original must be loaded first, so PE export forwarders resolve to
    # this verified DLL. Pin both modules for safe Windows FLS destruction.
    original_library=ctypes.WinDLL(str(original))
    adapter_library=ctypes.WinDLL(str(adapter))
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    pin=kernel.GetModuleHandleExW
    pin.argtypes=[wintypes.DWORD,wintypes.LPCWSTR,ctypes.POINTER(wintypes.HMODULE)]
    pin.restype=wintypes.BOOL
    for path in (original,adapter):
        handle=wintypes.HMODULE()
        if not pin(1,str(path),ctypes.byref(handle)):
            raise ctypes.WinError(ctypes.get_last_error())
    triple=adapter_library.LLVMGetDefaultTargetTriple
    triple.argtypes=[];triple.restype=ctypes.c_void_p
    dispose=adapter_library.LLVMDisposeMessage
    dispose.argtypes=[ctypes.c_void_p];dispose.restype=None
    ptr=triple()
    try:target=ctypes.string_at(ptr).decode('ascii')
    finally:dispose(ptr)
    if target!=meta['target']:raise RuntimeError('Unexpected LLVM adapter target')
    os.environ['DRJIT_LIBLLVM_PATH']=str(adapter)
    # Legacy Dr.Jit hashes do not distinguish object format. Never reuse a
    # COFF cache as ELF, even when both contain an equivalent numerical kernel.
    cache=Path(os.environ.get('DRJIT_CACHE_DIR',tempfile.gettempdir()))
    if cache.name!='sionna-llvm-elf-v1':cache=cache/'sionna-llvm-elf-v1'
    cache.mkdir(parents=True,exist_ok=True)
    os.environ['DRJIT_CACHE_DIR']=str(cache.resolve())
    return dict(status='enabled',target=target,original_llvm=str(original),adapter=str(adapter),cache=str(cache.resolve()))
