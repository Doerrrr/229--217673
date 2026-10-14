"""Existing viewer reads observation semantics, not JSON key order or layout."""
import argparse
import json
import subprocess


def consume(binary,manifest,samples):
    previous=None;count=0
    process=subprocess.Popen([binary,'--manifest',manifest,'--samples',','.join(samples)],stdout=subprocess.PIPE)
    try:
        for line in process.stdout:
            row=json.loads(line)
            key=(row['chrom'],row['position'],row['reference'])
            assert previous is None or previous<key
            previous=key
            assert isinstance(row['alternate'],list) and isinstance(row['contributors'],list)
            assert [s['name'] for s in row['samples']]==samples
            for sample in row['samples']:
                observations=([sample['winner']] if sample['winner'] is not None else [])+sample['others']
                for observation in observations:
                    assert {'source','ordinal','format','values'}<=observation.keys()
                    assert set(observation['format'])==set(observation['values'])
            count+=1
    finally:
        process.stdout.close()
        status=process.wait()
    if status:raise RuntimeError('source release did not complete: exit '+str(status))
    return count


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--binary',required=True)
    parser.add_argument('--manifest',required=True);parser.add_argument('--samples',required=True)
    args=parser.parse_args();print(consume(args.binary,args.manifest,args.samples.split(',')))
