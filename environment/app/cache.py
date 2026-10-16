"""Working-result cache used by local batch operators."""
import json
from pathlib import Path

class Cache:
    def __init__(self,folder):self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True)
    def get(self,cost):
        p=self.folder/f'{cost}.json'
        return json.loads(p.read_text()) if p.exists() else None
    def put(self,cost,value):(self.folder/f'{cost}.json').write_text(json.dumps(value))
