// Behaviour tests for Slate's OpenCode context hook. Run with: node --test tests/opencode_context.test.mjs
import test from "node:test"
import assert from "node:assert/strict"
import { composeSystemText } from "../plugins/slate/opencode/index.js"

test("the Slate line is composed into the existing system text, not a new part", () => {
  const system = [
    { type: "text", text: "Host base rules" },
    { type: "text", text: "Second host part" },
  ]
  composeSystemText(system, "Slate board: T-1 ready")
  assert.equal(system.length, 1)
  assert.equal(system[0].type, "text")
  assert.equal(system[0].text, "Host base rules\n\nSecond host part\n\nSlate board: T-1 ready")
})

test("the Slate line works when no system parts exist yet", () => {
  const system = []
  composeSystemText(system, "Slate board: nothing ready")
  assert.deepEqual(system, [{ type: "text", text: "Slate board: nothing ready" }])
})
