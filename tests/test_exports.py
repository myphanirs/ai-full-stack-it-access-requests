"""T-02/T-03: source identity and the plan's supported-length fixture.

Expected facts are from planning/plan.md F-001 and P-001. These reader checks
replay saved replies; routing remains a later build step.
"""

from contextlib import ExitStack
import hashlib
import importlib
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest import mock

from access_requests.mock_provider import MockProvider, ScriptedResponse


ROOT = Path(__file__).resolve().parents[1]
RESPONSES = ROOT / "tests" / "mock_responses"
PARAPHRASE = (
    "Request IT-001, dated 2026-10-22. I'm Maya Chen on the Analytics team. "
    "Please create new read access to Atlas's staging environment for "
    "2026-10-23 through 2026-11-06. Priya Shah is my manager. I need to check "
    "the weekly conversion dashboard against the changed event definitions "
    "before the next reporting cycle."
)
# Literal source facts, independent of the saved mock replies.
EXPECTED_SCALARS = {
    "request_id": "IT-001",
    "request_date": "2026-10-22",
    "kind": "new",
    "requester": "Maya Chen",
    "team": "Analytics",
    "system": "Atlas",
    "environment": "staging",
    "permission": "read",
    "start_date": "2026-10-23",
    "end_date": "2026-11-06",
    "manager": "Priya Shah",
}


class ExportReaderContract(unittest.TestCase):
    def setUp(self):
        guards = ExitStack()
        self.addCleanup(guards.close)
        environment_type = type(os.environ)
        original_getitem = environment_type.__getitem__

        def guarded_getitem(environment, key):
            if key == "API_KEY":
                raise AssertionError("export tests must not read API_KEY")
            return original_getitem(environment, key)

        guards.enter_context(
            mock.patch.object(environment_type, "__getitem__", guarded_getitem)
        )
        for name in ("socket", "create_connection"):
            guards.enter_context(
                mock.patch.object(
                    socket, name, side_effect=AssertionError("network is forbidden")
                )
            )

    def export_reader(self):
        try:
            module = importlib.import_module("access_requests.exports")
        except ModuleNotFoundError as error:
            if error.name == "access_requests.exports":
                self.fail("T-02/T-03: access_requests.exports is not implemented")
            raise
        return module.load_export

    def assert_source_facts(self, reply):
        self.assertEqual(reply["response_source"], "mock")
        self.assertEqual(reply["completion_status"], "completed")
        for field, value in EXPECTED_SCALARS.items():
            self.assertEqual(reply["extraction"][field], value, field)

    def test_t02_original_bytes_filename_and_message_ignore_metadata(self):
        load_export = self.export_reader()
        source = ROOT / "materials" / "requests" / "IT-001.json"
        original_bytes = source.read_bytes()
        original_message = json.loads(original_bytes.decode("utf-8"))["message"]
        first = load_export(source)
        self.assertEqual(first.document_id, "IT-001.json")
        self.assertEqual(first.source_sha256, hashlib.sha256(original_bytes).hexdigest())
        self.assertEqual(first.message, original_message)

        changed_export = json.loads(original_bytes.decode("utf-8"))
        changed_export["subject"] = "IT-999 production admin for Nobody — metadata only"
        changed_export["exported_at"] = "2099-01-01T00:00:00Z"
        changed_bytes = json.dumps(
            changed_export, ensure_ascii=False, indent=4
        ).encode("utf-8") + b"\n"
        with tempfile.TemporaryDirectory() as directory:
            changed_path = Path(directory) / "IT-001.json"
            changed_path.write_bytes(changed_bytes)
            second = load_export(changed_path)

        self.assertEqual(second.document_id, "IT-001.json")
        self.assertEqual(second.source_sha256, hashlib.sha256(changed_bytes).hexdigest())
        self.assertNotEqual(second.source_sha256, first.source_sha256)
        self.assertEqual(second.message, original_message)

        provider = MockProvider(
            [ScriptedResponse(RESPONSES / "it-001.complete.json") for _ in range(2)]
        )
        for exported in (first, second):
            reply = provider.extract(exported.message)
            self.assert_source_facts(reply)
            self.assertEqual(
                reply["extraction"]["business_purpose"],
                "I'm checking the weekly conversion dashboard with the new event "
                "definition changes (before next reporting cycle).",
            )
        self.assertEqual(provider.calls, [original_message, original_message])

    def test_t03_preserves_the_complete_200_word_message(self):
        load_export = self.export_reader()
        words_to_add = 200 - len(PARAPHRASE.split())
        self.assertGreater(words_to_add, 0)
        message = PARAPHRASE + " Thanks." * words_to_add
        self.assertEqual(len(message.split()), 200)
        raw = json.dumps(
            {
                "export_version": "1.0",
                "exported_at": "2026-10-22T16:00:00Z",
                "source_channel": "email",
                "subject": "Authored P-001, padded to 200 words",
                "message": message,
            },
            indent=2,
        ).encode("utf-8") + b"\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic-001.json"
            path.write_bytes(raw)
            exported = load_export(path)

        self.assertEqual(exported.document_id, "synthetic-001.json")
        self.assertEqual(exported.source_sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(exported.message, message)
        provider = MockProvider(
            [ScriptedResponse(RESPONSES / "paraphrase.complete.json")]
        )
        reply = provider.extract(exported.message)
        self.assert_source_facts(reply)
        self.assertEqual(
            reply["extraction"]["business_purpose"],
            "I need to check the weekly conversion dashboard against the changed "
            "event definitions before the next reporting cycle.",
        )
        for quote in reply["extraction"]["supporting_quotes"]:
            self.assertIn(quote, message)
        self.assertEqual(provider.calls, [message])


if __name__ == "__main__":
    unittest.main()
