"""Portable local checks. Does not replace Harbor container validation."""
import argparse
import json
import sys
from pathlib import Path

from check_boundary import check_boundary

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
import test_outputs as verifier

parser=argparse.ArgumentParser()
parser.add_argument('--mode',choices=('oracle','nop','scaffold_only','greedy','reuse','forward_only'),default='oracle')
args=parser.parse_args()
print(json.dumps({'boundary_preflight':check_boundary(ROOT)}),flush=True)
output=ROOT/'.trials'/('release-'+args.mode)
output.mkdir(parents=True,exist_ok=True)
verifier.DATA=ROOT/'environment/data'
if args.mode == 'oracle':
    verifier.COMMAND=[sys.executable,str(ROOT/'solution/oracle_release.py')]
elif args.mode == 'nop':
    verifier.COMMAND=[sys.executable,str(ROOT/'environment/app/release.py')]
else:
    verifier.COMMAND=[sys.executable,str(ROOT/'validation/mutant_release.py'),args.mode]
sys.argv=[sys.argv[0],'--reward-file',str(output/'reward.txt'),'--details-file',str(output/'details.json')]
verifier.main()
details=json.loads((output/'details.json').read_text())
score=details['reward']
if args.mode == 'oracle' and score != 1.0:
    raise SystemExit('Oracle must pass every check')
if args.mode == 'nop' and score != 0.0:
    raise SystemExit('NOP must fail all checks')
if args.mode not in ('oracle','nop') and score == 1.0:
    raise SystemExit('Negative control was not detected')
