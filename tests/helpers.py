"""Shared test helpers. Tests use only the standard library (unittest) and run under pytest too."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / "skills" / "api-architect-ai"
SCRIPTS = SKILL_DIR / "scripts"
FIXTURES = ROOT / "tests" / "fixtures"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def run_script(name: str, *args: str, hide_yaml: bool = False):
    """Run a bundled script in a subprocess; returns CompletedProcess.

    hide_yaml=True simulates an environment without PyYAML installed.
    """
    script = str(SCRIPTS / name)
    if hide_yaml:
        code = ("import sys, runpy; sys.modules['yaml'] = None; "
                "sys.argv = %r; runpy.run_path(%r, run_name='__main__')" % ([script, *args], script))
        cmd = [sys.executable, "-c", code]
    else:
        cmd = [sys.executable, script, *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=str(ROOT))


def run_json(name: str, *args: str):
    proc = run_script(name, *args, "--format", "json")
    return proc.returncode, json.loads(proc.stdout)
