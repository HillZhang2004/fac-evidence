"""Execute the same shell directly and through the real fac CLI."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from harness import Audit, states

HERE = Path(__file__).resolve().parent
audit = Audit(HERE)
observed, checks = {}, {}
for name, script, flags in [('failure', 'fail.sh', ()),
                             ('success-control', 'succeed.sh', ()),
                             ('halt-option-control', 'fail.sh', ('--debug.halt_on_error',))]:
    work = audit.workspace(name, HERE / 'fixtures')
    (work / 'fac.yaml').write_text('result.txt:\n  cmd: bash ' + script + '\n')
    direct = audit.capture(work, 'direct-shell', ['bash', script])
    # Remove only the control's direct-shell artifact in this new workspace.
    # fac must demonstrate that it creates its own output from a clean start.
    if (work / 'result.txt').exists():
        (work / 'result.txt').unlink()
    result = audit.fac(work, flags=flags)
    snapshot = audit.snapshot(work, 'after-fac')
    observed[name] = {
        'direct_shell_returncode': direct.returncode,
        'fac_process_returncode': result.returncode,
        'artifact_exists': (work / 'result.txt').exists(),
        'per_target_metadata_exists': '.result.txt.facjson' in snapshot,
        'global_buildlog_exists': '.buildlog' in snapshot,
        'fac_states': states(result) if result.returncode == 0 else None,
        'stderr_reports_command_exit_7': b'exit code 7' in result.stderr,
    }
failure, success, halt = (observed[n] for n in observed)
checks.update({
    'shell_really_exits_7': failure['direct_shell_returncode'] == 7,
    'default_fac_exits_0': failure['fac_process_returncode'] == 0,
    'failure_recorded_in_states': failure['fac_states']['build_error'] == ['result.txt'],
    'no_failed_artifact_or_success_metadata': not any([failure['artifact_exists'],
        failure['per_target_metadata_exists'], failure['global_buildlog_exists']]),
    'fac_reports_actual_shell_exit_7': failure['stderr_reports_command_exit_7'],
    'control_shell_and_fac_succeed': success['direct_shell_returncode'] == success['fac_process_returncode'] == 0,
    'control_built_with_artifact_and_metadata': success['fac_states']['built'] == ['result.txt']
        and success['artifact_exists'] and success['per_target_metadata_exists'] and success['global_buildlog_exists'],
    'existing_debug_option_raises_nonzero': halt['fac_process_returncode'] != 0
        and not halt['artifact_exists'] and halt['stderr_reports_command_exit_7'],
})
sys.exit(audit.finish(observed, checks))

