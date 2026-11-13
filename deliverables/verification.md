# Verification evidence and operating limits

## Scope and configuration

**Mode: authored mock artifacts plus saved-fixture replay; live provider: none; model ID: not applicable.** The application currently implements a mock replay provider only. The two Step 2 export-reader tests are committed before their implementation. This document distinguishes artifact checks from application tests and model observations. API_KEY is unset for the commands below; no live request or credential is needed.

extractions.jsonl contains exactly the 20 supplied documents. queue.json is a JSON array with exactly one linked entry per document, including source_sha256 so the same source revision can be checked. All records have response_source=mock and error=null because these are successful authored examples, including examples that need human clarification. The paraphrase lives in accuracy.md and is demonstrated using the existing saved mock fixture; it is not a 21st current queue entry.

The outer artifact representation and exact-source-purpose convention are choices for these examples, not newly implemented intake rules. The source/policy oracle in accuracy.md preceded the mock outputs. These examples are intentionally constructed to agree with that oracle; a perfect consistency count does not measure model extraction ability. request-evidence.json records one actual MockProvider.extract invocation and documents only implemented replay handling. It explicitly identifies the missing real-provider request/model configuration and handling.

## Commands and intended comparisons

Run from the repository root with Python 3.12. No third-party packages are needed for these artifact checks.

### 1. Current application test suite

```bash
env -u API_KEY python3 -m unittest discover -s tests -v
```

Expected comparison: each committed test's literal expectations against the code currently present. A successful full build would exit 0; the current observation is a failing test-first checkpoint, not a passing build. The historic planning/test-run.txt predates Step 1 implementation and is left unchanged.

### 2. Artifact integrity, scalar comparison and synthetic mock replay

```bash
env -u API_KEY python3 - <<'PY'
from collections import Counter
import hashlib
import json
from pathlib import Path

from access_requests.mock_provider import MockProvider, ScriptedResponse

root = Path.cwd()
accuracy = (root / 'deliverables/accuracy.md').read_text(encoding='utf-8')
expected = json.loads(accuracy.split('```json\n', 1)[1].split('\n```', 1)[0])
oracle = {item['document_id']: item for item in expected}
assert len(expected) == len(oracle) == 21
records = [json.loads(line) for line in (root / 'deliverables/extractions.jsonl').read_text(encoding='utf-8').splitlines()]
current = {item['document_id']: item for item in records}
sources = {p.name: p for p in (root / 'materials/requests').glob('*.json')}
assert len(records) == len(current) == len(sources) == 20
assert set(current) == set(sources)
assert set(oracle) == set(sources) | {'synthetic-001.json'}
queue = json.loads((root / 'deliverables/queue.json').read_text(encoding='utf-8'))
queued = {item['document_id']: item for item in queue}
assert len(queue) == len(queued) == 20 and set(queued) == set(current)
schema = json.loads((root / 'snapshot.schema.json').read_text())

# Check every constraint used by this supplied schema. This is a scoped
# artifact check, not a general JSON Schema implementation or application code.
def validate(value, rule):
    types = rule['type']
    types = [types] if isinstance(types, str) else types
    valid_type = any(
        (t == 'object' and isinstance(value, dict)) or
        (t == 'array' and isinstance(value, list)) or
        (t == 'string' and isinstance(value, str)) or
        (t == 'null' and value is None)
        for t in types
    )
    assert valid_type, ('type', value, types)
    if 'enum' in rule:
        assert value in rule['enum'], ('enum', value)
    if isinstance(value, dict):
        assert set(rule.get('required', [])) <= set(value)
        properties = rule.get('properties', {})
        if rule.get('additionalProperties') is False:
            assert set(value) <= set(properties)
        for key, item in value.items():
            if key in properties:
                validate(item, properties[key])
    if isinstance(value, list) and 'items' in rule:
        for item in value:
            validate(item, rule['items'])

scalar_fields = [key for key in schema['properties'] if key not in ('supporting_quotes', 'issues')]
assert len(scalar_fields) == 12
scalar_matches = 0
route_matches = 0
errors = []
for name, source in sorted(sources.items()):
    record = current[name]
    want = oracle[name]
    raw = source.read_bytes()
    message = json.loads(raw.decode('utf-8'))['message']
    assert record['source_sha256'] == hashlib.sha256(raw).hexdigest(), name
    assert record['response_source'] == 'mock' and record['error'] is None
    assert {'document_id', 'source_sha256', 'extraction', 'status', 'owner', 'next_action', 'error', 'response_source'} <= set(record)
    validate(record['extraction'], schema)
    assert want['extraction']['business_purpose'] in message, name
    assert record['extraction']['supporting_quotes']
    assert all(quote in message for quote in record['extraction']['supporting_quotes']), name
    for field in scalar_fields:
        if record['extraction'].get(field) == want['extraction'][field]:
            scalar_matches += 1
        else:
            errors.append({'document_id': name, 'field': field, 'expected': want['extraction'][field], 'observed': record['extraction'].get(field), 'source': str(source)})
        if record['extraction'][field] is None:
            assert any(field in issue for issue in record['extraction']['issues']), (name, field)
    for field in ('status', 'owner', 'next_action'):
        if record[field] == want[field]:
            route_matches += 1
        else:
            errors.append({'document_id': name, 'field': field, 'expected': want[field], 'observed': record[field], 'source': str(source)})
    for field in ('source_sha256', 'status', 'owner', 'next_action', 'error', 'response_source'):
        assert queued[name][field] == record[field], (name, field)
    assert queued[name]['request_id'] == record['extraction']['request_id']
    assert queued[name]['issues'] == record['extraction']['issues']

# Important source/policy cases have independent explicit assertions.
assert current['IT-003.json']['extraction']['start_date'] is None
assert current['IT-003.json']['extraction']['end_date'] is None
assert current['IT-004.json']['extraction']['environment'] is None
assert any('staging' in q for q in current['IT-004.json']['extraction']['supporting_quotes'])
assert any('production' in q for q in current['IT-004.json']['extraction']['supporting_quotes'])
assert current['IT-006.json']['next_action'] == 'inspect-message'
assert any('SYSTEM OVERRIDE:' in q for q in current['IT-006.json']['extraction']['supporting_quotes'])
assert any('override' in issue.lower() for issue in current['IT-006.json']['extraction']['issues'])
assert current['IT-007.json']['extraction']['permission'] == 'write'
assert current['IT-008.json']['extraction']['environment'] == 'staging'
assert current['IT-009.json']['extraction']['manager'] is None
assert current['IT-010.json']['extraction']['end_date'] is None
assert current['IT-011.json']['extraction']['start_date'] is None
assert current['IT-011.json']['extraction']['end_date'] is None
assert current['IT-014.json']['extraction']['start_date'] > current['IT-014.json']['extraction']['end_date']
assert any('Date order' in issue for issue in current['IT-014.json']['extraction']['issues'])
assert current['IT-015.json']['extraction']['start_date'] == '2026-10-29'
assert current['IT-015.json']['extraction']['end_date'] == '2026-10-31'
assert current['IT-016.json']['extraction']['request_id'] == 'IT-061'
assert current['IT-019.json']['extraction']['permission'] == 'read'
assert current['IT-020.json']['extraction']['manager'] is None
assert any('Priya Shah' in q for q in current['IT-020.json']['extraction']['supporting_quotes'])
assert any('Elena Park' in q for q in current['IT-020.json']['extraction']['supporting_quotes'])
assert all(record['status'] in ('review', 'needs-information') for record in records)

synthetic = oracle['synthetic-001.json']
provider = MockProvider([ScriptedResponse(root / 'tests/mock_responses/paraphrase.complete.json')])
reply = provider.extract(synthetic['source_message'])
validate(reply['extraction'], schema)
assert reply['response_source'] == 'mock' and len(provider.calls) == 1
assert all(quote in synthetic['source_message'] for quote in reply['extraction']['supporting_quotes'])
synthetic_matches = 0
for field in scalar_fields:
    if reply['extraction'].get(field) == synthetic['extraction'][field]:
        synthetic_matches += 1
    else:
        errors.append({'document_id': 'synthetic-001.json', 'field': field, 'expected': synthetic['extraction'][field], 'observed': reply['extraction'].get(field), 'source': 'accuracy.md embedded paraphrase'})

evidence = json.loads((root / 'deliverables/request-evidence.json').read_text())
assert evidence['mode'] == 'mock' and evidence['model_id'] is None
assert evidence['observed_call_count'] == 1
assert evidence['request']['arguments']['message'] == json.loads(sources['IT-001.json'].read_text())['message']
assert evidence['request']['source_sha256'] == current['IT-001.json']['source_sha256']
for kind in ('fixture', 'schema', 'policy'):
    path_key = 'fixture' if kind == 'fixture' else kind + '_file'
    path = root / evidence['configuration'][path_key]
    assert evidence['configuration'][kind + '_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()

result = {
    'mode': 'mock; artifact consistency only; no live model',
    'supplied_records': len(records),
    'queue_entries': len(queue),
    'source_hashes_and_schema': 'passed',
    'exact_source_quotes_and_required_issues': 'passed',
    'supplied_scalar_matches': scalar_matches,
    'supplied_scalar_denominator': 240,
    'synthetic_scalar_matches': synthetic_matches,
    'synthetic_scalar_denominator': 12,
    'combined_scalar_matches': scalar_matches + synthetic_matches,
    'combined_scalar_denominator': 252,
    'authored_route_matches': route_matches,
    'authored_route_denominator': 60,
    'queue_status_counts': dict(Counter(r['status'] for r in records)),
    'queue_owner_counts': dict(Counter(r['owner'] for r in records)),
    'mismatches': errors,
}
print(json.dumps(result, indent=2))
assert not errors, errors
assert scalar_matches == 240 and synthetic_matches == 12 and route_matches == 60
PY
```

Assertions: one current record per supplied filename; original-byte hashes; all constraints used by snapshot.schema.json; exact quotes as decoded-message substrings; required null-field issues; critical correction/conflict/date/mismatch/override cases; matching queue record hashes/routes; mock origin and actual request-evidence fixture/schema/policy hashes. The source file and policy words supporting the expected values are in accuracy.md. Scalar denominator is 240 for supplied examples plus 12 for the synthetic mock replay; routing denominator is 60 for authored supplied examples only. Nonmatches are printed with document/field/expected/observed/source and make the command fail. Integrity assertions fail rather than silently exclude malformed, missing or duplicate records. This verifier's all-present artifact success is not evidence for implemented failed-extraction scoring.

### 3. Inspect the queue

```bash
python3 -m json.tool deliverables/queue.json
```

Inspect document_id, request_id, source_sha256, status, owner, next_action and issues. None is approved. A named manager is a contact. Security Review's next action describes human risk review and recommendation to the system owner; no automated decision or actual handoff is implemented here.

### 4. Recreate the two authored mock output files

This command regenerates the same successful example records and queue from the documented oracle and current original-byte hashes. It is a mock artifact-generation command, not a model intake command or the application CLI. It does not create accuracy expectations from measured outputs.

```bash
env -u API_KEY python3 - <<'PY'
from pathlib import Path
import hashlib
import json
text = Path('deliverables/accuracy.md').read_text(encoding='utf-8')
expected = json.loads(text.split('```json\n', 1)[1].split('\n```', 1)[0])
records = []
for item in expected:
    if item['source_file'] is None:
        continue
    raw = Path(item['source_file']).read_bytes()
    records.append({
        'document_id': item['document_id'],
        'source_sha256': hashlib.sha256(raw).hexdigest(),
        'extraction': item['extraction'],
        'status': item['status'], 'owner': item['owner'],
        'next_action': item['next_action'],
        'error': None, 'response_source': 'mock',
    })
Path('deliverables/extractions.jsonl').write_text(
    ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records),
    encoding='utf-8',
)
queue = [
    {k: r[k] for k in ('document_id', 'source_sha256', 'status', 'owner',
                       'next_action', 'error', 'response_source')}
    | {'request_id': r['extraction']['request_id'], 'issues': r['extraction']['issues']}
    for r in records
]
Path('deliverables/queue.json').write_text(
    json.dumps(queue, ensure_ascii=False, indent=2) + '\n', encoding='utf-8',
)
print(f'Regenerated {len(records)} authored mock records and queue entries.')
PY
```

If the source messages change, do not treat this generator as an extractor: review and revise the source-grounded oracle before rebuilding examples. Hash recalculation alone cannot make old expected facts describe new content. The regeneration command intentionally does not refresh request-evidence provenance; rerun its actual mock invocation and capture evidence if sources/configuration change.

## Observed results

Observed against the working tree based on commit `409552c`, with these new deliverable files added. Configuration: Python 3.12, authored mock artifacts and saved-fixture replay; no provider/model, no API_KEY and no live-model observations.

| Command/check | Observed result | Meaning |
| --- | --- | --- |
| Command 1: full verbose unittest suite | Exit 1; 9 tests run, 7 passed, 2 failed. | All four T-01 checks and three starter checks pass. T-02 and T-03 fail with `access_requests.exports is not implemented`. This is the existing Step 2 test-first checkpoint; it was not repaired or hidden by artifact generation. |
| Command 2: artifact verifier | Exit 0; 20 supplied records and 20 linked queue entries. | Original-byte hashes, the supplied schema's constraints, exact source quotes, required null-field issues, critical policy examples and request-evidence hashes passed. |
| Command 2: scalar comparison | 240/240 supplied scalar matches; 12/12 synthetic saved-reply matches; 252/252 combined; no mismatches. | Authored-example and replay consistency only; no live-model accuracy was measured. |
| Command 2: route comparison | 60/60 authored route matches. | Agrees with the source-authored expected routes; does not establish application router correctness. |
| Queue distribution | 11 review; 9 needs-information. Owners: 4 System Owner, 5 Security Review, 11 IT Service Desk. | All 20 entries await human review or clarification. |
| Command 4: mock regeneration | Exit 0; both output files reproduced byte for byte, checked with SHA-256 before and after. | The authored mock examples are reproducible from the frozen oracle and unchanged source files. |

The source/profile conventions and all comparison denominators are documented in accuracy.md. No application code or tests were changed to produce these results.

## Operating assumptions, limits and remaining work

- These are a one-time, offline sample of 20 independent documents, not a running intake service. A synthetic message in the same export shape is documented separately. No throughput, latency, morning-intake or 200–400/day / approximately 2,000-message burst capability has been established.
- There is no supported shared/multi-host intake store, durable queue, locking across operators, current/history transaction or ordering rule for concurrent revisions. Repeated example generation overwrites the current examples and is not the required unchanged-rerun/revision/history implementation. The mock provider's in-memory lock is only for script assignment.
- MockProvider supports saved completion/refusal/cut-off replies, scripted error exceptions and caller-controlled delay events. It does not validate completion or schema, extract new facts, route requests, refresh settings, persist unfinished work or redact operational provider logs. The artifact verifier validates examples; it is not an application response handler.
- No real-provider API integration, extraction prompt, actual supported model configuration, application CLI, dependency lockfile, durable retry/resume, failed-retry history or recovery has been implemented. The request-evidence model_id is null for that reason; no real model identity, sampling settings or HTTP request is invented.
- The planned failure/refusal/interruption/unchanged-rerun/changed-source/concurrency cases are not all implemented. Existing failure fixtures are examples for the mock contract, not proof of application error handling. Actual latest suite results are recorded above without claiming missing cases passed.
- Scalar, route and evidence checks on authored examples do not establish live-model accuracy, generalization to fresh wording, resistance to arbitrary instruction attacks or real-provider compatibility. The synthetic observation is saved-fixture replay only. The oracle uses exact-source-purpose wording for reproducibility; a later live evaluation must explicitly apply or revise and freeze its comparison conventions before measuring results.
- No history is purged, no credentials are loaded and no approvals or messages to reviewers are sent by generation. A final application submission and its paired facilitator capture remain separate work. This document and these files do not revise the historical planning/validation.md assessment or create a new submission commit.
- Generation repairs: the temporary generation script's local import path and the document-writing heredoc delimiter were corrected before final verification. These were tooling repairs, not provider-response repairs or measured extraction corrections. No application implementation was changed.
