# Client folders

One folder per client, created when you add a client in `somna ui` (Repos tab) or with
`somna client <id> --name "<Name>" --markers "<word>,<word>"`.

    memory/clients/<client>/context.md          the engagement: scope, constraints, decisions, roles
    memory/clients/<client>/repos/<repo>.md     one context file per repo, injected at session start

Rules:
- Only what is needed to do the work. No credentials, account numbers or personal data.
- Nothing from one client is ever written into another client's folder or into general memory.
- Every cycle reads and writes one client at a time, so this is enforced, not just asked for.
- These folders never leave this Mac: a pre-push hook blocks pushing them.
- `example/` shows the shape. Delete it once you have real clients.
