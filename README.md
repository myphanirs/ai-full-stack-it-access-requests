# AI Full Stack Challenge — IT Access Requests

Northstar Labs prepares free-text access requests for human review. The task is defined in [CHALLENGE.md](CHALLENGE.md), the review rules in [office-policy.md](materials/office-policy.md), and the extraction format in [snapshot.schema.json](snapshot.schema.json).

The current repository provides a working mock-response replay provider and authored mock deliverables for the 20 supplied messages. It also documents expected facts for one paraphrased request. A complete intake application and live model integration are still being built. The commands below exercise the available mock workflow; they do not extract facts from new messages with a model.

## Setup and supported runtime

Use **Python 3.12**; verification was performed with Python 3.12.3. The current code and checks use only the Python standard library, so no package installation is required. A dependency lockfile has not yet been added. The shell commands below use a Unix-style shell and `env`.

Run every command from the repository root, the directory containing `CHALLENGE.md`:

```bash
python3 --version
```

The input exports are UTF-8 JSON files under `materials/requests/`. Their decoded `message` text supplies business facts; their original bytes supply the SHA-256 source hash. The input filename is the document identity, separate from any request ID inside the message.

## Supported provider and configuration

The implemented provider is **mock replay**: `access_requests.mock_provider.MockProvider`. It reads saved JSON responses under `tests/mock_responses/`, records calls, supports controlled delays and raises scripted provider errors. It returns saved refusal/interrupted markers unchanged. It does not itself validate responses, route requests or call a real model.

Mock configuration is supplied directly as a sequence of `ScriptedResponse` objects naming fixture paths; optional `started` and `release` events control delays. No provider endpoint, live model ID or sampling configuration is supported yet. [request-evidence.json](deliverables/request-evidence.json) records an actual mock invocation and identifies the missing live integration; its model ID is null because no model was invoked.

| Environment variable | Current use |
| --- | --- |
| `API_KEY` | Reserved by the challenge for the future live-provider integration. The mock provider and artifact commands do not read it. Leave it unset for tests and examples using `env -u API_KEY`. |

No other application environment variables are implemented. Do not place credentials in source files or deliverables.

## Mock intake and output generation

The following command recreates `deliverables/extractions.jsonl` and `deliverables/queue.json` for the **20 supplied messages**, using the source-authored expected facts in `deliverables/accuracy.md`. It overwrites those two example files. It preserves filename identity, calculates hashes from original bytes, and labels every record `response_source: mock`.

This is an authored-example generation command. An application intake CLI, automatic extraction of new messages, durable retry/resume and revision history are not implemented. If a message changes, review its expected facts before regenerating examples; the command rejects evidence quotes that no longer match the message.

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
        continue  # The authored paraphrase is evaluated separately.
    raw = Path(item['source_file']).read_bytes()
    message = json.loads(raw.decode('utf-8'))['message']
    assert all(q in message for q in item['extraction']['supporting_quotes']), item['document_id']
    records.append({
        'document_id': item['document_id'],
        'source_sha256': hashlib.sha256(raw).hexdigest(),
        'extraction': item['extraction'],
        'status': item['status'], 'owner': item['owner'],
        'next_action': item['next_action'],
        'error': None, 'response_source': 'mock',
    })
assert len(records) == len({r['document_id'] for r in records}) == 20
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
print(f'Generated {len(records)} authored mock records and queue entries.')
PY
```

Generating these examples does not exercise application routing or history and does not refresh the separately recorded request evidence.

## Run tests

```bash
env -u API_KEY python3 -m unittest discover -s tests
```

For individual test names and failure details:

```bash
env -u API_KEY python3 -m unittest discover -s tests -v
```

Current result: **9 tests run, 7 passed, 2 failed; exit code 1**. Step 1's mock-provider tests pass. T-02 and T-03 fail because `access_requests.exports` has not been implemented; they were committed at the test-first checkpoint. Tests use saved mock responses and block network access. No test requires a model key. See [the build plan](planning/plan.md) for the remaining steps.

## Run the accuracy and artifact checks

This exact command runs the verifier documented in [verification.md](deliverables/verification.md). It checks record uniqueness, source hashes, the supplied schema constraints, exact source quotes, null-field issues, queue links, critical policy examples and request-evidence hashes. It then compares the authored examples and synthetic saved reply against the documented expected facts.

```bash
env -u API_KEY python3 - <<'PY'
from pathlib import Path

text = Path('deliverables/verification.md').read_text(encoding='utf-8')
section = text.split('### 2. Artifact integrity, scalar comparison and synthetic mock replay', 1)[1]
code = section.split("python3 - <<'PY'\n", 1)[1].split('\nPY\n', 1)[0]
exec(compile(code, 'deliverables/verification.md:artifact-check', 'exec'))
PY
```

Current result: **exit code 0**, with 240/240 supplied-message scalar matches, 12/12 synthetic mock-replay scalar matches and 60/60 authored routing matches. These are consistency checks on authored examples seeded from the expected facts, not measured language-model accuracy. No live model observation has been made. [accuracy.md](deliverables/accuracy.md) defines expected values, exact-match denominators, null/error handling and factual-error reporting.

The full verifier is maintained in `verification.md`; the command above executes that local documented code, so changes to that section also change the check.

## Inspect the queue

Show every queue entry, including issues:

```bash
python3 -m json.tool deliverables/queue.json
```

For a compact view:

```bash
python3 - <<'PY'
from pathlib import Path
import json

queue = json.loads(Path('deliverables/queue.json').read_text(encoding='utf-8'))
print('Document\tRequest ID\tStatus\tOwner\tNext action')
for item in queue:
    print('\t'.join(str(item[key]) for key in (
        'document_id', 'request_id', 'status', 'owner', 'next_action'
    )))
PY
```

Link each entry to its extraction by `document_id` and verify the same `source_sha256`. `review` awaits the listed human reviewer; `needs-information` requires clarification through IT Service Desk. An `inspect-message` action flags an attempted instruction override. `review-risk-then-owner` describes Security Review followed by a system-owner decision. A named manager is a contact, and none of these entries approves access.

The authored queue contains 20 entries: 11 in review and 9 needing information. Owners are System Owner (4), Security Review (5) and IT Service Desk (11). The synthetic paraphrase is documented separately and is not an extra current queue entry.

## Deliverables and operating limits

| File | Content |
| --- | --- |
| [extractions.jsonl](deliverables/extractions.jsonl) | One current authored mock record per supplied message, including source hash, extraction, route, error and response origin. |
| [queue.json](deliverables/queue.json) | The linked current review queue. |
| [accuracy.md](deliverables/accuracy.md) | Source-derived expectations for 20 messages and a paraphrase, comparison rules and mock observations. |
| [request-evidence.json](deliverables/request-evidence.json) | Actual mock replay request/response evidence and implemented handling; live-provider evidence remains incomplete. |
| [verification.md](deliverables/verification.md) | Runnable checks, observed results, regeneration instructions and operating limits. |

There is no production workload or shared-operation claim: regional concurrency, durable attempts, source/configuration refresh, interrupted-run recovery and the full error/retry workflow remain planned work. Existing refusal, cut-off and error fixtures demonstrate replay behavior only. No intake/retry/resume command for the future application is presented as working here. The historical [validation report](planning/validation.md) and [test-run log](planning/test-run.txt) describe earlier repository states; use the commands above for current results.

Coding-session capture follows the facilitator's Entire setup. Final submission must pair its commit with the required capture and follow [CHALLENGE.md](CHALLENGE.md#submission); generating mock deliverables does not perform submission.
