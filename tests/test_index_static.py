"""Static checks on the board page (plugins/slate/assets/board/index.html) and the demo fixture.

The page is one self-contained file with no dependencies; these tests pin the parts other code relies
on: the board API contract it calls in live mode, the view-only copy-as-commands feature, roles for
custom statuses, claims, removed tickets, unlock banner/history, doctor banners and polling.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "plugins" / "slate" / "assets" / "board" / "index.html"
DEMO = ROOT / "tests" / "fixtures" / "board-demo" / "tickets.json"


def page() -> str:
    return PAGE.read_text(encoding="utf-8")


def script() -> str:
    m = re.search(r"<script>(.*)</script>", page(), re.DOTALL)
    assert m, "index.html must keep its inline <script>"
    return m.group(1)


def test_no_other_product_names() -> None:
    assert not re.search(r"\bforge\b", page(), re.IGNORECASE)


def test_self_contained_no_external_resources() -> None:
    html = page()
    assert not re.search(r"<script[^>]+src=", html), "no external scripts"
    assert not re.search(r"<link[^>]+stylesheet", html), "no external stylesheets"
    assert not re.search(r"(?:src|href)=[\"']https?://", html), "no remote src/href"
    assert "import " not in script().split("\n", 3)[0]


def test_version_meta_matches_js_constant() -> None:
    html = page()
    meta = re.search(r'<meta name="slate-version" content="([^"]+)"', html).group(1)
    js = re.search(r'var SLATE_VERSION = "([^"]+)"', html).group(1)
    assert meta == js


def test_live_mode_api_contract() -> None:
    js = script()
    assert '"./api/info"' in js
    assert '"./api/allowed?id="' in js
    assert '"X-Slate-Token"' in js
    for endpoint in ("set", "check-item", "uncheck-item", "usertest", "note", "promote", "claim", "release"):
        assert f'"{endpoint}"' in js, endpoint
    assert '"needs_handoff"' in js
    assert '"reset"' in js and "Clear result" in js
    assert "take_over" in js
    assert "slate.claim.name" in js
    assert "Live: changes save to the board" in js
    assert "View only: open with" in js and "serve" in js


def test_view_only_copy_commands() -> None:
    js = script()
    assert "Copy as board.py commands" in page()
    for cmd in (" check-item ", " usertest ", " set "):
        assert cmd in js
    assert "navigator.clipboard" in js and 'execCommand("copy")' in js
    assert "local only" in js and "not on the board" in js
    assert "function pruneOverlay" in js
    assert "note for the ticket's history" in js


def test_roles_labels_claims_removed_unlock_doctor() -> None:
    js = script()
    for needle in ("status_labels", "status_roles", "status_from", "function roleOf", "claimed_by",
                   "On it: ", "on: ", "meta.removed", "restore ID", "unlock_log", "unlock_active",
                   ".slate-unlock.json", "Board history", "run /slate:sync", "run /slate:upgrade",
                   "One direct edit allowed until"):
        assert needle in js or needle in page(), needle


def test_polling_is_conditional_with_backoff_and_safety_net() -> None:
    js = script()
    assert '"If-Modified-Since"' in js and '"Last-Modified"' in js
    assert re.search(r"POLL_FAST_MS = 5000\b", js)
    assert re.search(r"POLL_SLOW_MS = 30000\b", js)
    assert re.search(r"IDLE_MS = 180000\b", js)
    assert re.search(r"SAFETY_MS = 30000\b", js)
    assert 'visibilityState !== "visible"' in js
    assert 'state.source !== "fetch"' in js


def test_behaviour_keys_off_roles_not_status_names() -> None:
    js = script()
    # isDone / isDraft / needsYou / isMergeReady go through roles, so renamed/custom statuses work.
    for fn in ("isDone", "isDraft", "needsYou", "isMergeReady"):
        body = re.search(r"function " + fn + r"\(t\) \{([^}]*)\}", js).group(1)
        assert "roleNow" in body, fn


def test_dark_mode_tokens_present() -> None:
    html = page()
    assert "prefers-color-scheme: dark" in html and ':root[data-theme="dark"]' in html


def test_demo_fixture_exercises_v02_features() -> None:
    doc = json.loads(DEMO.read_text(encoding="utf-8"))
    meta = doc["meta"]
    assert "qa" in meta["statuses"]
    assert meta["status_labels"]["qa"] == "QA" and meta["status_roles"]["qa"] == "review"
    assert meta["status_from"]["qa"] == ["review"]
    assert meta["removed"] and meta["removed"][0]["ticket"]["id"]
    assert meta["unlock_log"] and all("date" in e and "event" in e for e in meta["unlock_log"])
    tickets = {t["id"]: t for t in doc["tickets"]}
    assert any("claimed_by" in t for t in tickets.values())
    assert any(t.get("item_checks") for t in tickets.values())
    assert any(t["status"] == "qa" for t in tickets.values())
    assert "Forge" not in DEMO.read_text(encoding="utf-8")


def test_every_page_write_carries_the_saved_name() -> None:
    """Bug (0.2.1): 'Take' claimed with the viewer's name, but moves were sent without it, so the
    server used the git branch and refused the viewer's own move. Every write must go through
    api(), which adds the saved name as "as"; /api/allowed must carry it too."""
    js = script()
    # no POST to the API outside api()
    posts = [m.start() for m in re.finditer(r'method:\s*"POST"', js)]
    assert len(posts) == 1, "only api() may POST to the board server"
    assert re.search(r"function api\(path, body\)[\s\S]{0,400}JSON\.stringify\(withActor\(body\)\)", js)
    assert re.search(r"function withActor\(body\)[\s\S]{0,300}myName\(\)[\s\S]{0,200}\.as = n", js)
    # /api/allowed is only fetched through allowedUrl(), which appends &as=<name>
    assert "getJson(allowedUrl(" in js
    assert re.search(r'function allowedUrl\(id\)[\s\S]{0,200}"&as=" \+ encodeURIComponent\(n\)', js)
    assert js.count("./api/allowed?id=") == 1
    # every write endpoint the page uses goes through api("…")
    for endpoint in ("set", "claim", "release", "usertest", "note", "promote"):
        assert f'api("{endpoint}"' in js, endpoint
    assert re.search(r'api\(path, \{ id: t\.id, kind: kind, index: i \}\)', js)  # check-item / uncheck-item


# --------------------------------------------------------------------------- 0.3: Cancelled + state flags


def fn_body(js: str, name: str) -> str:
    m = re.search(r"function " + name + r"\([^)]*\) \{\n([\s\S]*?)\n\}\n", js)
    assert m, name
    return m.group(1)


def test_state_flags_from_info_with_role_defaults_and_meta_overrides() -> None:
    js = script()
    assert re.search(r'var DEFAULT_STATUSES = \[[^\]]*"done", "cancelled"\]', js), "Cancelled sits after Done"
    assert re.search(r'var FLAG_KEYS = \["resolves_deps", "from_any", "progress", "terminal", "notify_dependents", "folded"\]', js)
    rf = fn_body(js, "roleFlags")
    assert 'role === "done"' in rf and 'role === "cancelled"' in rf
    assert re.search(r'role === "cancelled"\) return \{ resolves_deps: true, from_any: true, progress: "excluded", '
                     r'terminal: true, notify_dependents: true, folded: true \}', rf)
    assert re.search(r'role === "done"\) return \{ resolves_deps: true, from_any: false, progress: "done", terminal: true', rf)
    fo = fn_body(js, "flagsOf")
    assert "liveStatusInfo(st)" in fo and "info.flags" in fo and "state.statusFlags[st]" in fo
    assert "state.statusFlags = objOr(meta.status_flags)" in js


def test_folded_columns_start_folded_and_toggle() -> None:
    js = script()
    assert "flagsOf(st).folded" in js and "state.colFold" in js
    assert '" folded"' in js and "toggleFold" in js
    assert ".col.folded" in page() and "writing-mode: vertical-rl" in page()


def test_cancelled_cards_drawer_and_actions() -> None:
    js, html = script(), page()
    assert re.search(r"function isCancelled\(t\) \{[^}]*isExcludedStatus\(statusOf\(t\)\)", js)
    assert re.search(r'f\.terminal && f\.progress === "excluded"', js)
    assert '" is-cancelled"' in js and ".card.is-cancelled .title { text-decoration: line-through" in html
    assert 'el("span", "badge b-cancel", labelStatus(statusOf(t)).toLowerCase())' in js
    # drawer: banner with the reason from the last history note, Undo cancel, Cancel ticket…
    assert "function cancelReason(t)" in js and "cancelledNotice(t)" in js
    assert '"Undo cancel"' in js and "Cancel ticket…" in js
    assert 'api("cancel", { id: t.id, reason: reason })' in js
    assert 'api("uncancel", body)' in js and "body.keep_dependents = true" in js
    assert "Keep dependents as they are" in js and "keep[-_]dependents" in js
    assert "t.cancelled_from" in js
    # view only: the cancel is a local change copied as a board.py cancel command
    assert '" cancel " + shq(mv.id) + " --reason " + note' in js
    assert '" uncancel " + shq(mv.id)' in js and '" --handoff " + note' in js


def test_from_any_states_never_greyed_and_always_ask_for_a_note() -> None:
    js = script()
    mr = fn_body(js, "moveReason")
    assert mr.lstrip().startswith("// A state reachable from any state") and "if (flagsOf(st).from_any) return null;" in mr
    assert "!flagsOf(s).from_any" in fn_body(js, "localAllowed")
    assert "if (flagsOf(st).from_any) return true;" in fn_body(js, "noteRequired")


def test_excluded_progress_text_format() -> None:
    js = script()
    ps = fn_body(js, "progressSummary")
    assert 'done + "/" + total + " done"' in ps
    assert '" · " + excl[st] + " " + labelStatus(st).toLowerCase()' in ps
    assert 'if (p === "excluded")' in ps
    assert "progressSummary(all)" in js and "progressSummary(saved)" in js


def test_resolves_deps_and_dep_exceptions_drive_blocked_by() -> None:
    js = script()
    dr = fn_body(js, "depResolved")
    assert "flagsNow(dep).resolves_deps" in dr and "depException(t, d)" in dr
    assert "dep_exceptions" in fn_body(js, "depException")
    assert "!depResolved(t, d)" in fn_body(js, "openDeps")
    assert "showsBlocked(t)" in fn_body(js, "cardChips")
    assert "isTerminal(t)" in fn_body(js, "isReady"), "finished tickets are never ready"


def test_demo_fixture_exercises_v03_cancelled() -> None:
    doc = json.loads(DEMO.read_text(encoding="utf-8"))
    meta = doc["meta"]
    assert meta["schema_version"] == 3
    sts = meta["statuses"]
    assert sts.index("cancelled") == sts.index("done") + 1
    assert meta["status_roles"]["wontfix"] == "cancelled" and meta["status_labels"]["wontfix"] == "Won't fix"
    assert isinstance(meta["status_flags"], dict)
    tickets = {t["id"]: t for t in doc["tickets"]}
    done_like = {"done", "cancelled", "wontfix"}
    cancelled = [t for t in tickets.values() if t["status"] == "cancelled"]
    assert cancelled and cancelled[0]["cancelled_from"]
    cid = cancelled[0]["id"]
    dependents = [t for t in tickets.values() if cid in t["depends_on"]]
    assert dependents, "a cancelled ticket with a dependent"
    # that dependent is unblocked: every dependency is done or cancelled
    assert any(all(tickets[d]["status"] in done_like for d in t["depends_on"]) for t in dependents)
    assert any(t["status"] == "wontfix" for t in tickets.values())
    assert any(t.get("dep_exceptions") for t in tickets.values())
