# usage: source mkhome.sh <dir>   (fake Mac home with 3 client repos and Claude Code transcripts)
export T=$1; rm -rf $T; mkdir -p $T/home/.local/bin $T/home/.claude
export HOME=$T/home PATH=$T/home/.local/bin:/usr/bin:/bin
cp $(dirname ${BASH_SOURCE[0]})/mock_claude $HOME/.local/bin/claude; chmod +x $HOME/.local/bin/claude
mk_repo(){ # path remote
  mkdir -p "$1/envs/web" "$1/modules/net" && cd "$1" && git init -q -b main && git config user.email t@t && git config user.name t
  printf 'resource "x" "y" {}\n' > main.tf; printf 'print(1)\n' > envs/web/app.py; printf '# repo\n' > README.md
  git add -A && git commit -qm "initial" && git remote add origin "$2"; cd - >/dev/null; }
mk_repo $HOME/code/acme-shop git@github.com:acme-corp/shop.git
mk_repo $HOME/code/globex-infra git@github.com:globex/infra.git
mk_repo $HOME/code/acme-legacy git@github.com:globex/legacy-tools.git
add_session(){ # repo-path session-id text
  d=$HOME/.claude/projects/$(echo "$1" | sed 's/[^a-zA-Z0-9]/-/g'); mkdir -p "$d"
  python3 - "$d/$2.jsonl" "$1" "$2" "$3" << 'PY'
import json, sys
p, cwd, sid, text = sys.argv[1:5]
with open(p, "w") as f:
    f.write(json.dumps({"type": "user", "sessionId": sid, "cwd": cwd + "/envs/web", "timestamp": "2026-10-09T08:00:00Z", "message": {"role": "user", "content": text}}) + "\n")
    f.write(json.dumps({"type": "assistant", "sessionId": sid, "cwd": cwd, "message": {"role": "assistant", "content": [{"type": "text", "text": "ok, done"}]}}) + "\n")
PY
}
add_session $HOME/code/acme-shop a1 "fix the provider pin"
add_session $HOME/code/globex-infra b1 "add queue alarms"
add_session $HOME/code/acme-legacy c1 "clean up legacy scripts"
