"""Check the repaired payload bytes; historical scores are not fresh probes."""
import hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parents[2]
release=json.loads((root/'validation/question_release/release.json').read_bytes())
for name,digest in release['frozen_task_files'].items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest,name
assert release['revision_kind']=='security-and-coverage-repair'
print('FROZEN_R1_REPAIR_OK',release['task'])
