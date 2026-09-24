"""ClearJev router tests — stdlib unittest, no network, no API key needed."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(os.path.dirname(__file__), "..",
                    "plugins", "clearjev-router", "scripts", "jev_route.py")
HOOK = os.path.normpath(HOOK)


def run_hook(payload, env_extra=None):
    env = dict(os.environ)
    env.pop("TYPESAFE_API_KEY", None)
    env.pop("JEV_API_KEY", None)
    # Hermetic on/off state: never touch the real ~/.codex or $PLUGIN_DATA.
    tmp = tempfile.mkdtemp(prefix="clearjev-test-")
    env["CLEARJEV_STATE"] = os.path.join(tmp, "state.json")
    env.pop("CLEARJEV_ENABLED", None)
    env.pop("PLUGIN_DATA", None)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, HOOK], input=json.dumps(payload),
        capture_output=True, text=True, timeout=30, cwd="/tmp", env=env)
    return proc


def run_cli(*args, env_extra=None):
    env = dict(os.environ)
    env.pop("TYPESAFE_API_KEY", None)
    env.pop("JEV_API_KEY", None)
    tmp = tempfile.mkdtemp(prefix="clearjev-test-")
    env["CLEARJEV_STATE"] = os.path.join(tmp, "state.json")
    env.pop("CLEARJEV_ENABLED", None)
    env.pop("PLUGIN_DATA", None)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, HOOK, *args],
        capture_output=True, text=True, timeout=30, cwd="/tmp", env=env)
    return proc, env["CLEARJEV_STATE"]


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


class TestOnOff(unittest.TestCase):
    """Kill-switch: --on/--off/--status, env override, noroute: prefix."""

    def test_off_silences_hook(self):
        proc, state = run_cli("--off")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("OFF", proc.stdout)
        hooked = run_hook({"prompt": "Implement a full auth system.", "cwd": "/tmp"},
                          {"CLEARJEV_STATE": state})
        self.assertEqual(hooked.returncode, 0)
        self.assertEqual(hooked.stdout, "")

    def test_on_restores_hook(self):
        proc, state = run_cli("--off")
        proc, _ = run_cli("--on", env_extra={"CLEARJEV_STATE": state})
        self.assertEqual(proc.returncode, 0)
        self.assertIn("ON", proc.stdout)
        hooked = run_hook({"prompt": "Implement a full auth system.", "cwd": "/tmp"},
                          {"CLEARJEV_STATE": state})
        self.assertIn("additionalContext", hooked.stdout)

    def test_env_zero_overrides_on_file(self):
        _, state = run_cli("--on")
        hooked = run_hook({"prompt": "Implement a full auth system.", "cwd": "/tmp"},
                          {"CLEARJEV_STATE": state, "CLEARJEV_ENABLED": "0"})
        self.assertEqual(hooked.returncode, 0)
        self.assertEqual(hooked.stdout, "")

    def test_env_one_overrides_off_file(self):
        _, state = run_cli("--off")
        hooked = run_hook({"prompt": "Implement a full auth system.", "cwd": "/tmp"},
                          {"CLEARJEV_STATE": state, "CLEARJEV_ENABLED": "1"})
        self.assertIn("additionalContext", hooked.stdout)

    def test_noroute_prefix_skips_once(self):
        hooked = run_hook({"prompt": "noroute: just do it, no questions.", "cwd": "/tmp"})
        self.assertEqual(hooked.returncode, 0)
        self.assertEqual(hooked.stdout, "")

    def test_status_reports(self):
        proc, _ = run_cli("--status")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("routing: ON", proc.stdout)


if __name__ == "__main__":
    unittest.main()
