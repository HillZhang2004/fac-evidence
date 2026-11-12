"""Keep the actual LLM.text_async path, replace only openai.AsyncOpenAI."""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from harness import Audit, ROOT, read, states

HERE = Path(__file__).resolve().parent
audit = Audit(HERE)
settings = {
    'nested': '  options:\n    model: groq/llama-3.1-8b-instant\n',
    'top-level-control': '  model: groq/llama-3.1-8b-instant\n',
    'conflicting': '  model: groq/llama-3.1-8b-instant\n  options:\n    model: openai/gpt-5-mini\n',
    'absent-control': '',
}
observed, checks = {}, {}
for name, config in settings.items():
    work = audit.workspace(name, HERE / 'fixtures')
    (work / 'fac.yaml').write_text('result.txt:\n  description: Return a fixed diagnostic message.\n' + config)
    parsed = audit.capture(work, 'parsed-config', [sys.executable, '-B', str(ROOT / 'lib' / 'inspect_config.py')])
    checks[name + '_config_parser_succeeds'] = parsed.returncode == 0
    result = audit.fac(work, response='response.txt')
    invocations = [json.loads(line) for line in (work / '.fake-invocations.jsonl').read_text().splitlines()]
    invocation = invocations[0]
    observed[name] = {'fac_process_returncode': result.returncode,
        'fac_states': states(result), 'parsed_config': json.loads(parsed.stdout),
        'sdk_model': invocation['model'], 'sdk_base_url': invocation['base_url'],
        'sdk_invocation_count': len(invocations), 'response_source': 'DETERMINISTIC FAKE SDK CLIENT'}
    checks[name + '_one_invocation_and_real_artifact'] = result.returncode == 0 and len(invocations) == 1 and (work / 'result.txt').exists()
    audit.snapshot(work, 'after-fac')
checks.update({
    'nested_model_retained_by_parser': observed['nested']['parsed_config']['result.txt']['options']['model'] == 'groq/llama-3.1-8b-instant',
    'nested_uses_same_default_as_absent': observed['nested']['sdk_model'] == observed['absent-control']['sdk_model'] == 'gpt-5.5',
    'nested_uses_openai_base_url': observed['nested']['sdk_base_url'] == 'https://api.openai.com/v1',
    'top_level_honored': observed['top-level-control']['sdk_model'] == 'llama-3.1-8b-instant'
        and observed['top-level-control']['sdk_base_url'] == 'https://api.groq.com/openai/v1',
    'top_level_wins_conflict': observed['conflicting']['sdk_model'] == 'llama-3.1-8b-instant',
})
sys.exit(audit.finish(observed, checks))

