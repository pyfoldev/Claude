#!/bin/bash
# Проверка синтаксиса всех GDScript (headless). Показывает файл и строку ошибок.
G=${GODOT:-/root/tools/godot/Godot_v4.3-stable_linux.x86_64}
cd "$(dirname "$0")/.."
rc=0
for f in $(find . -name "*.gd" -not -path "./.godot/*" | sort); do
  out=$($G --headless --path . --check-only --script "res://${f#./}" 2>&1 | grep -E "ERROR|error|Error" | grep -v "^Godot\|JAVA" )
  if [ -n "$out" ]; then echo "== $f"; echo "$out" | head -6; rc=1; fi
done
exit $rc
