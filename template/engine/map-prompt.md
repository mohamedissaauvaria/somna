MAP REPO. You are mapping one repository to write its context file. This is a read-only
pass: you can only read, list and search files. Do not try to change anything.

Repository: {{REPO_PATH}}
Mapped to client: {{CLIENT_NAME}} (id {{CLIENT}}). Other known clients: {{OTHER_CLIENTS}}.

Facts collected deterministically (trust these):
{{FACTS}}

Top of the folder tree (depth 2, build and vendor folders skipped):
```
{{TREE}}
```

Client context so far:
<client_context>
{{CLIENT_CONTEXT}}
</client_context>

Existing context for this repo (update it, keep what is still true):
<existing>
{{EXISTING}}
</existing>

## Your job
1. Explore enough to understand the repo: README, entry points, build and deploy files,
   CI pipelines, infrastructure code, main modules. Prefer reading over guessing.
   Stop when you can describe it well; do not read every file.
2. Check ownership: does anything in the repo (names, domains, account aliases, README,
   remotes) point to a different client than {{CLIENT_NAME}}? Report it, do not decide.
3. Write the context in markdown, under {{MAX_CHARS}} characters, with exactly these sections:

# {{REPO_NAME}} ({{CLIENT_NAME}})
## What this repo does
## How to navigate it
(main folders and what lives where, entry points, how to build, test, plan and deploy)
## How it connects
(other repos, pipelines, cloud accounts or services it deploys to or depends on, key dependencies)
## Current state
(what the recent commits show is in progress)
## Gotchas and decisions
(only what the code, comments or docs actually show)
## Questions for the owner
(ownership doubts, unclear structure, anything a person should confirm; "- none" if none)

Rules: only facts you saw. No secrets, credentials or account numbers. Short bullets.

Your final answer must be ONLY the markdown document, starting with "# ". No preamble.
