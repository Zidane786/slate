// OpenCode cannot distinguish a human card click from opencode run --auto's automatic reply,
// so an agent-run unlock is refused and the typed-code path is the only activation.
import test from "node:test"
import assert from "node:assert/strict"
import { unlockDecision } from "../plugins/slate/opencode/index.js"

test("an unlock ask becomes a denial naming the typed-code fallback", () => {
  const out = unlockDecision({ action: "ask", reason: "Slate: allow ONE direct edit (within 5 minutes)?" })
  assert.equal(out.action, "deny")
  assert.match(out.reason, /ONE direct edit/)
  assert.match(out.reason, /own terminal/)
  assert.match(out.reason, /type the code/)
  assert.match(out.reason, /python3 kanban\/board\.py unlock/)
})

test("ordinary allow and deny decisions pass through unchanged", () => {
  assert.deepEqual(unlockDecision({ action: "allow" }), { action: "allow" })
  assert.deepEqual(unlockDecision({ action: "deny", reason: "no" }), { action: "deny", reason: "no" })
})
