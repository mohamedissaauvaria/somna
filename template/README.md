# My Somna memory

| Folder | What it is |
|---|---|
| `memory/` | What agents read. Start at `memory/index.md`. Clients and repo contexts in `memory/clients/`, agent notes in `memory/inbox/` and `memory/scratch/`. |
| `skills/` | Personal Claude Code skills, linked into `~/.claude/skills` |
| `engine/` | Settings: `config.json`, `steering.md`, `repos.json` (repos and clients), prompts |
| `ui/` | The local review page served by `somna ui` |
| `cycles/` | Cycle and map records, reports, diffs, run logs (local only) |
| `logs/` | `somna.log` and `somna.jsonl` (local only) |
| `bin/somna` | The somna command |

## Daily use

The easy way:

    somna ui                   open the review page (Review, Repos, History, Memory, Logs, Health)

From the terminal:

    somna list                 recent cycles, REVIEW marks the ones waiting for you
    somna review <id>          read the report and the diff
    somna adopt <id>           accept the curated memory
    somna adopt <id> --force   merge even if memory changed since the cycle started
    somna discard <id>         throw it away
    somna create --since-last  run a cycle now instead of waiting for the night
    somna repos                repos, clients and open questions
    somna map <repo>           propose a repo's context (read-only pass)
    somna logs --level warn    what went wrong recently
    somna doctor               check the setup

Every adopted cycle and every edit made in the review page is a Git commit,
so any change can be undone with `git revert`.
