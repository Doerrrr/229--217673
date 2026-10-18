"""Preserve reward semantics and expose bounded diagnostics on abnormal runs."""
import argparse
import json
from pathlib import Path


def diagnostic(result):
    issues = result.get('runtime_issues', [])
    rows = []
    fields = ('returncode', 'timed_out', 'elapsed_seconds', 'peak_rss_kib',
              'log_limit_exceeded', 'captured_bytes', 'capture_limit_bytes',
              'input_sha256', 'expected_kill', 'descendants_remaining')
    for issue in issues[:4]:
        if 'candidate_runtime' in issue:
            log = issue['candidate_runtime']
            row = {k: log[k] for k in fields if k in log}
            if log.get('log_limit_exceeded'):
                cause = 'diagnostic_output_limit_exceeded'
            elif log.get('timed_out'):
                cause = 'candidate_call_timeout'
            elif isinstance(log.get('returncode'), int) and log['returncode'] < 0:
                cause = 'candidate_terminated_by_signal'
                row['signal_number'] = -log['returncode']
            else:
                cause = 'candidate_runtime_error'
            command = log.get('command', [])
            if '--input' in command:
                pos = command.index('--input') + 1
                if pos < len(command):
                    row['input_name'] = str(command[pos]).replace('\\', '/').rsplit('/', 1)[-1][:120]
            row['cause'] = cause
            if log.get('stderr_tail'):
                row['stderr_tail'] = str(log['stderr_tail'])[-512:]
        elif 'launch_failure' in issue:
            row = {'cause': 'candidate_launch_failure', 'returncode': issue['launch_failure']}
        else:
            row = {'cause': 'measurement_or_other_error',
                   'error': str(issue.get('error', 'unclassified issue'))[:400]}
        rows.append(row)
    skipped = [c.get('name') for c in result.get('cases', [])
               if c.get('evidence') == 'not run after runtime failure']
    return {'error': 'EB032_ABNORMAL_EXECUTION',
            'execution_status': result.get('execution_status'), 'reward': None,
            'runtime_issue_count': len(issues), 'runtime_issues': rows,
            'not_run_check_count': len(skipped), 'first_not_run_checks': skipped[:4]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--result', type=Path, required=True)
    parser.add_argument('--reward', type=Path, required=True)
    args = parser.parse_args()
    result = json.loads(args.result.read_bytes())
    # This is exactly the original acceptance condition. Abnormal executions
    # never become a score, and partially earned groups are never added up.
    if result['execution_status'] == 'NORMAL' and result['reward'] is not None:
        args.reward.write_text(str(result['reward']) + '\n')
        return
    detail = diagnostic(result)
    print('EB032_DIAGNOSTIC ' + json.dumps(detail, ensure_ascii=True, separators=(',', ':')), flush=True)
    causes = ','.join(row['cause'] for row in detail['runtime_issues']) or 'details_unavailable'
    raise RuntimeError('EB032 abnormal execution; reward withheld; causes=' + causes)


if __name__ == '__main__':
    main()
