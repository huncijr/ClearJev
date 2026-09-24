#!/usr/bin/env python3
"""ClearJev pre-prompt router — Codex UserPromptSubmit hook.

Reads the Codex hook payload (JSON) from stdin, judges the prompt with
TypeSafe Jev (System One, one batched request), composes the routing decision
in code, and prints hook JSON with `additionalContext` to stdout.

Contract (Codex hooks):
  stdin  - {"prompt": str, "cwd": str, "model": str, "session_id": str, ...}
  stdout - {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
            "additionalContext": "<routing block>"}}
  Fail-open: on ANY error print nothing and exit 0 (session must never break
  because routing failed). Never emit decision:block.

Stdlib only (urllib/json/os/subprocess) so the hook runs on macOS, Windows
and Linux with stock python3 and no pip install.

Env:
  TYPESAFE_API_KEY (fallback JEV_API_KEY) - without it, a clearly labeled
  heuristic fallback is used so the layer still works out of the box.
  CLEARJEV_ENABLED=0 - instant kill-switch: the hook exits silently (no
  routing, no Jev call, no cost). Any of 0/false/no/off disables;
  1/true/yes/on forces enabled. Unset = follow the state file.
  CLEARJEV_STATE - override path of the on/off state file (used by tests).

On/off (persistent, works in Codex CLI and App, no restart needed):
  python3 jev_route.py --off     # pause routing
  python3 jev_route.py --on      # resume routing
  python3 jev_route.py --status  # show on/off + key + routing smoke test

Per-prompt bypass: start the prompt with "noroute:" to skip routing once.

Usage:
  echo '{"prompt":"...","cwd":"."}' | python3 jev_route.py
  python3 jev_route.py --prompt "Fix the 500 on uploads" --cwd .
  python3 jev_route.py --check
"""

import json
import os
import subprocess
import sys
import urllib.request
import urllib.error

JEV_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
JEV_MODEL = "jev-latest"
JEV_TIMEOUT = 8  # seconds; hook timeout is 12s, leave headroom

INTENTS = ("explain", "question", "generate", "implement", "debug",
           "refactor", "architect", "review", "research", "test",
           "migration", "security", "documentation", "unknown")

# (model, capabilities 0-10, costClass 1-4). Explicit config, not model output.
PROFILES = {
    "gpt-6-luna": ({"coding": 4, "reasoning": 3, "planning": 2,
                     "architecture": 2, "context": 4, "explanation": 8}, 1),
    "gpt-6-terra": ({"coding": 6, "reasoning": 5, "planning": 5,
                      "architecture": 4, "context": 6, "explanation": 7}, 2),
    "gpt-6-sol": ({"coding": 9, "reasoning": 8, "planning": 8,
                    "architecture": 8, "context": 8, "explanation": 7}, 3),
    "gpt-6-astra": ({"coding": 9, "reasoning": 10, "planning": 10,
                      "architecture": 10, "context": 10, "explanation": 8}, 4),
}


# ---------------------------------------------------------------- payload

def extract_prompt(payload):
    """Pull the user prompt out of known Codex hook payload shapes."""
    if not isinstance(payload, dict):
        return ""
    prompt = payload.get("prompt")
    if isinstance(prompt, str) and prompt.strip():
        return prompt.strip()
    event = payload.get("event")
    if isinstance(event, dict):
        for key in ("user_prompt", "prompt", "text"):
            val = event.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return ""


def collect_repo_meta(cwd):
    """Progressive Level 1 scan: metadata only, best-effort, never raises."""
    meta = {"languages": [], "top_files": [], "git_status": ""}
    try:
        entries = sorted(os.listdir(cwd or "."))
    except OSError:
        return meta
    meta["top_files"] = [e for e in entries if not e.startswith(".")][:40]
    markers = {"package.json": "node", "pyproject.toml": "python",
               "requirements.txt": "python", "Cargo.toml": "rust",
               "go.mod": "go", "pom.xml": "java", "Gemfile": "ruby",
               "composer.json": "php", "CMakeLists.txt": "cpp"}
    try:
        files = set(os.listdir(cwd or "."))
    except OSError:
        files = set()
    for marker, lang in markers.items():
        if marker in files and lang not in meta["languages"]:
            meta["languages"].append(lang)
    for fname in ("README.md", "README", "AGENTS.md", "CODEX.md"):
        if fname in files:
            meta["top_files"].insert(0, fname)
            break
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain=v1", "-uno"],
            cwd=cwd or ".", capture_output=True, text=True, timeout=3)
        if proc.returncode == 0 and proc.stdout.strip():
            lines = proc.stdout.strip().splitlines()[:20]
            meta["git_status"] = "\n".join(lines)
    except Exception:
        pass
    return meta


# ---------------------------------------------------------------- Jev call

def build_questions():
    """The 11-question batch (see references/jev-questions.md)."""
    return {
        "intent": {
            "type": "choice",
            "instructions": "What is the developer asking the agent to accomplish in `prompt.text`? Classify the primary requested outcome, not the topic words.",
            "criteria": {
                "explain": "Explain a concept; no repo change.",
                "question": "Answer about this repo's code.",
                "generate": "Small new snippet or single-file addition.",
                "implement": "Build a feature touching code.",
                "debug": "Find or fix a failure or bug.",
                "refactor": "Restructure code without behavior change.",
                "architect": "Design structure or decide tradeoffs; no immediate edit.",
                "review": "Critique given code or diff.",
                "research": "Survey options and report back.",
                "test": "Write or run tests.",
                "migration": "Move versions, frameworks, or data.",
                "security": "Harden, audit, or fix a vulnerability.",
                "documentation": "Write docs or comments.",
                "unknown": "None of the above fits.",
            },
        },
        "coding_demand": {
            "type": "score",
            "instructions": "How much code writing does `prompt.text` require?",
            "criteria": ["No code output.",
                         "Single snippet or small edit.",
                         "Multi-file feature or fix.",
                         "System-wide implementation or migration."],
        },
        "reasoning_demand": {
            "type": "score",
            "instructions": "How much careful reasoning (edge cases, tradeoffs, hidden interactions) does `prompt.text` need?",
            "criteria": ["Trivial, one obvious step.",
                         "Some judgment, few steps.",
                         "Deep reasoning, many interacting parts.",
                         "Novel design under uncertainty."],
        },
        "planning_demand": {
            "type": "score",
            "instructions": "How much up-front planning or decomposition does `prompt.text` need?",
            "criteria": ["None, act directly.",
                         "Light: 1-2 steps.",
                         "Standard: short plan, several files.",
                         "Deep or multi-phase plan required."],
        },
        "repo_demand": {
            "type": "score",
            "instructions": "How much repository context does `prompt.text` need, given `repo`?",
            "criteria": ["None, prompt is self-contained.",
                         "Targeted: 1-3 files.",
                         "Broad: a directory or subsystem.",
                         "Repository-wide analysis."],
        },
        "risk": {
            "type": "score",
            "instructions": "What is the cost of getting `prompt.text` wrong?",
            "criteria": ["Safe: typo, rename, docs.",
                         "Low: isolated change, easy revert.",
                         "Medium: auth/data/billing-adjacent or multi-file.",
                         "High: security, migration, or production data."],
        },
        "requires_repo": {
            "type": "noul",
            "instructions": "Does `prompt.text` need any file from `repo` to answer correctly?",
            "criteria": {"true": "Needs repo files.",
                         "false": "Answerable from the prompt alone."},
        },
        "security_sensitive": {
            "type": "noul",
            "instructions": "Does `prompt.text` touch auth, sessions, crypto, PII, payments, or access control?",
            "criteria": {"true": "Security-sensitive.",
                         "false": "No security sensitivity."},
        },
        "ambiguous": {
            "type": "noul",
            "instructions": "Is `prompt.text` ambiguous about what success looks like?",
            "criteria": {"true": "More than one plausible reading.",
                         "false": "Single clear reading."},
        },
        "change_size": {
            "type": "choice",
            "instructions": "What is the expected code change size for `prompt.text`?",
            "criteria": {"small": "One file, few lines.",
                         "medium": "Few files.",
                         "large": "Many files or subsystem.",
                         "massive": "Repository-wide."},
        },
        "validation_need": {
            "type": "choice",
            "instructions": "How much validation does `prompt.text` need?",
            "criteria": {"none": "No validation.",
                         "basic": "Eyeball the diff.",
                         "tests": "Run or add tests.",
                         "deep": "Tests plus edge cases.",
                         "full_regression": "Full regression suite."},
        },
    }


def call_jev(state, api_key):
    """One batched System One request. Raises on any failure (caller falls back)."""
    body = json.dumps({"state": state, "model": JEV_MODEL,
                       "questions": build_questions()}).encode("utf-8")
    req = urllib.request.Request(
        JEV_ENDPOINT, data=body,
        headers={"Authorization": "Bearer " + api_key,
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=JEV_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------- composition (code, not prompts)

def norm3(score):
    try:
        return max(0.0, min(1.0, float(score) / 3.0))
    except (TypeError, ValueError):
        return 0.5


def complexity_from_demands(coding, reasoning, repo, risk, ambiguous):
    return round(100 * (0.30 * norm3(coding) + 0.25 * norm3(reasoning)
                        + 0.15 * norm3(repo) + 0.20 * norm3(risk)
                        + 0.10 * max(0.0, min(1.0, float(ambiguous)))), 1)


def band(complexity):
    if complexity < 20:
        return "trivial"
    if complexity < 40:
        return "simple"
    if complexity < 60:
        return "moderate"
    if complexity < 75:
        return "complex"
    if complexity < 90:
        return "very complex"
    return "critical"


def pick_model(demands, intent, complexity):
    """score(model, task) = capabilityFit + contextFit - costPenalty + policyBonus."""
    arch = 1.0 if intent == "architect" else demands["reasoning"] * 0.5
    best, best_score = "gpt-6-terra", float("-inf")
    for name, (caps, cost) in sorted(PROFILES.items()):
        fit = (caps["coding"] * demands["coding"]
               + caps["reasoning"] * demands["reasoning"]
               + caps["planning"] * demands["planning"]
               + caps["architecture"] * arch
               + caps["context"] * demands["repo"]) / 5.0
        penalty = 8 * cost * (1.5 if complexity < 40 else 1.0)
        bonus = 0.0
        if intent in ("explain", "question", "documentation") and name == "gpt-6-luna":
            bonus = 15.0
        elif intent == "debug" and name == "gpt-6-sol":
            bonus = 8.0
        score = fit * 10 - penalty + bonus
        if score > best_score:
            best, best_score = name, score
    # Hard policy floors (never suggestions).
    if demands.get("security_floor") and best in ("gpt-6-luna", "gpt-6-terra"):
        best = "gpt-6-sol"
    if intent == "architect" and best == "gpt-6-luna":
        best = "gpt-6-terra"
    return best


def level_for(complexity, kind, security_floor=False):
    if kind == "reasoning":
        lvl = ("low" if complexity < 20 else "low/medium" if complexity < 40
               else "medium" if complexity < 60 else "high"
               if complexity < 90 else "very_high")
        if security_floor and lvl in ("low", "low/medium", "medium"):
            return "high"
        return lvl
    if kind == "planning":
        return ("none" if complexity < 20 else "light" if complexity < 40
                else "standard" if complexity < 60 else "deep"
                if complexity < 90 else "multi_phase")
    if kind == "repo":
        return ("unnecessary" if complexity < 20 else "targeted"
                if complexity < 50 else "broad" if complexity < 75 else "deep")
    # validation
    return ("none/basic" if complexity < 20 else "basic" if complexity < 40
            else "tests" if complexity < 60 else "deep"
            if complexity < 85 else "full_regression")


def route_from_jev(answers):
    """Compose a routing decision purely from typed Jev answers."""
    intent_a = answers.get("intent", {})
    intent = intent_a.get("choice", "unknown")
    if intent not in INTENTS:
        intent = "unknown"
    intent_conf = float(intent_a.get("confidence", 0) or 0)

    def sc(key):
        a = answers.get(key, {})
        return float(a.get("score", 1.5) or 0), float(a.get("confidence", 0) or 0)

    def nl(key):
        a = answers.get(key, {})
        try:
            return float(a.get("noul", 0.5))
        except (TypeError, ValueError):
            return 0.5

    coding, c_c = sc("coding_demand")
    reasoning, r_c = sc("reasoning_demand")
    planning, p_c = sc("planning_demand")
    repo, rp_c = sc("repo_demand")
    risk, rk_c = sc("risk")
    ambiguous = nl("ambiguous")
    sec = nl("security_sensitive")
    mean_conf = sum(x for x in (c_c, r_c, p_c, rp_c, rk_c) if x) / 5.0

    complexity = complexity_from_demands(coding, reasoning, repo, risk, ambiguous)
    if mean_conf < 0.50:
        complexity = min(99.0, complexity + 10)  # safe side when unsure

    demands = {"coding": norm3(coding), "reasoning": norm3(reasoning),
               "planning": norm3(planning), "repo": norm3(repo),
               "security_floor": sec >= 0.7 or intent == "security"}
    model = pick_model(demands, intent, complexity)
    reasoning_lvl = level_for(complexity, "reasoning", demands["security_floor"])
    planning_lvl = level_for(complexity, "planning")
    repo_lvl = level_for(complexity, "repo")
    val_a = answers.get("validation_need", {})
    validation = val_a.get("choice") if val_a.get("confidence", 0) >= 0.6 else None
    validation = validation or level_for(complexity, "validation")

    uncertain = intent_conf < 0.60 or intent == "unknown"
    reasons = reason_list(intent, complexity, sec, repo, risk, ambiguous)
    return {"intent": intent, "intent_conf": intent_conf,
            "complexity": complexity, "band": band(complexity),
            "mean_conf": mean_conf, "model": model,
            "reasoning": reasoning_lvl, "planning": planning_lvl,
            "repo": repo_lvl, "validation": validation,
            "uncertain": uncertain, "reasons": reasons, "source": "jev"}


def reason_list(intent, complexity, sec, repo, risk, ambiguous):
    out = []
    if intent != "unknown":
        out.append(intent + " task")
    if complexity >= 75:
        out.append("very high complexity")
    elif complexity >= 60:
        out.append("multi-file/subsystem scope")
    if sec >= 0.7:
        out.append("security-sensitive")
    if repo >= 2.0:
        out.append("broad repo context needed")
    if risk >= 2.0:
        out.append("medium-high failure cost")
    if ambiguous >= 0.7:
        out.append("ambiguous requirements")
    return out[:4] or ["routine task"]


# ---------------------------------------------------------------- heuristic fallback (no key / Jev down)

KEYWORDS = (
    (("security",), "security"),
    (("vuln", "exploit", "xss", "csrf", "injection", "auth", "oauth",
      "password", "session", "permission"), None),  # security flag only
    (("redesign", "design", "architect", "scale", "scaling", "multi-tenan",
      "microservice", "traffic", "tenancy"), "architect"),
    (("race condition", "deadlock", "500", "crash", "traceback", "failing",
      "broken", "bug", "debug", "why does", "not working", "find why",
      "disconnect", "intermittent", "flaky", "randomly", "timeout", "hang",
      "leak", "reproduc", "stack trace"), "debug"),
    (("refactor", "split", "rename", "migrate", "migration"), None),
    (("review", "audit", "look over"), "review"),
    (("explain", "what is", "what are", "how does", "how do", "why is",
      "document", "summar"), "explain"),
    (("test", "coverage", "regression"), "test"),
    (("implement", "build", "create", "add", "feature", "integrat",
      "dashboard", "system"), "implement"),
)


def heuristic_route(prompt, repo_meta):
    """Transparent keyword/size fallback. Clearly labeled, never silent."""
    low = prompt.lower()
    intent = "unknown"
    if any(k in low for k in ("implement", "build", "create", "add a",
                              "feature", "integrat")):
        intent = "implement"
    for keys, mapped in KEYWORDS:
        if any(k in low for k in keys) and mapped:
            # first strong match wins, except pure security-flag group (None)
            intent = mapped
            break
    sec_text = low.replace("dependency injection", " ").replace(
        "dependency-injection", " ")
    sec = any(k in sec_text for k in (
        "sql injection", "sql-injection", "sqli", "command injection",
        "prompt injection", "xss", "csrf",
        "auth", "oauth", "sso", "password", "session", "crypto", "pii",
        "payment", "stripe", "permission", "access control", "rbac",
        "secret", "vuln", "exploit")) or intent == "security"
    complexity = 20.0
    complexity += min(25.0, len(prompt) / 40.0)
    scope_signals = ("multi", "system", "architect", "migrat", "production",
                     "database", "postgres", "mysql", "mongodb", "redis",
                     "middlewar", "webhook", "subscrip", "payment", "stripe",
                     "oauth", "sso", "queue", "worker", "cron", "throughout",
                     "across", "end-to-end", "end to end", "multi-file",
                     "multiple files", "legacy", "backward compat",
                     "zero-downtime", "real-time", "realtime", "websocket",
                     "distributed", "multi-tenan", "tenancy", "ci/cd",
                     "pipeline", "k8s", "kubernetes", "terraform", "observab",
                     "tracing", "refactor", "codebase", "repo-wide", "entire",
                     "redesign", "traffic", "breaking", "10x", "sla")
    hits = sum(1 for k in scope_signals if k in low)
    complexity += min(45.0, 12.0 * hits)
    if intent in ("architect", "migration", "security"):
        complexity += 25
    elif intent == "debug":
        complexity += 15
    if sec:
        complexity += 10
    if repo_meta.get("git_status"):
        complexity += 5
    complexity = max(5.0, min(95.0, round(complexity, 1)))
    demands = {"coding": 0.7 if intent == "implement" else 0.4,
               "reasoning": 0.7 if intent in ("debug", "architect") else 0.4,
               "planning": 0.8 if intent == "architect" else 0.4,
               "repo": 0.6, "security_floor": sec}
    return {"intent": intent, "intent_conf": 0.0, "complexity": complexity,
            "band": band(complexity), "mean_conf": 0.0,
            "model": pick_model(demands, intent, complexity),
            "reasoning": level_for(complexity, "reasoning", sec),
            "planning": level_for(complexity, "planning"),
            "repo": level_for(complexity, "repo"),
            "validation": level_for(complexity, "validation"),
            "uncertain": True, "reasons": reason_list(intent, complexity,
                                                      1.0 if sec else 0.0,
                                                      1.5, 1.5, 0.5),
            "source": "heuristic"}


# ---------------------------------------------------------------- rendering

def render(decision):
    src = ("ClearJev routing · jev" if decision["source"] == "jev"
           else "ClearJev routing · heuristic fallback — set TYPESAFE_API_KEY for Jev")
    head = ("%s | intent=%s (%.2f) · complexity=%.0f (%s)") % (
        src, decision["intent"], decision["intent_conf"],
        decision["complexity"], decision["band"])
    body = ("Model: %s · Reasoning: %s · Planning: %s · Validation: %s · Repo: %s"
            % (decision["model"], decision["reasoning"], decision["planning"],
               decision["validation"], decision["repo"]))
    why = "Why: " + "; ".join(decision["reasons"]) + "."
    if decision["uncertain"]:
        why += (" If intent looks wrong, reply 'reroute: <what it really is>' "
                "before editing; prefer a targeted scan over guessing.")
    else:
        why += " If this looks wrong, reply 'reroute: <correction>'."
    return "\n".join((head, body, why))


def emit(additional_context):
    sys.stdout.write(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": additional_context}}))


# ---------------------------------------------------------------- on/off switch

def state_path():
    """Where the persistent on/off flag lives.

    Precedence: $CLEARJEV_STATE > $PLUGIN_DATA/state.json > ~/.codex/clearjev.json.
    PLUGIN_DATA is set by Codex for plugin-bundled hooks; the ~/.codex
    fallback covers standalone skill installs.
    """
    override = os.environ.get("CLEARJEV_STATE")
    if override:
        return override
    plugin_data = os.environ.get("PLUGIN_DATA")
    if plugin_data:
        return os.path.join(plugin_data, "state.json")
    return os.path.join(os.path.expanduser("~"), ".codex", "clearjev.json")


def is_disabled():
    """True when routing must stay silent. Never raises."""
    env = os.environ.get("CLEARJEV_ENABLED", "").strip().lower()
    if env in ("0", "false", "no", "off"):
        return True, "env CLEARJEV_ENABLED=0"
    if env in ("1", "true", "yes", "on"):
        return False, ""
    try:
        with open(state_path()) as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("enabled") is False:
            return True, state_path()
    except (OSError, ValueError):
        pass
    return False, ""


def set_enabled(enabled):
    """Persist the on/off flag. Returns (ok, message). Never raises."""
    path = state_path()
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w") as f:
            json.dump({"enabled": bool(enabled)}, f)
        return True, path
    except OSError as exc:
        return False, str(exc)


def status():
    """Human-readable status for `clearjev status`. Manual use only."""
    disabled, reason = is_disabled()
    key = os.environ.get("TYPESAFE_API_KEY") or os.environ.get("JEV_API_KEY")
    print("ClearJev status")
    print("- routing: " + ("OFF (" + reason + ")" if disabled else "ON"))
    print("- state file: " + state_path())
    print("- TYPESAFE_API_KEY: " + ("set" if key else "MISSING (heuristic fallback)"))
    demo = heuristic_route("Add a dark mode toggle to the settings page.", {})
    print("- fallback smoke: %s/%.0f/%s" % (demo["intent"], demo["complexity"], demo["model"]))
    return 0


# ---------------------------------------------------------------- entry

def main(argv):
    if "--off" in argv:
        ok, msg = set_enabled(False)
        print("ClearJev routing OFF (" + msg + ")" if ok else "Failed: " + msg)
        return 0 if ok else 1
    if "--on" in argv:
        ok, msg = set_enabled(True)
        print("ClearJev routing ON (" + msg + ")" if ok else "Failed: " + msg)
        return 0 if ok else 1
    if "--status" in argv:
        return status()
    if "--check" in argv:
        return check()
    disabled, _reason = is_disabled()
    if disabled:
        return 0  # paused: silent no-op, zero cost
    prompt, cwd = "", ""
    if "--prompt" in argv:
        try:
            prompt = argv[argv.index("--prompt") + 1]
        except IndexError:
            prompt = ""
    if "--cwd" in argv:
        try:
            cwd = argv[argv.index("--cwd") + 1]
        except IndexError:
            cwd = ""
    raw = ""
    if not prompt and not sys.stdin.isatty():
        try:
            raw = sys.stdin.read()
        except Exception:
            raw = ""
    payload = {}
    if raw.strip():
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = {"prompt": raw}
    if not prompt:
        prompt = extract_prompt(payload)
    if not cwd:
        cwd = payload.get("cwd", "") if isinstance(payload, dict) else ""
    if not prompt:
        return 0  # fail-open: nothing to judge
    if prompt.lstrip().lower().startswith("noroute:"):
        return 0  # one-shot bypass for this prompt only
    if not cwd or not os.path.isdir(cwd):
        cwd = os.getcwd()

    repo_meta = collect_repo_meta(cwd)
    state = {"prompt": {"text": prompt}, "repo": repo_meta,
             "note": ("Classify the developer request in `prompt.text`. "
                      "Use `repo` only as background.")}

    api_key = os.environ.get("TYPESAFE_API_KEY") or os.environ.get("JEV_API_KEY") or ""
    decision = None
    if api_key:
        try:
            resp = call_jev(state, api_key)
            decision = route_from_jev(resp.get("answers", {}))
        except Exception:
            decision = None
    if decision is None:
        decision = heuristic_route(prompt, repo_meta)
    emit(render(decision))
    return 0


def check():
    """Installer verification: setup + optional live Jev ping."""
    ok = True
    print("ClearJev check")
    print("- python: " + sys.version.split()[0])
    key = os.environ.get("TYPESAFE_API_KEY") or os.environ.get("JEV_API_KEY")
    print("- TYPESAFE_API_KEY: " + ("set" if key else "MISSING (heuristic fallback will be used)"))
    if not key:
        ok = False
    if key:
        try:
            resp = call_jev(
                {"prompt": {"text": "Explain what a hook does."}, "repo": {}},
                key)
            print("- jev ping: ok (" + resp.get("model", "?") + ")")
        except urllib.error.HTTPError as exc:
            print("- jev ping: HTTP " + str(exc.code) + " (check key)")
            ok = False
        except Exception as exc:
            print("- jev ping: failed (" + str(exc) + ")")
            ok = False
    # routing smoke test (no network)
    demo = heuristic_route("Add a dark mode toggle to the settings page.", {})
    print("- fallback smoke: %s/%.0f/%s" % (demo["intent"], demo["complexity"], demo["model"]))
    print("OK" if ok else "CHECK FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except Exception:
        # Absolute last resort: never break the session.
        raise SystemExit(0)
