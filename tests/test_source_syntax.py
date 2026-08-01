import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "sionnart_bridge"


def test_python_sources_parse():
    for source in SOURCE.glob("*.py"):
        ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
