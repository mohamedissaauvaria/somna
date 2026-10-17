# Inbox

Agents append one dated line per lasting update to `memory/inbox/<client>/<repo>.md`
while they work, for example:

    - 2026-10-09: switched remote state to S3 native locking, DynamoDB table can go

The nightly cycle merges these lines into the repo context and removes them.
Do not write here by hand unless you want the cycle to pick something up.
