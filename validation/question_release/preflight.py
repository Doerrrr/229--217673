"""Check the repaired payload bytes; historical scores are not fresh probes."""
import hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parents[2]
release=json.loads((root/'validation/question_release/release.json').read_bytes())
optional_notes={'agent_prompt.txt','README.md'}
missing_notes=[]
for name,digest in release['frozen_task_files'].items():
    path=root/name
    if name in optional_notes and not path.exists():
        missing_notes.append(name)
        continue
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest,name
assert release['revision_kind']=='security-and-coverage-repair'
if missing_notes:print('OPTIONAL_NOTES_ABSENT',','.join(missing_notes))
print('FROZEN_R1_REPAIR_OK',release['task'])
