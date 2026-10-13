"""Audit the platform adapter against the immutable DDI-008 trial source."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import zipfile


def sha(body):
    return hashlib.sha256(body).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--frozen', type=Path, required=True)
    p.add_argument('--answer', type=Path, required=True)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    reference = json.loads((Path(__file__).parent/'reference_provenance.json').read_text(encoding='utf-8'))
    assert sha(a.answer.read_bytes()) == reference['answer_sha256']
    with zipfile.ZipFile(a.answer) as z:
        assert (root/'solution/oracle_lineage.py').read_bytes() == z.read('app/lineage.py'), 'Reference bytes changed'
    with zipfile.ZipFile(a.frozen/'DDI-008_符号化证据来源与精确可靠性_v01_评分包_2febd68.zip') as z:
        public = ['instruction.md','task.toml','environment/Dockerfile','environment/app/lineage.py',
                  'environment/bin/ddi-lineage','environment/data/evidence_graph.json',
                  'environment/data/stress_graph.json']
        hidden = ['tests/test.sh','tests/test_outputs.py','tests/certificate_check.py','tests/fixtures.py']
        for name in public + hidden:
            assert (root/name).read_bytes() == z.read('DDI-008_v01_evaluator_private/task/'+name), name+' differs'
    for name in ('.github/workflows/harbor-validation.yml','environment/data/drug_list.csv',
                 'environment/data/DDI_event.csv','environment/data/newddi.csv'):
        baseline = subprocess.check_output(['git','show','bee6005:'+name], cwd=root)
        current = (root/name).read_bytes().replace(b'\r\n', b'\n')
        assert current == baseline.replace(b'\r\n', b'\n'), 'Protected content changed: '+name
    candidate = [root/'environment/app/lineage.py',root/'environment/bin/ddi-lineage',
                 root/'environment/data/evidence_graph.json',root/'environment/data/stress_graph.json']
    hidden_files = [root/name for name in hidden]+[root/'solution/oracle_lineage.py',root/'solution/solve.sh']
    assert not any(c.read_bytes()==h.read_bytes() for c in candidate for h in hidden_files), 'Duplicate hidden file in image'
    print(json.dumps({'task':'DDI-008','public_contract':'UNCHANGED','checks':20,
                      'frozen_grader':'UNCHANGED','reference_source':'EXACT_EXTERNAL_BYTES',
                      'original_csv':'PRESERVED','workflow':'PRESERVED','candidate_hidden_duplicates':0}))


if __name__ == '__main__':
    main()
