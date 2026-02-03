"""Make token-usage.py importable as token_usage for tests."""
import importlib
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "token_usage", Path(__file__).parent / "token-usage.py"
)
mod = importlib.util.module_from_spec(spec)
sys.modules["token_usage"] = mod
spec.loader.exec_module(mod)
