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

import hashlib
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSET_CONFIG = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "assets", "router-config.json"))
REASONING_ORDER = ("low", "medium", "high", "xhigh", "max", "ultra")


def load_router_config():
    """Load the shipped, human-reviewable routing configuration."""
    with open(ASSET_CONFIG, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data.get("models"), dict) or not data["models"]:
        raise ValueError("router-config.json has no models")
    return data


ROUTER_CONFIG = load_router_config()
JEV_ENDPOINT = ROUTER_CONFIG["jev"]["endpoint"]
JEV_MODEL = ROUTER_CONFIG["jev"]["model"]
JEV_TIMEOUT = ROUTER_CONFIG["jev"]["timeout_seconds"]

INTENTS = ("explain", "question", "generate", "implement", "debug",
           "refactor", "architect", "review", "research", "test",
           "migration", "security", "documentation", "unknown")

# Profiles are loaded from assets/router-config.json and can be enabled,
# disabled, or extended in the user's ClearJev config.


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


# ---------------------------------------------------------------- local configuration

def codex_home():
    return os.environ.get("CODEX_HOME") or os.path.join(
        os.path.expanduser("~"), ".codex")


def data_dir():
    return os.environ.get("CLEARJEV_DATA") or os.path.join(
        codex_home(), "clearjev")


def config_path():
    return os.environ.get("CLEARJEV_CONFIG") or os.environ.get(
        "CLEARJEV_STATE") or os.path.join(data_dir(), "config.json")


def credentials_path():
    return os.environ.get("CLEARJEV_CREDENTIALS") or os.path.join(
        data_dir(), "credentials.json")


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            value = json.load(f)
        return value if isinstance(value, type(default)) else default
    except (OSError, ValueError):
        return default


def write_private_json(path, value):
    """Atomically write user configuration with owner-only permissions."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, mode=0o700, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write("\n")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def user_config():
    return read_json(config_path(), {})


def model_catalog():
    """Return visible Codex models and supported reasoning efforts."""
    path = os.environ.get("CLEARJEV_MODELS_CACHE") or os.path.join(
        codex_home(), "models_cache.json")
    data = read_json(path, {})
    out = {}
    for model in data.get("models", []):
        if not isinstance(model, dict) or model.get("visibility") == "hide":
            continue
        slug = model.get("slug")
        levels = [item.get("effort") for item in
                  model.get("supported_reasoning_levels", [])
                  if isinstance(item, dict) and item.get("effort") in REASONING_ORDER]
        if isinstance(slug, str) and slug:
            out[slug] = levels
    return out


def inferred_profile(slug, reasoning):
    low = slug.lower()
    if "astra" in low:
        caps, cost = ({"coding": 10, "reasoning": 10, "planning": 10,
                       "architecture": 10, "context": 10, "explanation": 9}, 4)
    elif "sol" in low:
        caps, cost = ({"coding": 9, "reasoning": 8, "planning": 8,
                       "architecture": 8, "context": 8, "explanation": 7}, 3)
    elif "luna" in low:
        caps, cost = ({"coding": 4, "reasoning": 3, "planning": 2,
                       "architecture": 2, "context": 4, "explanation": 8}, 1)
    elif "terra" in low:
        caps, cost = ({"coding": 6, "reasoning": 5, "planning": 5,
                       "architecture": 4, "context": 6, "explanation": 7}, 2)
    else:
        caps, cost = ({"coding": 7, "reasoning": 7, "planning": 6,
                       "architecture": 6, "context": 7, "explanation": 7}, 2)
    return {"capabilities": caps, "cost_class": cost,
            "reasoning": list(reasoning or ("low", "medium", "high"))}


def active_profiles():
    """Build routing candidates from the live Codex catalog first.

    Every visible catalog model gets a profile: the shipped curated one when
    available, otherwise an inferred one from the slug family. User overrides
    then enable/disable models or restrict reasoning. Nothing is hardcoded:
    if Codex adds or renames a model, it becomes routable without a release.
    """
    shipped = ROUTER_CONFIG["models"]
    catalog = model_catalog()
    overrides = user_config().get("models", {})
    if not isinstance(overrides, dict):
        overrides = {}
    out = {}
    for slug in sorted(set(shipped) | set(catalog) | set(overrides)):
        override = overrides.get(slug)
        if not isinstance(override, dict):
            override = {}
        if slug in shipped:
            profile = json.loads(json.dumps(shipped[slug]))
        else:
            profile = inferred_profile(slug, catalog.get(slug))
        profile.update({k: v for k, v in override.items()
                        if k in ("capabilities", "cost_class", "reasoning")})
        if override.get("enabled", True) is False:
            continue
        if catalog and slug not in catalog:
            continue
        allowed = [x for x in profile.get("reasoning", []) if x in REASONING_ORDER]
        if catalog and catalog.get(slug):
            allowed = [x for x in allowed if x in catalog[slug]]
        if not allowed:
            continue
        profile["reasoning"] = allowed
        out[slug] = profile
    return out


def get_api_key():
    key = os.environ.get("TYPESAFE_API_KEY") or os.environ.get("JEV_API_KEY")
    if key:
        return key.strip()
    value = read_json(credentials_path(), {})
    key = value.get("api_key") if isinstance(value, dict) else None
    return key.strip() if isinstance(key, str) else ""


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
    weights = ROUTER_CONFIG["weights"]
    return round(100 * (weights["coding"] * norm3(coding)
                        + weights["reasoning"] * norm3(reasoning)
                        + weights["repository"] * norm3(repo)
                        + weights["risk"] * norm3(risk)
                        + weights["ambiguity"] * max(
                            0.0, min(1.0, float(ambiguous)))), 1)


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


def pick_model(demands, intent, complexity, profiles=None):
    """score(model, task) = capabilityFit + contextFit - costPenalty + policyBonus."""
    profiles = profiles if profiles is not None else active_profiles()
    # Cheap Q&A policy: explanation-class intents go to the cheapest model
    # with strong explanation capability (never a suggestion for other intents).
    if intent in ("explain", "question", "documentation"):
        cheap = [name for name, profile in profiles.items()
                 if profile["capabilities"].get("explanation", 0) >= 7
                 and (not demands.get("security_floor")
                      or profile["capabilities"].get("reasoning", 0) >= 8)]
        if cheap:
            return min(cheap, key=lambda name: (
                profiles[name]["cost_class"],
                -profiles[name]["capabilities"].get("explanation", 0)))
    arch = 1.0 if intent == "architect" else demands["reasoning"] * 0.5
    best, best_score = None, float("-inf")
    for name, profile in sorted(profiles.items()):
        caps = profile["capabilities"]
        cost = profile["cost_class"]
        if demands.get("security_floor") and caps.get("reasoning", 0) < 8:
            continue
        if intent == "architect" and caps.get("architecture", 0) < 6:
            continue
        fit = (caps["coding"] * demands["coding"]
               + caps["reasoning"] * demands["reasoning"]
               + caps["planning"] * demands["planning"]
               + caps["architecture"] * arch
               + caps["context"] * demands["repo"]) / 5.0
        penalty = 8 * cost * (1.5 if complexity < 40 else 1.0)
        bonus = 0.0
        if intent in ("explain", "question", "documentation"):
            bonus = caps.get("explanation", 0) * 1.5
        elif intent == "debug" and "sol" in name:
            bonus = 8.0
        score = fit * 10 - penalty + bonus
        if score > best_score:
            best, best_score = name, score
    if best is None and profiles:
        best = max(profiles, key=lambda name: (
            profiles[name]["capabilities"].get("reasoning", 0),
            profiles[name]["capabilities"].get("coding", 0)))
    return best


def reasoning_for(complexity, profile, security_floor=False):
    desired = ("low" if complexity < 30 else "medium" if complexity < 60
               else "high" if complexity < 80 else "xhigh"
               if complexity < 95 else "max")
    if security_floor and REASONING_ORDER.index(desired) < REASONING_ORDER.index("high"):
        desired = "high"
    allowed = profile.get("reasoning", ["medium"])
    target = REASONING_ORDER.index(desired)
    higher = [level for level in allowed
              if REASONING_ORDER.index(level) >= target]
    return higher[0] if higher else allowed[-1]


def level_for(complexity, kind, security_floor=False):
    if kind == "reasoning":
        # Kept for callers that do not yet have a model profile.
        return ("low" if complexity < 30 else "medium" if complexity < 60
                else "high" if complexity < 80 else "xhigh"
                if complexity < 95 else "max")
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
    if mean_conf < ROUTER_CONFIG["thresholds"]["complexity_confidence_floor"]:
        complexity = min(99.0, complexity + 10)  # safe side when unsure

    demands = {"coding": norm3(coding), "reasoning": norm3(reasoning),
               "planning": norm3(planning), "repo": norm3(repo),
                "security_floor": sec >= ROUTER_CONFIG["thresholds"]["security_noul_floor"]
                or intent == "security"}
    profiles = active_profiles()
    model = pick_model(demands, intent, complexity, profiles)
    if model is None:
        raise ValueError("no enabled model profiles are available")
    reasoning_lvl = reasoning_for(complexity, profiles[model],
                                  demands["security_floor"])
    planning_lvl = level_for(complexity, "planning")
    requires_repo = nl("requires_repo")
    repo_lvl = (level_for(complexity, "repo") if requires_repo >= 0.5
                else "unnecessary")
    val_a = answers.get("validation_need", {})
    validation = val_a.get("choice") if val_a.get("confidence", 0) >= 0.6 else None
    validation = validation or level_for(complexity, "validation")
    if intent == "architect":
        planning_lvl = "deep" if complexity < 90 else "multi_phase"
    if demands["security_floor"] and validation in ("none", "basic", "none/basic"):
        validation = "deep"

    uncertain = (intent_conf < ROUTER_CONFIG["thresholds"]["intent_confidence_floor"]
                 or intent == "unknown")
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
    (("migrate", "migration", "upgrade framework", "upgrade database"), "migration"),
    (("refactor", "split", "rename", "restructure"), "refactor"),
    (("review", "audit", "look over"), "review"),
    (("research", "compare options", "survey", "investigate options"), "research"),
    (("document", "readme", "write docs", "comment"), "documentation"),
    (("explain", "what is", "what are", "how does", "how do", "why is",
      "summar"), "explain"),
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
    profiles = active_profiles()
    model = pick_model(demands, intent, complexity, profiles)
    if model is None:
        raise ValueError("no enabled model profiles are available")
    return {"intent": intent, "intent_conf": 0.0, "complexity": complexity,
             "band": band(complexity), "mean_conf": 0.0,
            "model": model,
            "reasoning": reasoning_for(complexity, profiles[model], sec),
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
           else "ClearJev routing · heuristic fallback · "
           + decision.get("fallback_reason", "Jev unavailable"))
    head = ("%s | intent=%s (%.2f) · complexity=%.0f (%s)") % (
        src, decision["intent"], decision["intent_conf"],
        decision["complexity"], decision["band"])
    current = decision.get("current_model") or "unknown"
    body = ("Recommended model: %s · Current model: %s · Reasoning: %s · "
            "Planning: %s · Validation: %s · Repo: %s"
            % (decision["model"], current, decision["reasoning"],
               decision["planning"], decision["validation"], decision["repo"]))
    why = "Why: " + "; ".join(decision["reasons"]) + "."
    if decision["uncertain"]:
        why += (" If intent looks wrong, reply 'reroute: <what it really is>' "
                "before editing; prefer a targeted scan over guessing.")
    else:
        why += " If this looks wrong, reply 'reroute: <correction>'."
    if current != "unknown" and current != decision["model"]:
        why += " Advisory only: use /model to switch this session."
    return "\n".join((head, body, why))


def emit(additional_context):
    sys.stdout.write(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": additional_context}}))


# ---------------------------------------------------------------- on/off switch

def state_path():
    """Backward-compatible name for the single stable user config path."""
    return config_path()


def is_disabled():
    """True when routing must stay silent. Never raises."""
    env = os.environ.get("CLEARJEV_ENABLED", "").strip().lower()
    if env in ("0", "false", "no", "off"):
        return True, "env CLEARJEV_ENABLED=0"
    if env in ("1", "true", "yes", "on"):
        return False, ""
    try:
        data = user_config()
        if isinstance(data, dict) and data.get("enabled") is False:
            return True, state_path()
    except (OSError, ValueError):
        pass
    return False, ""


def set_enabled(enabled):
    """Persist the on/off flag. Returns (ok, message). Never raises."""
    path = state_path()
    try:
        data = user_config()
        data["enabled"] = bool(enabled)
        write_private_json(path, data)
        return True, path
    except OSError as exc:
        return False, str(exc)


def status():
    """Human-readable status for `clearjev status`. Manual use only."""
    disabled, reason = is_disabled()
    key = get_api_key()
    print("ClearJev status")
    print("- routing: " + ("OFF (" + reason + ")" if disabled else "ON"))
    print("- state file: " + state_path())
    print("- TYPESAFE_API_KEY: " + ("set" if key else "MISSING (heuristic fallback)"))
    print("- models: " + str(len(active_profiles())) + " enabled / "
          + str(len(model_catalog()) or len(ROUTER_CONFIG["models"])) + " available")
    demo = heuristic_route("Add a dark mode toggle to the settings page.", {})
    print("- fallback smoke: %s/%.0f/%s" % (demo["intent"], demo["complexity"], demo["model"]))
    return 0


# ---------------------------------------------------------------- entry

def set_api_key(value):
    value = (value or "").strip()
    if not value:
        return False, "API key must not be empty"
    try:
        write_private_json(credentials_path(), {"api_key": value})
        return True, credentials_path()
    except OSError as exc:
        return False, str(exc)


def key_command(args):
    action = args[0].lower() if args else "status"
    if action == "status":
        print("TypeSafe API key: " + ("set" if get_api_key() else "missing"))
        print("Credentials file: " + credentials_path())
        return 0
    if action == "set":
        value = args[1] if len(args) > 1 else ""
        ok, message = set_api_key(value)
        print("TypeSafe API key saved to " + message if ok else "Failed: " + message)
        return 0 if ok else 1
    if action == "import-env":
        ok, message = set_api_key(os.environ.get("TYPESAFE_API_KEY", ""))
        print("TypeSafe API key saved to " + message if ok else "Failed: " + message)
        return 0 if ok else 1
    if action in ("unset", "remove"):
        try:
            os.remove(credentials_path())
        except FileNotFoundError:
            pass
        except OSError as exc:
            print("Failed: " + str(exc))
            return 1
        print("TypeSafe API key removed")
        return 0
    print("Usage: clearjev key set <key>|unset|status")
    return 2


def parse_reasoning(args, default):
    value = None
    for index, arg in enumerate(args):
        if arg == "--reasoning" and index + 1 < len(args):
            value = args[index + 1]
        elif arg.startswith("--reasoning="):
            value = arg.split("=", 1)[1]
    if not value or value == "all":
        return list(default)
    levels = [item.strip().lower() for item in value.split(",") if item.strip()]
    invalid = [item for item in levels if item not in REASONING_ORDER]
    if invalid:
        raise ValueError("invalid reasoning: " + ", ".join(invalid))
    return levels


def save_model_override(slug, changes):
    data = user_config()
    models = data.setdefault("models", {})
    current = models.setdefault(slug, {})
    current.update(changes)
    write_private_json(config_path(), data)


def models_command(args):
    action = args[0].lower() if args else "list"
    catalog = model_catalog()
    if action in ("list", "status"):
        active = active_profiles()
        print("ClearJev models")
        for slug in sorted(set(ROUTER_CONFIG["models"]) | set(catalog)
                           | set(user_config().get("models", {}))):
            if slug in active:
                print("- %s: enabled [%s]" % (
                    slug, ",".join(active[slug]["reasoning"])))
            else:
                reason = "unavailable" if catalog and slug not in catalog else "disabled"
                print("- %s: %s" % (slug, reason))
        return 0
    if action == "available":
        source = catalog or {name: value["reasoning"] for name, value in
                             ROUTER_CONFIG["models"].items()}
        for slug, levels in sorted(source.items()):
            print("%s [%s]" % (slug, ",".join(levels)))
        return 0
    if action == "add" and len(args) >= 2:
        slug = args[1]
        if catalog and slug not in catalog:
            print("Failed: model is not available in this Codex catalog: " + slug)
            return 1
        defaults = catalog.get(slug) or ROUTER_CONFIG["models"].get(
            slug, {}).get("reasoning") or ("low", "medium", "high")
        try:
            levels = parse_reasoning(args[2:], defaults)
        except ValueError as exc:
            print("Failed: " + str(exc))
            return 2
        if catalog.get(slug):
            unsupported = [level for level in levels if level not in catalog[slug]]
            if unsupported:
                print("Failed: unsupported by %s: %s" % (slug, ", ".join(unsupported)))
                return 1
        save_model_override(slug, {"enabled": True, "reasoning": levels})
        print("Model added: %s [%s]" % (slug, ",".join(levels)))
        return 0
    if action == "remove" and len(args) == 2:
        save_model_override(args[1], {"enabled": False})
        print("Model removed from routing: " + args[1])
        return 0
    if action == "reasoning" and len(args) >= 4:
        slug, operation = args[1], args[2].lower()
        requested = [value.strip().lower() for value in
                     ",".join(args[3:]).split(",") if value.strip()]
        if any(value not in REASONING_ORDER for value in requested):
            print("Failed: reasoning must be one of " + ",".join(REASONING_ORDER))
            return 2
        profiles = active_profiles()
        base = profiles.get(slug) or ROUTER_CONFIG["models"].get(slug)
        if not base:
            print("Failed: add the model first")
            return 1
        levels = list(base.get("reasoning", []))
        if operation == "add":
            for value in requested:
                if catalog.get(slug) and value not in catalog[slug]:
                    print("Failed: %s does not support %s" % (slug, value))
                    return 1
                if value not in levels:
                    levels.append(value)
            levels.sort(key=REASONING_ORDER.index)
        elif operation == "remove":
            levels = [value for value in levels if value not in requested]
            if not levels:
                print("Failed: a model needs at least one reasoning level")
                return 1
        else:
            print("Usage: clearjev models reasoning <model> add|remove <levels>")
            return 2
        save_model_override(slug, {"enabled": True, "reasoning": levels})
        print("Model reasoning updated: %s [%s]" % (slug, ",".join(levels)))
        return 0
    print("Usage: clearjev models list|available|add <model> [--reasoning all|low,medium,...]|remove <model>|reasoning <model> add|remove <levels>")
    return 2


def fallback_reason(exc):
    if exc is None:
        return "API key missing"
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 401:
            return "API key rejected (HTTP 401)"
        if exc.code in (429, 529):
            return "Jev temporarily unavailable (HTTP %s)" % exc.code
        return "Jev HTTP %s" % exc.code
    if isinstance(exc, (TimeoutError, urllib.error.URLError)):
        return "Jev network timeout"
    return "Jev response error"


def route_prompt(prompt, cwd, current_model=""):
    repo_meta = collect_repo_meta(cwd)
    state = {"prompt": {"text": prompt}, "repo": repo_meta,
             "note": ("Classify the developer request in `prompt.text`. "
                      "Use `repo` only as background.")}
    api_key = get_api_key()
    decision = None
    error = None
    if api_key:
        try:
            response = call_jev(state, api_key)
            decision = route_from_jev(response.get("answers", {}))
        except Exception as exc:
            error = exc
    if decision is None:
        decision = heuristic_route(prompt, repo_meta)
        decision["fallback_reason"] = fallback_reason(error)
    decision["current_model"] = current_model
    return decision


def run_command(args):
    dry_run = "--dry-run" in args
    prompt_parts = [arg for arg in args if arg != "--dry-run"]
    prompt = " ".join(prompt_parts).strip()
    if not prompt:
        print("Usage: clearjev run [--dry-run] <prompt>")
        return 2
    decision = route_prompt(prompt, os.getcwd())
    command = ["codex", "--model", decision["model"], "-c",
               'model_reasoning_effort="%s"' % decision["reasoning"], prompt]
    print(render(decision))
    if dry_run:
        print("Command: " + " ".join(command))
        return 0
    os.environ["CLEARJEV_SKIP_PROMPT_HASH"] = hashlib.sha256(
        prompt.encode("utf-8")).hexdigest()
    try:
        os.execvp(command[0], command)
    except OSError as exc:
        print("Failed to start Codex: " + str(exc))
        return 1

def main(argv):
    args = list(argv[1:])
    command = args[0].lower().lstrip("-") if args else ""
    if command == "off":
        ok, msg = set_enabled(False)
        print("ClearJev routing OFF (" + msg + ")" if ok else "Failed: " + msg)
        return 0 if ok else 1
    if command == "on":
        ok, msg = set_enabled(True)
        print("ClearJev routing ON (" + msg + ")" if ok else "Failed: " + msg)
        return 0 if ok else 1
    if command == "status":
        return status()
    if command == "check":
        return check()
    if command == "key":
        return key_command(args[1:])
    if command in ("models", "model"):
        return models_command(args[1:])
    if command == "run":
        return run_command(args[1:])
    if command in ("help", "h") or (not args and sys.stdin.isatty()):
        print("ClearJev: on | off | status | check | key | models | run")
        print("Use 'clearjev models --help' or see README.md for details.")
        return 0
    disabled, _reason = is_disabled()
    if disabled:
        return 0  # paused: silent no-op, zero cost
    prompt, cwd = "", ""
    if "--prompt" in args:
        try:
            prompt = args[args.index("--prompt") + 1]
        except IndexError:
            prompt = ""
    if "--cwd" in args:
        try:
            cwd = args[args.index("--cwd") + 1]
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
    if prompt.lstrip().lower().startswith("reroute:"):
        return 0  # correction handled conversationally; do not re-route
    skip_hash = os.environ.get("CLEARJEV_SKIP_PROMPT_HASH", "")
    if skip_hash and hashlib.sha256(prompt.encode("utf-8")).hexdigest() == skip_hash:
        return 0
    if not cwd or not os.path.isdir(cwd):
        cwd = os.getcwd()

    current_model = payload.get("model", "") if isinstance(payload, dict) else ""
    decision = route_prompt(prompt, cwd, current_model)
    emit(render(decision))
    return 0


def check():
    """Installer verification: setup + optional live Jev ping."""
    ok = True
    print("ClearJev check")
    print("- python: " + sys.version.split()[0])
    key = get_api_key()
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
