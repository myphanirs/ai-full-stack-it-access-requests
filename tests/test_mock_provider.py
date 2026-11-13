"""T-01: saved replies, scripted errors and controlled delays, without a model.

Expected business facts come from planning/plan.md F-001 and the message in
materials/requests/IT-001.json. These tests exercise replay, not extraction or
routing. The fixture envelopes are a provider-independent mock contract.
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import importlib
import json
import os
from pathlib import Path
import socket
import threading
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
RESPONSES = ROOT / "tests" / "mock_responses"

# Independent of saved responses: F-001, supported by the message's exact words.
EXPECTED_EXTRACTION = {
    "request_id": "IT-001",
    "request_date": "2026-10-22",
    "kind": "new",
    "requester": "Maya Chen",
    "team": "Analytics",
    "system": "Atlas",
    "environment": "staging",
    "permission": "read",
    "business_purpose": (
        "I'm checking the weekly conversion dashboard with the new event "
        "definition changes (before next reporting cycle)."
    ),
    "start_date": "2026-10-23",
    "end_date": "2026-11-06",
    "manager": "Priya Shah",
    "supporting_quotes": [
        "Maya Chen from Analytics here, with request IT-001 dated 2026-10-22.",
        "new read access on Atlas in staging from 2026-10-23 to 2026-11-06",
        "My manager is Priya Shah.",
        "I'm checking the weekly conversion dashboard with the new event "
        "definition changes (before next reporting cycle).",
    ],
    "issues": [],
}


class MockProviderContract(unittest.TestCase):
    def setUp(self):
        guards = ExitStack()
        self.addCleanup(guards.close)

        # Fail on attempted credential lookup, without reading its value or
        # copying the process environment (which could itself read API_KEY).
        environment_type = type(os.environ)
        original_getitem = environment_type.__getitem__

        def guarded_getitem(environment, key):
            if key == "API_KEY":
                raise AssertionError("T-01 must not read API_KEY")
            return original_getitem(environment, key)

        guards.enter_context(
            mock.patch.object(environment_type, "__getitem__", guarded_getitem)
        )
        guards.enter_context(
            mock.patch.object(
                socket, "socket", side_effect=AssertionError("network is forbidden")
            )
        )
        guards.enter_context(
            mock.patch.object(
                socket,
                "create_connection",
                side_effect=AssertionError("network is forbidden"),
            )
        )
        self.message = json.loads(
            (ROOT / "materials" / "requests" / "IT-001.json").read_text(
                encoding="utf-8"
            )
        )["message"]

    def provider_types(self):
        # Import inside the guarded test: the initial failure should identify
        # the missing planned provider, rather than prevent test discovery.
        try:
            module = importlib.import_module("access_requests.mock_provider")
        except ModuleNotFoundError as error:
            if error.name in {"access_requests", "access_requests.mock_provider"}:
                self.fail("T-01: access_requests.mock_provider is not implemented")
            raise
        return module.MockProvider, module.ScriptedResponse, module.MockProviderError

    def assert_complete_reply(self, reply):
        self.assertEqual(reply["response_source"], "mock")
        self.assertEqual(reply["completion_status"], "completed")
        self.assertEqual(reply["extraction"], EXPECTED_EXTRACTION)
        for quote in EXPECTED_EXTRACTION["supporting_quotes"]:
            self.assertIn(quote, self.message)
        # No status/owner/next_action is manufactured by the replay provider.
        self.assertNotIn("status", reply)
        self.assertNotIn("owner", reply)
        self.assertNotIn("next_action", reply)

    def test_t01_replays_saved_completion_and_counts_calls(self):
        MockProvider, ScriptedResponse, _ = self.provider_types()
        provider = MockProvider(
            [
                ScriptedResponse(RESPONSES / "it-001.complete.json"),
                ScriptedResponse(RESPONSES / "it-001.complete.json"),
            ]
        )
        self.assert_complete_reply(provider.extract(self.message))
        self.assert_complete_reply(provider.extract(self.message))
        self.assertEqual(provider.calls, [self.message, self.message])

    def test_t01_saved_error_does_not_consume_the_next_completion(self):
        MockProvider, ScriptedResponse, MockProviderError = self.provider_types()
        provider = MockProvider(
            [
                ScriptedResponse(RESPONSES / "it-001.provider-error.json"),
                ScriptedResponse(RESPONSES / "it-001.complete.json"),
            ]
        )
        with self.assertRaisesRegex(MockProviderError, "Simulated provider unavailable"):
            provider.extract(self.message)
        self.assert_complete_reply(provider.extract(self.message))
        self.assertEqual(provider.calls, [self.message, self.message])

    def test_t01_replays_refusal_and_cutoff_without_inventing_facts(self):
        MockProvider, ScriptedResponse, _ = self.provider_types()
        provider = MockProvider(
            [
                ScriptedResponse(RESPONSES / "it-001.refusal.json"),
                ScriptedResponse(RESPONSES / "it-001.interrupted.json"),
            ]
        )
        refusal = provider.extract(self.message)
        self.assertEqual(refusal["response_source"], "mock")
        self.assertEqual(refusal["completion_status"], "refused")
        self.assertIsNone(refusal["extraction"])
        self.assertEqual(refusal["refusal"], "Simulated refusal")

        interrupted = provider.extract(self.message)
        self.assertEqual(interrupted["response_source"], "mock")
        self.assertEqual(interrupted["completion_status"], "interrupted")
        self.assertIsNone(interrupted["extraction"])
        self.assertEqual(interrupted["output_text"], '{"request_id":"IT-001"')
        self.assertEqual(provider.calls, [self.message, self.message])

    def test_t01_delay_waits_for_release_while_another_reply_is_available(self):
        MockProvider, ScriptedResponse, _ = self.provider_types()
        started = threading.Event()
        release = threading.Event()
        provider = MockProvider(
            [
                ScriptedResponse(
                    RESPONSES / "it-001.complete.json",
                    started=started,
                    release=release,
                ),
                ScriptedResponse(RESPONSES / "it-001.complete.json"),
            ]
        )
        with ThreadPoolExecutor(max_workers=2) as workers:
            delayed = workers.submit(provider.extract, self.message)
            try:
                # Timeouts are deadlock watchdogs, not a performance target.
                self.assertTrue(started.wait(timeout=2), "delayed call never started")
                self.assertFalse(delayed.done(), "reply returned before release")
                immediate = workers.submit(provider.extract, self.message)
                self.assert_complete_reply(immediate.result(timeout=2))
                self.assertFalse(delayed.done(), "second call released delayed reply")
            finally:
                release.set()
            self.assert_complete_reply(delayed.result(timeout=2))
        self.assertEqual(provider.calls, [self.message, self.message])


if __name__ == "__main__":
    unittest.main()
