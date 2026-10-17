"""Read-only fixed-payload and public/private boundary check."""
from pathlib import Path
import ast,hashlib,json
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    manifest=json.loads((ROOT/'validation/eb032_platform/payload.json').read_bytes())
    for relative,expected in manifest['files'].items():assert sha(ROOT/relative)==expected,relative
    public=[p for folder in ('app','bin','packet') for p in (ROOT/'environment'/folder).rglob('*') if p.is_file()]
    hidden=[p for folder in ('solution','tests') for p in (ROOT/folder).rglob('*') if p.is_file()]
    assert not ({sha(p) for p in public}&{sha(p) for p in hidden}),'public/private full-file overlap'
    for folder in ('environment/app','solution','tests'):
        for p in (ROOT/folder).rglob('*.py'):ast.parse(p.read_bytes(),filename=str(p))
    expected=json.loads((ROOT/'validation/eb032_platform/payload.json').read_bytes())['candidate_image_files']
    actual={p.relative_to(ROOT/'environment').as_posix():sha(p) for p in public}
    assert actual==expected,'candidate image file inventory changed'
    copies=[line.strip() for line in (ROOT/'environment/Dockerfile').read_text().splitlines() if line.startswith('COPY ')]
    assert copies==['COPY app/ app/','COPY bin/ bin/','COPY packet/ packet/']
    assert not (ROOT/'reference_project').exists()
    print(json.dumps(dict(status='PASS',payload_files=len(manifest['files']),visible_files=len(public),hidden_files=len(hidden),exact_hidden_duplicates=0,registered_oracle=True, oracle_scope="FINITE_WITNESS_STARTUP_CONTROL_ONLY")))
if __name__=='__main__':main()
