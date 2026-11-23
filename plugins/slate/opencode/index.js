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

function python() {
  for (const candidate of ["python3", "python", "py"]) {
    const probe = spawnSync(candidate, ["-c", "import sys; print(sys.version_info >= (3, 9))"],
                            { encoding: "utf8", timeout: 5000 })
    if (probe.status === 0 && probe.stdout.trim() === "True") return candidate
  }
  return null
}

function guard(payload, post = false) {
  const py = python()
  if (!py || !existsSync(GUARD)) return ALLOW
  const args = [GUARD, "--opencode"]
  if (post) args.push("--post")
  try {
    const r = spawnSync(py, args, {
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

function statusLine(project) {
  const py = python()
  const script = join(project, BOARD)
  if (!py || !existsSync(script)) return ""
  try {
    const r = spawnSync(py, [script, "next", "--brief", "--against", HERE], {
      cwd: project, encoding: "utf8", timeout: 9000, env: process.env,
    })
    return r.status === 0 ? (r.stdout || "").trim() : ""
  } catch (e) {
    return ""
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

    // The one-line board hint that Claude Code/Copilot get from SessionStart.
    await ctx.session.hook("context", async (event) => {
      const line = statusLine(project)
      if (line) composeSystemText(event.system, `Slate board: ${line}`)
    })

    // The same guard, through OpenCode's permission decisions.
    await ctx.permission.hook("evaluate", async (event) => {
      const action = event.action
      if (action !== "edit" && action !== "write" && action !== "shell") return
      const resources = Array.isArray(event.resources) ? event.resources.map(String) : []
      if (!resources.length) return

      if (action === "shell") {
        let verdict = ALLOW
        for (const command of resources) {
          const d = guard({ tool: "shell", cwd: project, command })
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
      const d = guard({ tool: "edit", cwd: project, resources })
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
      const d = guard({ tool: "shell", cwd: project, command }, true)
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
