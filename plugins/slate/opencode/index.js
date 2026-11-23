// Slate for OpenCode V2. Local plugin: copied into .opencode/plugins/slate/ by /slate:init.
// No npm dependencies: OpenCode's own JS runtime and the project's Python 3.9+ are enough.
// The guard logic lives in the SAME Python file the Claude Code and Copilot CLI hooks use;
// this file only translates OpenCode V2 hook events into its JSON dialect.
import { spawnSync } from "node:child_process"
import { existsSync, readFileSync, readdirSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const HERE = dirname(fileURLToPath(import.meta.url))
const GUARD = join(HERE, "hooks", "guard_tickets.py")
const SKILLS = join(HERE, "skills")
const BOARD = join("kanban", "board.py")
const UNLOCK = /board\.py\s+unlock\b/i
const ALLOW = { action: "allow" }
export const CHAIN_MESSAGE = ('Use: python3 kanban/board.py unlock --reason "…" --minutes 5 on its own '
                              + "(no && or ;). OpenCode splits chained commands, so they cannot be approved.")

// ShellParse splits `echo hi && board.py unlock` into several resources before evaluate, while
// execute.after still sees the whole command and cannot activate it. Refuse it at the card.
export function chainedUnlock(resources) {
  return Array.isArray(resources) && resources.length > 1 &&
    resources.some((r) => UNLOCK.test(String(r)))
}

// Compose into ONE system part: several parts break some chat templates (Plannotator #1114).
// Read the existing text first, then replace the array in place. Title generation uses a separate
// session.hook("title"), so the context hook never runs for it.
export function composeSystemText(system, text) {
  if (!Array.isArray(system) || !text) return
  const parts = system.map((part) => (part && typeof part.text === "string" ? part.text.trim() : ""))
    .filter(Boolean)
  parts.push(text)
  system.length = 0
  system.push({ type: "text", text: parts.join("\n\n") })
}

// Find the interpreter ONCE at setup, not on every hook call. Windows uses `py -3` first.
const PY_CANDIDATES = [["python3"], ["python"], ["py", "-3"]]
const PY_WINDOWS = [["py", "-3"], ["python"], ["python3"]]

export function detectPython(platform = process.platform, runner = spawnSync) {
  for (const spec of platform === "win32" ? PY_WINDOWS : PY_CANDIDATES) {
    const probe = runner(spec[0], [...spec.slice(1), "-c", "import sys; print(sys.version_info >= (3, 9))"],
                         { encoding: "utf8", timeout: 5000 })
    if (probe.status === 0 && String(probe.stdout || "").trim() === "True") return spec
  }
  return null
}

function runPython(runner, py, args, options) {
  return runner(py[0], [...py.slice(1), ...args], options)
}

function guard(payload, post, py) {
  if (!py || !existsSync(GUARD)) return ALLOW
  const args = [GUARD, "--opencode"]
  if (post) args.push("--post")
  try {
    const r = runPython(spawnSync, py, args, {
      input: JSON.stringify(payload), encoding: "utf8", timeout: 10000,
      cwd: payload.cwd || process.cwd(), env: process.env,
    })
    if (r.error || r.status !== 0 || !r.stdout) return ALLOW
    const out = JSON.parse(r.stdout)
    return out && typeof out.action === "string" ? out : ALLOW
  } catch (e) {
    return ALLOW // a guard failure must never break an unrelated tool call
  }
}

// board.py next is read-only but slow; reuse the line for ~30 seconds (a session lasts minutes).
export function makeStatusLine(runner = spawnSync, ttlMs = 30000, exists = existsSync) {
  let cached = "", cachedAt = -Infinity
  return (project, py, now = Date.now()) => {
    if (cached && now - cachedAt < ttlMs) return cached
    const script = join(project, BOARD)
    if (!py || !exists(script)) return ""
    try {
      const r = runPython(runner, py, [script, "next", "--brief", "--against", HERE], {
        cwd: project, encoding: "utf8", timeout: 9000, env: process.env,
      })
      cached = r.status === 0 ? (r.stdout || "").trim() : ""
    } catch (e) {
      cached = ""
    }
    cachedAt = now
    return cached
  }
}

function splitSkill(raw) {
  const m = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(raw)
  if (!m) return { meta: {}, body: raw }
  const meta = {}
  for (const line of m[1].split(/\r?\n/)) {
    const i = line.indexOf(":")
    if (i > 0) meta[line.slice(0, i).trim()] = line.slice(i + 1).trim().replace(/^["']|["']$/g, "")
  }
  return { meta, body: raw.slice(m[0].length) }
}

export default {
  id: "slate",
  async setup(ctx) {
    const project = (ctx.location && ctx.location.directory) || process.cwd()
    const py = detectPython()
    const statusLine = makeStatusLine()

    // The one-line board hint that Claude Code/Copilot get from SessionStart.
    await ctx.session.hook("context", async (event) => {
      const line = statusLine(project, py)
      if (line) composeSystemText(event.system, `Slate board: ${line}`)
    })

    // The same guard, through OpenCode's permission decisions.
    await ctx.permission.hook("evaluate", async (event) => {
      const action = event.action
      if (action !== "edit" && action !== "write" && action !== "shell") return
      const resources = Array.isArray(event.resources) ? event.resources.map(String) : []
      if (!resources.length) return

      if (action === "shell") {
        if (chainedUnlock(resources)) {
          event.effect = "deny"
          event.message = CHAIN_MESSAGE
          return
        }
        let verdict = ALLOW
        for (const command of resources) {
          const d = guard({ tool: "shell", cwd: project, command }, false, py)
          if (d.action === "deny") { verdict = d; break }
          if (d.action === "ask") verdict = d
        }
        if (verdict.action !== "allow") {
          event.effect = verdict.action
          event.message = verdict.reason
        }
        return
      }

      // One call for all paths of an edit, so one unlock is consumed at most once.
      const d = guard({ tool: "edit", cwd: project, resources }, false, py)
      if (d.action !== "allow") {
        event.effect = d.action
        event.message = d.reason
      }
    })

    // The approval card said yes: turn the request into a one-edit unlock.
    await ctx.tool.hook("execute.after", async (event) => {
      if (event.status !== "completed") return
      const input = event.input || {}
      const command = typeof input === "string" ? input : (input.command || "")
      if (typeof command !== "string" || !UNLOCK.test(command)) return
      const d = guard({ tool: "shell", cwd: project, command }, true, py)
      if (!d.note) return
      const sessionID = event.sessionID || input.sessionID
      if (sessionID) await ctx.session.synthetic({ sessionID, text: d.note })
      else console.log(d.note)
    })

    // Register Slate's SKILL.md files verbatim, with ROOT pointed at this plugin folder.
    // IDs are slate-* so they cannot collide with a project's own skills.
    if (existsSync(SKILLS)) {
      await ctx.skill.transform((editor) => {
        for (const entry of readdirSync(SKILLS, { withFileTypes: true })) {
          if (!entry.isDirectory()) continue
          const dir = join(SKILLS, entry.name)
          const file = join(dir, "SKILL.md")
          if (!existsSync(file)) continue
          const { meta, body } = splitSkill(readFileSync(file, "utf8"))
          // The name matches the command stubs, so "Use the slate-init skill" resolves.
          editor.add({
            id: `slate-${entry.name}`,
            name: `slate-${entry.name}`,
            description: meta.description || "Slate command",
            path: file,
            content: body.replaceAll("${CLAUDE_PLUGIN_ROOT}", HERE),
          })
        }
      })
    }
  },
}
