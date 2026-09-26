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
