# Slate

Plan ideas into plain-language tickets on a kanban board in your repo, then build them one at
a time with tests, review, your own check and the commit/PR recorded on the ticket. You stay
in charge: Claude builds one ticket per request and stops.

| Command | What it does |
|---|---|
| `/slate:init` | Set Slate up in this repo: `kanban/` board + `SLATE.md` (project context) |
| `/slate:plan [idea]` | Brainstorm into tickets: story → flow picture → phases → cards → board preview → save as ready or draft |
| `/slate:work [ID]` | Build one ticket end to end, then stop |
| `/slate:review [ID]` | Re-run the review step on the current changes |
| `/slate:status` | Progress, in flight, waiting for you to test, drafts, next |
| `/slate:upgrade` | Update this project's board to the plugin's version |

Open the board: `cd kanban && python3 -m http.server 8088`, then http://localhost:8088.

Full docs, design and source: https://github.com/Zidane786/slate · Changes: [CHANGELOG.md](CHANGELOG.md)
