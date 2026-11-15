from pathlib import Path
import argparse,json,subprocess,time
p=argparse.ArgumentParser();p.add_argument('label');p.add_argument('--mode',default='oracle');p.add_argument('--image',default='sha256:7f106ea45a5e565a2910c2c1d911f573244034d71464046264624e9a2962b554');a=p.parse_args()
work=Path(__file__).resolve().parent;repo=work.parent/'repository';logs=work/(a.label+'-logs');logs.mkdir()
args=['docker','run','--rm','--network','none','--cpus','2','--memory','2048m','--pids-limit','256','--security-opt','no-new-privileges','--mount',f'type=bind,source={repo},target=/root/repo,readonly','--mount',f'type=bind,source={work},target=/root/tools,readonly','--mount',f'type=bind,source={logs},target=/logs/verifier','--entrypoint','python3',a.image,'-B','/root/tools/worker.py','--mode',a.mode]
start=time.monotonic();r=subprocess.run(args,capture_output=True,timeout=1800)
(work/(a.label+'-stdout.txt')).write_bytes(r.stdout);(work/(a.label+'-stderr.txt')).write_bytes(r.stderr)
(work/(a.label+'-execution.json')).write_text(json.dumps(dict(command=args,exit_code=r.returncode,seconds=time.monotonic()-start),indent=2),encoding='utf-8',newline='\n')
print('EXIT',r.returncode)
if (logs/'receipt.json').exists():print((logs/'receipt.json').read_text())
if (logs/'eb032_math_k/result.json').exists():
    value=json.loads((logs/'eb032_math_k/result.json').read_bytes());print('FAILED_CHECKS',json.dumps([v for v in value['cases'] if not v['passed']],ensure_ascii=False))
else:print(r.stderr.decode(errors='replace')[-2000:])
raise SystemExit(r.returncode)
