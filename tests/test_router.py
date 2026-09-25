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


import atexit
import shutil

_TEST_TMPDIRS = []


def _register_tmp(tmp):
    _TEST_TMPDIRS.append(tmp)
    return tmp


@atexit.register
def _cleanup_test_tmp():
    for tmp in _TEST_TMPDIRS:
        shutil.rmtree(tmp, ignore_errors=True)


def hermetic_env(env_extra=None):
    env = dict(os.environ)
    env.pop("TYPESAFE_API_KEY", None)
    env.pop("JEV_API_KEY", None)
    env.pop("CLEARJEV_ENABLED", None)
    env.pop("PLUGIN_DATA", None)
    env.pop("CODEX_HOME", None)
    if env_extra:
        env.update(env_extra)
    # Hermetic on/off state: never touch the real ~/.codex or $PLUGIN_DATA.
    tmp = _register_tmp(tempfile.mkdtemp(prefix="clearjev-test-"))
    env.setdefault("CLEARJEV_STATE", os.path.join(tmp, "state.json"))
    # One stable config file: chained calls pass CLEARJEV_STATE back in.
    env.setdefault("CLEARJEV_CONFIG", env["CLEARJEV_STATE"])
    env.setdefault("CLEARJEV_CREDENTIALS",
                   os.path.join(tmp, "credentials.json"))
    # No model catalog in unit tests: fall back to shipped profiles only.
    env.setdefault("CLEARJEV_MODELS_CACHE",
                   os.path.join(tmp, "no-models.json"))
    return env


def run_hook(payload, env_extra=None):
    env = hermetic_env(env_extra)
    proc = subprocess.run(
        [sys.executable, HOOK], input=json.dumps(payload),
        capture_output=True, text=True, timeout=30, cwd="/tmp", env=env)
    return proc


def run_cli(*args, env_extra=None):
    env = hermetic_env(env_extra)
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
        for token in ("Recommended model:", "Current model:", "Reasoning:",
                      "Planning:", "Validation:"):
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
        self.assertIn("gpt-5.6-luna", ctx)

    def test_small_task_uses_fast_model(self):
        ctx = decision({"prompt": "Add a dark mode toggle to the settings page.",
                        "cwd": "/tmp"})
        self.assertTrue("gpt-5.6-luna" in ctx or "gpt-5.5" in ctx,
                        "small task should route to a cheap model: " + ctx)
        self.assertIn("Planning: light", ctx)

    def test_complex_feature_uses_sol(self):
        ctx = decision({"prompt": "Implement Stripe subscriptions with monthly/yearly plans, "
                                  "webhooks, subscription state sync and access control.",
                        "cwd": "/tmp"})
        self.assertIn("gpt-5.6-sol", ctx)
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
        self.assertIn("gpt-5.6-sol", ctx)


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

    def test_reroute_prefix_skips_hook(self):
        hooked = run_hook({"prompt": "reroute: this is actually a refactor.", "cwd": "/tmp"})
        self.assertEqual(hooked.returncode, 0)
        self.assertEqual(hooked.stdout, "")

    def test_status_reports(self):
        proc, _ = run_cli("--status")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("routing: ON", proc.stdout)

    def test_bare_and_dashed_commands_agree(self):
        bare, _ = run_cli("status")
        dashed, _ = run_cli("--status")
        self.assertEqual(bare.returncode, 0)
        norm = lambda text: "\n".join(
            line for line in text.splitlines()
            if not line.startswith("- state file:"))
        self.assertEqual(norm(bare.stdout), norm(dashed.stdout))


class TestKeyManagement(unittest.TestCase):
    def test_key_roundtrip(self):
        import tempfile as _tf
        tmp = _tf.mkdtemp(prefix="clearjev-key-")
        self.__class__._tmp = tmp
        creds = os.path.join(tmp, "credentials.json")
        base = {"CLEARJEV_CREDENTIALS": creds,
                "CLEARJEV_CONFIG": os.path.join(tmp, "config.json"),
                "CLEARJEV_STATE": os.path.join(tmp, "state.json"),
                "CLEARJEV_MODELS_CACHE": os.path.join(tmp, "no-models.json")}
        proc, _ = run_cli("key", "set", "secret-123", env_extra=base)
        self.assertEqual(proc.returncode, 0)
        self.assertNotIn("secret-123", proc.stdout)
        proc, _ = run_cli("key", "status", env_extra=base)
        self.assertIn("set", proc.stdout)
        data = json.load(open(creds))
        self.assertEqual(data["api_key"], "secret-123")
        self.assertEqual(oct(os.stat(creds).st_mode & 0o777), "0o600")
        proc, _ = run_cli("key", "unset", env_extra=base)
        self.assertEqual(proc.returncode, 0)
        self.assertFalse(os.path.exists(creds))

    def test_key_set_rejects_empty(self):
        proc, _ = run_cli("key", "set", "")
        self.assertNotEqual(proc.returncode, 0)


class TestModels(unittest.TestCase):
    def _catalog(self, models):
        import tempfile as _tf
        tmp = _tf.mkdtemp(prefix="clearjev-models-")
        path = os.path.join(tmp, "models.json")
        with open(path, "w") as f:
            json.dump({"models": [
                {"slug": slug, "visibility": "list",
                 "supported_reasoning_levels": [{"effort": e} for e in eff]}
                for slug, eff in models]}, f)
        config = os.path.join(tmp, "config.json")
        return {"CLEARJEV_MODELS_CACHE": path, "CLEARJEV_CONFIG": config,
                "CLEARJEV_STATE": config,
                "CLEARJEV_CREDENTIALS": os.path.join(tmp, "creds.json")}

    def test_list_shows_shipped_profiles(self):
        proc, _ = run_cli("models", "list")
        self.assertEqual(proc.returncode, 0)
        for slug in ("gpt-6-astra", "gpt-5.6-sol", "gpt-5.6-terra",
                     "gpt-5.6-luna", "gpt-5.5"):
            self.assertIn(slug, proc.stdout)

    def test_catalog_filters_unavailable(self):
        base = self._catalog([("gpt-5.6-luna", ["low", "medium"])])
        proc, _ = run_cli("models", "list", env_extra=base)
        self.assertIn("gpt-5.6-luna: enabled", proc.stdout)
        self.assertIn("gpt-6-astra: unavailable", proc.stdout)

    def test_add_rejects_unknown_model(self):
        base = self._catalog([("gpt-5.6-luna", ["low", "medium"])])
        proc, _ = run_cli("models", "add", "gpt-9-mythic", env_extra=base)
        self.assertNotEqual(proc.returncode, 0)

    def test_add_rejects_unsupported_reasoning(self):
        base = self._catalog([("gpt-5.6-luna", ["low", "medium"])])
        proc, _ = run_cli("models", "add", "gpt-5.6-luna",
                          "--reasoning", "low,ultra", env_extra=base)
        self.assertNotEqual(proc.returncode, 0)

    def test_add_remove_reasoning_roundtrip(self):
        base = self._catalog([("gpt-5.6-luna", ["low", "medium", "high"])])
        proc, _ = run_cli("models", "add", "gpt-5.6-luna",
                          "--reasoning", "low,medium", env_extra=base)
        self.assertEqual(proc.returncode, 0)
        proc, _ = run_cli("models", "reasoning", "gpt-5.6-luna",
                          "add", "high", env_extra=base)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("low,medium,high", proc.stdout)
        proc, _ = run_cli("models", "reasoning", "gpt-5.6-luna",
                          "remove", "low,medium,high", env_extra=base)
        self.assertNotEqual(proc.returncode, 0)  # must keep >= 1 level
        proc, _ = run_cli("models", "remove", "gpt-5.6-luna",
                          env_extra=base)
        self.assertEqual(proc.returncode, 0)

    def test_routing_respects_removed_model(self):
        base = self._catalog([
            ("gpt-6-astra", ["low", "medium", "high", "xhigh", "max", "ultra"]),
            ("gpt-5.6-sol", ["low", "medium", "high", "xhigh", "max", "ultra"]),
            ("gpt-5.6-luna", ["low", "medium", "high", "xhigh", "max"])])
        run_cli("models", "remove", "gpt-5.6-luna", env_extra=base)
        run_cli("models", "remove", "gpt-5.6-sol", env_extra=base)
        proc = run_hook({"prompt": "Explain dependency injection.",
                         "cwd": "/tmp"}, base)
        outer = json.loads(proc.stdout)
        ctx = outer["hookSpecificOutput"]["additionalContext"]
        self.assertIn("gpt-6-astra", ctx)


class TestRunCommand(unittest.TestCase):
    def test_run_dry_run_selects_real_model(self):
        proc, _ = run_cli("run", "--dry-run",
                          "Implement Stripe subscriptions with webhooks.")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("gpt-5.6-sol", proc.stdout)
        self.assertIn("--model gpt-5.6-sol", proc.stdout)

    def test_run_requires_prompt(self):
        proc, _ = run_cli("run")
        self.assertNotEqual(proc.returncode, 0)


class TestPackaging(unittest.TestCase):
    ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..",
                                         "plugins", "clearjev-router"))

    def test_hooks_json_uses_command_windows(self):
        with open(os.path.join(self.ROOT, "hooks", "hooks.json")) as f:
            data = json.load(f)
        cmds = [h.get("commandWindows", "")
                for g in data["hooks"]["UserPromptSubmit"] for h in g["hooks"]]
        self.assertTrue(all(cmds))
        self.assertNotIn("command_windows", json.dumps(data))

    def test_skill_invocation_name(self):
        with open(os.path.join(self.ROOT, "skills", "clearjev",
                               "SKILL.md")) as f:
            text = f.read()
        self.assertIn("name: clearjev", text[:400])
        # No-action menu: mandatory numbered on/off menu at the top.
        self.assertIn("No-action menu (mandatory)", text)
        for item in ("1. on", "2. off", "3. status", "4. key",
                     "5. models", "6. run"):
            self.assertIn(item, text)
        # Picker trigger words in the description.
        self.assertIn("on/off/status", text.split("---")[1])

    def test_prompt_files_have_descriptions(self):
        proms = os.path.join(self.ROOT, "prompts")
        names = sorted(f for f in os.listdir(proms) if f.endswith(".md"))
        self.assertTrue({"clearjev.md", "clearjev-on.md", "clearjev-off.md",
                         "clearjev-add.md", "clearjev-remove.md",
                         "clearjev-key.md"} <= set(names))
        for name in names:
            with open(os.path.join(proms, name)) as f:
                self.assertIn("description:", f.read())

    def test_shim_resolves_bundled_or_installed_runtime(self):
        with open(os.path.join(self.ROOT, "scripts", "clearjev")) as f:
            text = f.read()
        self.assertIn("clearjev-runtime", text)

    def test_router_config_is_json_and_loaded(self):
        with open(os.path.join(self.ROOT, "assets",
                               "router-config.json")) as f:
            data = json.load(f)
        for slug in ("gpt-6-astra", "gpt-5.6-sol", "gpt-5.6-terra",
                     "gpt-5.6-luna", "gpt-5.5"):
            self.assertIn(slug, data["models"])
            self.assertTrue(data["models"][slug]["reasoning"])


if __name__ == "__main__":
    unittest.main()
