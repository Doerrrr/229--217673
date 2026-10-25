import hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parents[2]
release=json.loads((root/'validation/question_release/release.json').read_bytes())
for name,digest in release['frozen_task_files'].items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest,name
assert release['local_gate']['normal'] and release['local_gate']['reward']<=.5
print('FROZEN_TASK_OK',release['task'],release['local_gate']['reward'])
