# Changelog

## 1.0.0 (2026-10-17)

First public release.

- Nightly and weekly cycles that curate your Markdown memory from your Claude Code sessions,
  one isolated run per client, with a review page on 127.0.0.1.
- Repo and client context injected at session start and subagent start, with a freshness check
  against the code and a correction loop.
- Decisions with confidence and evidence dates; low-confidence changes become questions.
- Adopt automatically when safe, with a morning summary and Undo.
- Reading budget for long sessions, incremental reading of resumed sessions.
- Settings page for schedule, models, limits and review mode; model list from your provider.
- Read-only memory for agents, scope guardrails, versions and redact, pre-push hook that keeps
  client folders local.
