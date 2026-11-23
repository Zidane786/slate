// OpenCode splits shell commands before permission.evaluate, so a chained unlock arrives as
// several resources while execute.after still sees the full command and cannot activate it.
import test from "node:test"
import assert from "node:assert/strict"
import { chainedUnlock, CHAIN_MESSAGE } from "../plugins/slate/opencode/index.js"

test("an unlock inside split shell resources is refused with the plain-command fix", () => {
  const resources = ["echo hi", "python3 kanban/board.py unlock --reason x --minutes 5"]
  assert.equal(chainedUnlock(resources), true)
  assert.match(CHAIN_MESSAGE, /on its own/)
  assert.match(CHAIN_MESSAGE, /no &&/)
})

test("a plain unlock is not treated as a chained command", () => {
  assert.equal(chainedUnlock(["python3 kanban/board.py unlock --reason x --minutes 5"]), false)
  assert.equal(chainedUnlock([]), false)
  assert.equal(chainedUnlock(undefined), false)
})
