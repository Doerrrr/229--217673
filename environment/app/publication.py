"""Local batch working directory adapter."""
import json
from pathlib import Path

def write_draft(store,ticket,value):
    folder=Path(store)/'sessions'/ticket;folder.mkdir(parents=True,exist_ok=True)
    (folder/'draft.json').write_text(json.dumps(value)+'\n')
    return folder

def legacy(assignment,calls):return dict(assignment=assignment,calls=calls)
