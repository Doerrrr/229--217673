import runpy
from pathlib import Path
runpy.run_path(str(Path(__file__).resolve().parents[1]/'question_release/author_checks.py'),run_name='__main__')
