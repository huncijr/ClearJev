"""ClearJev router tests — stdlib unittest, no network, no API key needed."""
import json
import os
import subprocess
import sys
import unittest

HOOK = os.path.join(os.path.dirname(__file__), "..",
                    "plugins", "clearjev-router", "scripts", "jev_route.py")
HOOK = os.path.normpath(HOOK)


def run_hook(payload, env_extra=None):
    env = dict(os.environ)
    env.pop("TYPESAFE_API_KEY", None)
    env.pop("JEV_API_KEY", None)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, HOOK], input=json.dumps(payload),
        capture_output=True, text=True, timeout=30, cwd="/tmp", env=env)
    return proc


def decision(payload):
    proc = run_hook(payload)
    assert proc.returncode == 0, proc.stderr
    outer = json.loads(proc.stdout)
    return outer["hookSpecificOutput"]["additionalContext"]


class TestContract(unittest.TestCase):
    def test_output_shape(self):
        proc = run_hook({"prompt": "Fix this typo.", "cwd": "/tmp"})
        self.assertEqual(proc.returncode, 0)
        outer = json.loads(proc.stdout)
        self.assertEqual(outer["hookSpecificOutput"]["hookEventName"],
                         "UserPromptSubmit")
        ctx = outer["hookSpecificOutput"]["additionalContext"]
        for token in ("Model:", "Reasoning:", "Planning:", "Validation:"):
            self.assertIn(token, ctx)

    def test_fail_open_empty_prompt(self):
        proc = run_hook({"prompt": "", "cwd": "/tmp"})
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "")

    def test_fail_open_garbage_stdin(self):
        proc = subprocess.run(
            [sys.executable, HOOK], input="not json {{{",
            capture_output=True, text=True, timeout=30, cwd="/tmp")
        self.assertEqual(proc.returncode, 0)

    def test_no_block_without_key(self):
        proc = run_hook({"prompt": "rm -rf /", "cwd": "/tmp"})
        self.assertEqual(proc.returncode, 0)
        self.assertNotIn("decision", proc.stdout)
        self.assertIn("heuristic fallback", proc.stdout)


class TestSpecExamples(unittest.TestCase):
    """The five canonical examples from the spec (fallback path)."""

    def test_explanation_uses_luna(self):
        ctx = decision({"prompt": "Explain dependency injection in TypeScript.",
                        "cwd": "/tmp"})
        self.assertIn("explain", ctx)
        self.assertIn("gpt-6-luna", ctx)

    def test_small_task_uses_fast_model(self):
        ctx = decision({"prompt": "Add a dark mode toggle to the settings page.",
                        "cwd": "/tmp"})
        self.assertIn("gpt-6-luna", ctx)
        self.assertIn("Planning: light", ctx)

    def test_complex_feature_uses_sol(self):
        ctx = decision({"prompt": "Implement Stripe subscriptions with monthly/yearly plans, "
                                  "webhooks, subscription state sync and access control.",
                        "cwd": "/tmp"})
        self.assertIn("gpt-6-sol", ctx)
        self.assertIn("Reasoning: high", ctx)

    def test_architecture_uses_astra(self):
        ctx = decision({"prompt": "Redesign the backend to support 10x traffic "
                                  "without breaking customer data.",
                        "cwd": "/tmp"})
        self.assertIn("gpt-6-astra", ctx)

    def test_debugging_uses_sol(self):
        ctx = decision({"prompt": "Find why websocket connections randomly "
                                  "disconnect in production.",
                        "cwd": "/tmp"})
        self.assertIn("debug", ctx)
        self.assertIn("gpt-6-sol", ctx)


if __name__ == "__main__":
    unittest.main()
