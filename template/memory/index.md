# Memory index

This is the table of contents for my agent memory. Read this file first,
then open only the files that matter for the task. Do not load everything.
Every file below is an example. Replace them with your own.

## Always relevant
- [me/preferences.md](me/preferences.md): how I like answers, tone and format
- [me/writing-style.md](me/writing-style.md): rules for anything drafted in my name

## Work practices (open when the task touches the topic)
- [work/code-review.md](work/code-review.md): what I check in a review, conventions
- [work/releases.md](work/releases.md): release checklist and versioning
- [work/terraform.md](work/terraform.md): Terraform conventions and known pitfalls

## Clients and repos
- When you work inside a mapped repo, its context and its client's context are already
  injected at session start. You do not need to look for them.
- [clients/](clients/): one folder per client or project group. Open another client's folder
  only if the task is explicitly about that client. Never copy client details anywhere else.

## Notes while working
- General notes: append one dated line to [scratch/notes.md](scratch/notes.md).
- Repo updates: append one dated line to the repo's inbox (its path is in the injected context).
- The nightly cycle curates both. Do not edit other memory files directly.
