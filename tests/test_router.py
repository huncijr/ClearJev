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


class TestDynamicCatalog(unittest.TestCase):
    """The live catalog — not hardcoded slugs — defines routing candidates."""

    def _catalog(self, models):
        import tempfile as _tf
        tmp = _tf.mkdtemp(prefix="clearjev-dyncat-")
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

    def test_unknown_catalog_models_are_routable(self):
        base = self._catalog([
            ("gpt-9-mythic", ["low", "medium", "high"]),
            ("gpt-9-tiny", ["low", "medium"])])
        proc = run_hook({"prompt": "Explain dependency injection.",
                         "cwd": "/tmp"}, base)
        outer = json.loads(proc.stdout)
        ctx = outer["hookSpecificOutput"]["additionalContext"]
        self.assertTrue("gpt-9-mythic" in ctx or "gpt-9-tiny" in ctx,
                        "catalog models must be routable without profiles: " + ctx)

    def test_list_shows_unprofiled_catalog_models(self):
        base = self._catalog([("gpt-9-mythic", ["low", "medium", "high"])])
        proc, _ = run_cli("models", "list", env_extra=base)
        self.assertIn("gpt-9-mythic: enabled [low,medium,high]", proc.stdout)

    def test_add_unprofiled_catalog_model(self):
        base = self._catalog([("gpt-9-mythic", ["low", "medium"])])
        proc, _ = run_cli("models", "add", "gpt-9-mythic",
                          "--reasoning", "low", env_extra=base)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("gpt-9-mythic [low]", proc.stdout)

    def test_shipped_models_unavailable_in_catalog(self):
        base = self._catalog([("gpt-9-mythic", ["low", "medium", "high"])])
        proc = run_hook({"prompt": "Implement Stripe subscriptions with "
                                   "webhooks and access control.",
                         "cwd": "/tmp"}, base)
        outer = json.loads(proc.stdout)
        ctx = outer["hookSpecificOutput"]["additionalContext"]
        self.assertIn("gpt-9-mythic", ctx)
        self.assertNotIn("gpt-5.6-sol", ctx)


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


def load_router_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("jev_route_under_test", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def switch_decision(model="gpt-5.6-luna", current="gpt-5.6-sol"):
    return {"intent": "explain", "intent_conf": 1.0, "complexity": 15,
            "band": "trivial", "mean_conf": 1.0, "model": model,
            "reasoning": "low", "planning": "none", "repo": "unnecessary",
            "validation": "none", "uncertain": False,
            "reasons": ["explain task"], "source": "jev",
            "current_model": current}


class TestHostScope(unittest.TestCase):
    """ClearJev routes in Codex CLI only; App hosts stay silent (zero cost)."""

    def test_cli_by_default(self):
        # default env (no originator var) routes
        proc = run_hook({"prompt": "Explain dependency injection.", "cwd": "/tmp"},
                        {"CODEX_INTERNAL_ORIGINATOR_OVERRIDE": "",
                         "CLEARJEV_FORCE_HOST": ""})
        self.assertIn("additionalContext", proc.stdout)

    def test_app_host_stays_silent(self):
        proc = run_hook({"prompt": "Explain dependency injection.", "cwd": "/tmp"},
                        {"CODEX_INTERNAL_ORIGINATOR_OVERRIDE": "Codex Desktop"})
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "")

    def test_app_control_gets_cli_only_pointer(self):
        proc = run_hook({"prompt": "clearjev off", "cwd": "/tmp"},
                        {"CODEX_INTERNAL_ORIGINATOR_OVERRIDE": "Codex Desktop"})
        ctx = json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("CLI-only", ctx)
        self.assertNotIn("routing OFF", ctx)

    def test_force_host_override(self):
        proc = run_hook({"prompt": "Explain dependency injection.", "cwd": "/tmp"},
                        {"CODEX_INTERNAL_ORIGINATOR_OVERRIDE": "Codex Desktop",
                         "CLEARJEV_FORCE_HOST": "cli"})
        self.assertIn("additionalContext", proc.stdout)

    def test_status_shows_host(self):
        proc, _ = run_cli("status")
        self.assertIn("- host: CLI", proc.stdout)


class TestChatControl(unittest.TestCase):
    """Hook-side on/off/status: exact prompts only, no shell needed."""

    def test_exact_forms_execute(self):
        for text, word in (("clearjev off", "OFF"), ("clearjev on", "ON"),
                           ("  ClearJev Status ", "ClearJev status")):
            proc = run_hook({"prompt": text, "cwd": "/tmp"})
            self.assertEqual(proc.returncode, 0, text)
            outer = json.loads(proc.stdout)
            ctx = outer["hookSpecificOutput"]["additionalContext"]
            self.assertTrue(ctx.startswith("ClearJev control result"), text)
            self.assertIn(word, ctx)

    def test_mention_plus_action_executes(self):
        proc = run_hook(
            {"prompt": "[$clearjev](/x/SKILL.md) off", "cwd": "/tmp"})
        ctx = json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertTrue(ctx.startswith("ClearJev control result"))
        self.assertIn("OFF", ctx)

    def test_control_works_while_routing_off(self):
        proc, state = run_cli("off")
        hooked = run_hook({"prompt": "clearjev on", "cwd": "/tmp"},
                          {"CLEARJEV_STATE": state})
        ctx = json.loads(hooked.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("ClearJev routing ON", ctx)

    def test_near_matches_route_normally(self):
        for text in ("off", "status", "clearjev off please",
                     "what does clearjev off do?", "clearjev models list",
                     "please turn clearjev off", "[$clearjev](/x/SKILL.md) hello"):
            self.assertIsNone(
                _chat_control(text), "must not intercept: " + text)

    def test_off_still_silences_routing(self):
        proc, state = run_cli("off")
        hooked = run_hook({"prompt": "Implement a full auth system.", "cwd": "/tmp"},
                          {"CLEARJEV_STATE": state})
        self.assertEqual(hooked.stdout, "")


def _chat_control(text):
    # Hermetic: never touch the real ~/.codex config from unit tests.
    import importlib.util
    import tempfile as _tf
    tmp = _tf.mkdtemp(prefix="clearjev-ctl-")
    os.environ["CLEARJEV_CONFIG"] = os.path.join(tmp, "config.json")
    os.environ["CLEARJEV_STATE"] = os.environ["CLEARJEV_CONFIG"]
    os.environ["CLEARJEV_CREDENTIALS"] = os.path.join(tmp, "creds.json")
    try:
        spec = importlib.util.spec_from_file_location("jev_ctl", HOOK)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.chat_control_command(text)
    finally:
        for key in ("CLEARJEV_CONFIG", "CLEARJEV_STATE", "CLEARJEV_CREDENTIALS"):
            os.environ.pop(key, None)


class TestAutoSwitch(unittest.TestCase):
    """Same-thread switch: success, failure, and opt-out paths."""

    def test_already_on_same_model(self):
        mod = load_router_module()
        decision = switch_decision(model="gpt-5.6-sol", current="gpt-5.6-sol")
        mod.maybe_switch(decision, "any-session")
        self.assertEqual(decision["switch"], "already")
        self.assertIn("no switch needed", mod.render(decision))

    def test_unknown_current_model_stays_advisory(self):
        mod = load_router_module()
        decision = switch_decision(current="unknown")
        mod.maybe_switch(decision, "any-session")
        self.assertEqual(decision["switch"], "already")
        self.assertNotIn("Switched", mod.render(decision))

    def test_success_marks_switched(self):
        mod = load_router_module()
        mod.rpc_thread_settings = lambda *a, **k: (True, "confirmed")
        decision = switch_decision()
        mod.maybe_switch(decision, "session-123")
        self.assertEqual(decision["switch"], "done")
        self.assertIn("Switched this session to gpt-5.6-luna (low)",
                      mod.render(decision))

    def test_failure_stays_honest(self):
        mod = load_router_module()
        mod.rpc_thread_settings = lambda *a, **k: (False, "boom")
        decision = switch_decision()
        mod.maybe_switch(decision, "session-123")
        self.assertEqual(decision["switch"], "failed: boom")
        self.assertIn("Switch failed (boom)", mod.render(decision))
        self.assertNotIn("Switched this session", mod.render(decision))

    def test_missing_socket_fails_open(self):
        # Invalid id against a live daemon, or missing socket without one:
        # either way a clean (False, detail) pair, never an exception.
        mod = load_router_module()
        ok, detail = mod.rpc_thread_settings("s", "m", "low", timeout=5)
        self.assertFalse(ok)
        self.assertIsInstance(detail, str)
        self.assertTrue(detail)

    def test_no_session_id_skips_rpc(self):
        mod = load_router_module()
        calls = []
        mod.rpc_thread_settings = lambda *a, **k: calls.append(a) or (True, "x")
        decision = switch_decision()
        mod.maybe_switch(decision, "")
        self.assertEqual(calls, [])
        self.assertTrue(decision["switch"].startswith("failed"))

    def test_autoswitch_command_roundtrip(self):
        proc, state = run_cli("autoswitch", "off")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("OFF", proc.stdout)
        proc, _ = run_cli("autoswitch", env_extra={"CLEARJEV_STATE": state})
        self.assertIn("OFF", proc.stdout)
        proc, _ = run_cli("autoswitch", "on",
                          env_extra={"CLEARJEV_STATE": state})
        self.assertIn("ON", proc.stdout)

    def test_unavailable_thread_stays_advisory(self):
        mod = load_router_module()
        self.assertTrue(mod.classify_unavailable("thread not found: abc"))
        self.assertTrue(mod.classify_unavailable("Thread Not Found"))
        self.assertFalse(mod.classify_unavailable("handshake refused"))
        self.assertFalse(mod.classify_unavailable(""))
        mod.rpc_thread_settings = lambda *a, **k: (False, "thread not found: abc")
        decision = switch_decision()
        mod.maybe_switch(decision, "abc")
        self.assertTrue(decision["switch"].startswith("unavailable"))
        rendered = mod.render(decision)
        self.assertIn("Switch unavailable in this host", rendered)
        self.assertIn("use /model", rendered)
        self.assertNotIn("Switched this session", rendered)

    def test_retry_only_on_transient(self):
        mod = load_router_module()
        calls = []
        def flaky(*a, **k):
            calls.append(1)
            if len(calls) == 1:
                return False, "no settings response", True
            return True, "confirmed", False
        mod._update_once = flaky
        ok, detail = mod.rpc_thread_settings("tid", "m", "low", timeout=10)
        self.assertTrue(ok)
        self.assertEqual(len(calls), 2)
        calls.clear()
        def deterministic(*a, **k):
            calls.append(1)
            return False, "thread not found", False
        mod._update_once = deterministic
        ok, detail = mod.rpc_thread_settings("tid", "m", "low", timeout=10)
        self.assertFalse(ok)
        self.assertEqual(len(calls), 1)

    def test_endpoint_override_env(self):
        mod = load_router_module()
        os.environ["CLEARJEV_APP_SERVER_SOCK"] = "/tmp/cj-custom.sock"
        try:
            self.assertEqual(mod.app_server_endpoints(), ["/tmp/cj-custom.sock"])
        finally:
            del os.environ["CLEARJEV_APP_SERVER_SOCK"]

    def test_autoswitch_off_disables_switch(self):
        mod = load_router_module()
        import tempfile as _tf
        tmp = _tf.mkdtemp(prefix="clearjev-asw-")
        cfg = os.path.join(tmp, "config.json")
        with open(cfg, "w") as f:
            json.dump({"auto_switch": False}, f)
        os.environ["CLEARJEV_CONFIG"] = cfg
        try:
            self.assertFalse(mod.auto_switch_enabled())
            calls = []
            mod.rpc_thread_settings = lambda *a, **k: calls.append(a) or (True, "x")
            decision = switch_decision()
            mod.maybe_switch(decision, "session-123")
            self.assertEqual(calls, [])
            self.assertIn("auto-switch disabled", decision["switch"])
        finally:
            del os.environ["CLEARJEV_CONFIG"]


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
        # Act-first behavior with menu only as fallback.
        self.assertIn("Act first (default)", text)
        self.assertIn("Fallback menu (only for empty or garbled messages)", text)
        for item in ("1. on", "2. off", "3. status", "4. key",
                     "5. models", "6. run"):
            self.assertIn(item, text)
        # Picker trigger words in the description.
        self.assertIn("on/off/status", text.split("---")[1])
        # CLI-only: mandatory host check with App refusal text.
        self.assertIn("## Host check (mandatory, first step)", text)
        self.assertIn("Codex CLI only", text)
        self.assertIn("ClearJev control is CLI-only", text)

    def test_prompt_files_have_descriptions(self):
        proms = os.path.join(self.ROOT, "prompts")
        names = sorted(f for f in os.listdir(proms) if f.endswith(".md"))
        self.assertTrue({"clearjev.md", "clearjev-on.md", "clearjev-off.md",
                         "clearjev-add.md", "clearjev-remove.md",
                         "clearjev-key.md"} <= set(names))
        for name in names:
            with open(os.path.join(proms, name)) as f:
                self.assertIn("description:", f.read())
        with open(os.path.join(proms, "clearjev.md")) as f:
            self.assertIn("Codex CLI only", f.read())

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
