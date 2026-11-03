"""Release safety gates: unsupported binaries and user edits must be preserved."""
import importlib.util,json,sys
from pathlib import Path
from types import SimpleNamespace
import pytest

spec=importlib.util.spec_from_file_location('llvm_adapter_manager',Path(__file__).resolve().parents[1]/'tools/windows_llvm_adapter/manage.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

@pytest.mark.parametrize('difference',['version','architecture','llvm','core'])
def test_preflight_rejects_unsupported_stack_without_writing(tmp_path,monkeypatch,difference):
    package=tmp_path/'drjit';package.mkdir();llvm=tmp_path/'llvm';llvm.mkdir()
    (package/'drjit-core.dll').write_bytes(b'core');(llvm/'LLVM-C.dll').write_bytes(b'llvm')
    monkeypatch.setattr(m,'os',SimpleNamespace(name='nt'))
    monkeypatch.setattr(m,'LLVM_SHA',m.sha(llvm/'LLVM-C.dll'));monkeypatch.setattr(m,'CORE_SHA',m.sha(package/'drjit-core.dll'))
    info=dict(site=str(tmp_path),machine='AMD64',versions={'sionna-rt':'2.1.0','mitsuba':'3.9.1','drjit':'1.5.0'})
    if difference=='version':info['versions']['drjit']='1.6.0'
    elif difference=='architecture':info['machine']='ARM64'
    elif difference=='llvm':(llvm/'LLVM-C.dll').write_bytes(b'other LLVM')
    else:(package/'drjit-core.dll').write_bytes(b'other core')
    before={p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    monkeypatch.setattr(m.subprocess,'check_output',lambda *a,**kw:json.dumps(info))
    with pytest.raises(RuntimeError):m.preflight(Path(sys.executable),llvm)
    assert {p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}==before

def test_modified_initializer_is_never_overwritten(tmp_path,monkeypatch):
    init=tmp_path/'__init__.py';init.write_bytes(b'# user customization\n')
    monkeypatch.setattr(m,'preflight',lambda *a:(tmp_path,{}))
    monkeypatch.setattr(sys,'argv',['manage.py','--python',sys.executable,'--llvm-bin',str(tmp_path),'--apply'])
    with pytest.raises(RuntimeError,match='unmodified'):m.main()
    assert init.read_bytes()==b'# user customization\n'
    assert list(tmp_path.iterdir())==[init]
