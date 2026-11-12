"""Real fac CLI + real model-selection/validation; only SDK client is fake."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
try:
    import jsonschema
except ImportError:
    sys.exit('Missing jsonschema; run bash setup.sh or set DIAG_PYTHON. No case executed.')
from harness import Audit, events, read, save, states

HERE = Path(__file__).resolve().parent
audit = Audit(HERE)
observed, checks = {}, {}
for mode, fixture, halt in [('schema_file', 'invalid.json', False),
                           ('schema_file', 'valid.json', False),
                           ('inline', 'invalid.json', False),
                           ('inline', 'valid.json', False),
                           ('schema_file', 'invalid.json', True)]:
    name = mode + '-' + fixture[:-5] + ('-halt-option' if halt else '')
    work = audit.workspace(name, HERE / 'fixtures')
    if mode == 'inline':
        config = (work / 'fac.yaml').read_text().replace('  schema_file: schema.json',
            '  schema: |\n' + '\n'.join('    ' + line for line in (work / 'schema.json').read_text().splitlines()))
        (work / 'fac.yaml').write_text(config)
    result = audit.fac(work, response=fixture, targets=('consumed.json',),
                       flags=('--debug.halt_on_error',) if halt else ())
    validation = {}
    for filename in (fixture, 'record.json', 'consumed.json'):
        path = work / filename
        entry = {'exists': path.exists()}
        if path.exists():
            # Actual json.loads and an independently raising validator, not
            # fac's warn-only helper. Syntax validity and schema validity differ.
            instance = read(path)
            entry.update(json_syntax_valid=True, instance=instance)
            try:
                jsonschema.Draft7Validator(read(work / 'schema.json')).validate(instance)
                entry.update(json_schema_valid=True, error=None)
            except jsonschema.ValidationError as error:
                entry.update(json_schema_valid=False, error=error.message)
        validation[filename] = entry
    save(work.parent / 'independent-validation.json', validation)
    invocations = [__import__('json').loads(line) for line in (work / '.fake-invocations.jsonl').read_text().splitlines()]
    observed[name] = {
        'fac_process_returncode': result.returncode, 'fac_states': states(result),
        'schema_warning': b'JSON schema validation error' in result.stderr,
        'validation': validation, 'built_events': [e['path'] for e in events(work)],
        'sdk_invocation_count': len(invocations), 'response_source': 'DETERMINISTIC FAKE SDK CLIENT',
        'per_target_metadata_exists': (work / '.record.json.facjson').exists(),
    }
    audit.snapshot(work, 'after-fac')
    item = observed[name]
    checks[name + '_CLI_and_downstream_accept'] = (result.returncode == 0 and
        sorted(item['fac_states']['built']) == ['consumed.json', 'record.json'] and
        len(invocations) == 1 and item['per_target_metadata_exists'])
    checks[name + '_independent_validation'] = (validation['record.json']['json_schema_valid'] ==
        validation['consumed.json']['json_schema_valid'] == (fixture == 'valid.json'))
    checks[name + '_warning_distinguishes_inline_from_file'] = item['schema_warning'] == (mode == 'schema_file' and fixture == 'invalid.json')
sys.exit(audit.finish(observed, checks))

