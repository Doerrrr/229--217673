"""Author-only Windows/Unix curation regression; NOT a Linux publication test."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
spec = importlib.util.spec_from_file_location("checks", ROOT / "tests/test_outputs.py")
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)
original_run = subprocess.run

with tempfile.TemporaryDirectory() as directory:
    temporary = Path(directory)
    shutil.copy2(ROOT / "solution/oracle_curate.py", temporary / "curate.py")
    shutil.copy2(ROOT / "solution/oracle_publication.py", temporary / "publication.py")

    def local_run(argv, **kwargs):
        if argv[0] == checks.COMMAND:
            argv = [sys.executable, str(temporary / "curate.py"), *argv[1:]]
            argv = [str(ROOT / "environment/data" / arg[6:]) if isinstance(arg, str) and arg.startswith("/data/") else arg for arg in argv]
        kwargs.pop("preexec_fn", None)  # Portable author check is not a trust-isolation claim.
        return original_run(argv, **kwargs)

    subprocess.run = local_run
    results = []
    for name, weight, function in checks.LEGACY_CHECKS:
        item = {"name": name, "passed": False}
        try:
            function()
            item["passed"] = True
        except BaseException as exc:
            item["error"] = str(exc)
        results.append(item)
    print(json.dumps({"scope": "portable reference curation only", "checks": results}, indent=2))
    raise SystemExit(0 if all(item["passed"] for item in results) else 1)
