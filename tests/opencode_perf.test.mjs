// Behaviour tests for Slate's OpenCode hook startup/cache. Run with: node --test tests/opencode_perf.test.mjs
import test from "node:test"
import assert from "node:assert/strict"
import { detectPython, makeStatusLine } from "../plugins/slate/opencode/index.js"

test("Windows probes py -3 first, other platforms probe python3 first", () => {
  const calls = []
  const runner = (cmd, args) => {
    calls.push([cmd, ...args])
    return { status: 0, stdout: "True\n" }
  }
  assert.deepEqual(detectPython("win32", runner), ["py", "-3"])
  assert.deepEqual(calls[0].slice(0, 2), ["py", "-3"])
  calls.length = 0
  assert.deepEqual(detectPython("darwin", runner), ["python3"])
  assert.deepEqual(calls[0].slice(0, 1), ["python3"])
})

test("interpreter detection falls through to the next candidate", () => {
  const tried = []
  const runner = (cmd) => {
    tried.push(cmd)
    return { status: cmd === "python3" ? 1 : 0, stdout: cmd === "python3" ? "" : "True\n" }
  }
  assert.deepEqual(detectPython("darwin", runner), ["python"])
  assert.deepEqual(tried, ["python3", "python"])
})

test("the status line is cached for 30 seconds and rebuilt after that", () => {
  const calls = []
  const runner = (cmd, args) => {
    calls.push([cmd, ...args])
    return { status: 0, stdout: "Slate 0.5.0: T-1 ready\n" }
  }
  const status = makeStatusLine(runner, 30000, () => true)
  assert.equal(status("/project", ["python3"], 1000), "Slate 0.5.0: T-1 ready")
  assert.equal(status("/project", ["python3"], 2000), "Slate 0.5.0: T-1 ready")
  assert.equal(calls.length, 1)
  assert.equal(status("/project", ["python3"], 31001), "Slate 0.5.0: T-1 ready")
  assert.equal(calls.length, 2)
  assert.ok(calls[0].includes("next") && calls[0].includes("--brief"))
})
