#!/usr/bin/env bash
# Removes the schedule, the somna command and the CLAUDE.md block. Keeps your memory repo.
set -euo pipefail
MEMORY_HOME="${SOMNA_HOME:-$HOME/somna}"
PLIST="$HOME/Library/LaunchAgents/com.somna.tick.plist"
if [ -f "$PLIST" ]; then
  launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true; rm -f "$PLIST"; echo "removed schedule"
fi
UI_PLIST="$HOME/Library/LaunchAgents/com.somna.ui.plist"
if [ -f "$UI_PLIST" ]; then
  launchctl bootout "gui/$(id -u)" "$UI_PLIST" 2>/dev/null || true; rm -f "$UI_PLIST"; echo "removed review page at login"
fi
rm -f "$HOME/.local/bin/somna" && echo "removed somna command"
for l in "$HOME"/.claude/skills/*; do
  [ -L "$l" ] && case "$(readlink "$l")" in "$MEMORY_HOME"/*) rm "$l"; echo "unlinked skill $(basename "$l")";; esac
done
if [ -f "$HOME/.claude/CLAUDE.md" ]; then
  python3 - "$HOME/.claude/CLAUDE.md" << 'PY'
import re, sys
p = sys.argv[1]; t = open(p).read()
t = re.sub(r"\n*<!-- somna:begin -->.*?<!-- somna:end -->\n?", "\n", t, flags=re.S)
open(p, "w").write(t.strip() + "\n" if t.strip() else "")
PY
  echo "removed memory block from ~/.claude/CLAUDE.md"
fi
KIT_DIR="$(cd "$(dirname "$0")" && pwd)"
[ -f "$HOME/.claude/settings.json" ] && python3 "$KIT_DIR/lib/settings.py" uninstall "$HOME/.claude/settings.json" "$MEMORY_HOME"
echo "Your memory is still in $MEMORY_HOME. Delete it yourself if you want it gone."
