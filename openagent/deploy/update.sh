#!/usr/bin/env bash
# Обновление сервера OpenAgent и ваших ботов/проектов из GitHub — без архивов.
#   openagent-update            применить новые коммиты ветки (если есть)
#   openagent-update --check    только показать, что изменилось, ничего не трогая
#   openagent-update --force    переустановить даже без новых коммитов
#   openagent-update --target X только цель X из targets.conf
#   openagent-update --status   что сейчас развёрнуто
# Настройки: /etc/openagent/deploy.env (репозиторий, ветка, токен) и /etc/openagent/targets.conf (что куда ставить). См. install-autoupdate.sh.
# Безопасность: перед заменой делается снимок цели; после перезапуска проверяется health — не ответил, откат на снимок.
set -uo pipefail
ENVF="${DEPLOY_ENV:-/etc/openagent/deploy.env}"; [ -f "$ENVF" ] && . "$ENVF"
REPO="${DEPLOY_REPO:-}"; BRANCH="${DEPLOY_BRANCH:-main}"; TOKEN="${DEPLOY_TOKEN:-}"
STATE="${DEPLOY_STATE:-/var/lib/openagent-deploy}"; TARGETS="${DEPLOY_TARGETS:-/etc/openagent/targets.conf}"
LOG="${DEPLOY_LOG:-/var/log/openagent-deploy.log}"; KEEP="${DEPLOY_KEEP_BACKUPS:-3}"
MODE=apply; ONLY=""
while [ $# -gt 0 ]; do case "$1" in --check) MODE=check;; --force) MODE=force;; --status) MODE=status;; --target) ONLY="$2"; shift;; -h|--help) sed -n 2,10p "$0"; exit 0;; *) echo "неизвестный ключ $1"; exit 2;; esac; shift; done
[ -z "$REPO" ] && { echo "Не задан DEPLOY_REPO (см. $ENVF)"; exit 2; }
mkdir -p "$STATE/backups" "$STATE/marks"; SRC="$STATE/src"; REPORT="$STATE/last-update.txt"
say() { echo "$*" | tee -a "$LOG" 2>/dev/null; echo "$*" >> "$REPORT.tmp"; }
: > "$REPORT.tmp"
exec 9>"$STATE/lock"; flock -n 9 || { echo "Обновление уже идёт"; exit 3; }

GIT=(git); [ -n "$TOKEN" ] && GIT=(git -c "http.extraheader=AUTHORIZATION: basic $(printf 'x-access-token:%s' "$TOKEN" | base64 -w0)")
say "=== $(date '+%F %T') обновление: $REPO ($BRANCH), режим $MODE"
if [ ! -d "$SRC/.git" ]; then rm -rf "$SRC"; "${GIT[@]}" clone -q --depth 100 --branch "$BRANCH" "$REPO" "$SRC" || { say "ОШИБКА: не удалось клонировать (токен/адрес/ветка?)"; mv "$REPORT.tmp" "$REPORT"; exit 1; }
else (cd "$SRC" && "${GIT[@]}" fetch -q --depth 100 origin "$BRANCH" && git reset -q --hard FETCH_HEAD) || { say "ОШИБКА: git fetch не удался"; mv "$REPORT.tmp" "$REPORT"; exit 1; }; fi
NEW=$(cd "$SRC" && git rev-parse HEAD); say "Ветка на GitHub: ${NEW:0:8} — $(cd "$SRC" && git log -1 --format=%s)"

[ -f "$TARGETS" ] || { say "ОШИБКА: нет $TARGETS (скопируйте targets.conf.example)"; mv "$REPORT.tmp" "$REPORT"; exit 2; }
FAIL=0; CHANGED=0
while IFS=$'\x01' read -r NAME SPATH TDIR CHECK PRE POST HEALTH; do
  NAME=$(echo "$NAME" | xargs); [ -z "$NAME" ] && continue; case "$NAME" in \#*) continue;; esac
  [ -n "$ONLY" ] && [ "$ONLY" != "$NAME" ] && continue
  SPATH=$(echo "$SPATH" | xargs); TDIR=$(echo "$TDIR" | xargs); CHECK=$(echo "$CHECK" | sed 's/^ *//;s/ *$//'); PRE=$(echo "$PRE" | sed 's/^ *//;s/ *$//'); POST=$(echo "$POST" | sed 's/^ *//;s/ *$//'); HEALTH=$(echo "$HEALTH" | xargs)
  MARK="$STATE/marks/$NAME"; OLD=$(cat "$MARK" 2>/dev/null || true)
  if [ "$MODE" = status ]; then say "• $NAME: развёрнут ${OLD:0:8}${OLD:+ }(цель $TDIR)"; continue; fi
  [ -d "$SRC/$SPATH" ] || { say "• $NAME: в репозитории нет папки $SPATH — пропуск"; FAIL=1; continue; }
  if [ -n "$OLD" ] && [ "$MODE" != force ]; then
    if (cd "$SRC" && git cat-file -e "$OLD^{commit}" 2>/dev/null); then
      [ -z "$(cd "$SRC" && git diff --name-only "$OLD" "$NEW" -- "$SPATH")" ] && { say "• $NAME: без изменений"; echo "$NEW" > "$MARK"; continue; }
    fi
  fi
  CHANGED=1
  say "• $NAME: есть обновление${OLD:+ (${OLD:0:8} → ${NEW:0:8})}"
  [ -n "$OLD" ] && (cd "$SRC" && git log --format='    - %s' "$OLD..$NEW" -- "$SPATH" 2>/dev/null | head -15 | tee -a "$LOG" "$REPORT.tmp")
  [ "$MODE" = check ] && continue
  # 1. проверка нового кода до замены
  if [ -n "$CHECK" ]; then (cd "$SRC/$SPATH" && bash -c "$CHECK") >>"$LOG" 2>&1 || { say "  ✗ проверка кода не прошла ($CHECK) — цель НЕ тронута. Подробности: $LOG"; FAIL=1; continue; }; say "  ✓ проверка кода прошла"; fi
  # 2. снимок
  mkdir -p "$TDIR"; SNAP="$STATE/backups/$NAME-$(date +%Y%m%d-%H%M%S).tgz"
  tar -czf "$SNAP" -C "$TDIR" --exclude=node_modules --exclude=data --exclude=workspaces . 2>/dev/null && say "  ✓ снимок: $SNAP"
  # 3. замена файлов (секреты и данные не трогаем)
  EXC=(--exclude=.env --exclude='.env.*' --exclude=data --exclude=workspaces --exclude=node_modules --exclude='*.db' --exclude='*.db-*' --exclude=.git); [ -f "$TDIR/.deployignore" ] && EXC+=(--exclude-from="$TDIR/.deployignore")
  rsync -a --delete "${EXC[@]}" "$SRC/$SPATH/" "$TDIR/" || { say "  ✗ rsync не удался"; FAIL=1; continue; }
  # 4. зависимости, перезапуск
  if [ -n "$PRE" ]; then (cd "$TDIR" && bash -c "$PRE") >>"$LOG" 2>&1 || { say "  ✗ подготовка не удалась ($PRE) — откат"; tar -xzf "$SNAP" -C "$TDIR" 2>/dev/null; FAIL=1; continue; }; fi
  if [ -n "$POST" ]; then (cd "$TDIR" && bash -c "$POST") >>"$LOG" 2>&1 || say "  ! команда перезапуска вернула ошибку ($POST)"; fi
  # 5. проверка живости
  OKH=1
  if [ -n "$HEALTH" ]; then OKH=0; for i in $(seq 1 20); do curl -fsS -m 3 "$HEALTH" >/dev/null 2>&1 && { OKH=1; break; }; sleep 2; done; fi
  if [ "$OKH" = 1 ]; then echo "$NEW" > "$MARK"; say "  ✓ $NAME обновлён до ${NEW:0:8}${HEALTH:+, health ответил}"
  else
    say "  ✗ $HEALTH не ответил за 40 с — ОТКАТ на снимок"
    RT=$(mktemp -d); tar -xzf "$SNAP" -C "$RT" && rsync -a --delete "${EXC[@]}" "$RT/" "$TDIR/"; rm -rf "$RT"
    [ -n "$PRE" ] && (cd "$TDIR" && bash -c "$PRE") >>"$LOG" 2>&1; [ -n "$POST" ] && (cd "$TDIR" && bash -c "$POST") >>"$LOG" 2>&1
    say "  ↩ откат выполнен, возвращена прошлая версия. Причина — в $LOG и journalctl"; FAIL=1
  fi
  ls -1t "$STATE/backups/$NAME-"*.tgz 2>/dev/null | tail -n +$((KEEP+1)) | xargs -r rm -f
done < <(sed 's/@@/\x01/g' "$TARGETS")

# заметки о выпуске (что сделать руками: новые ключи в .env и т. п.)
if [ "$CHANGED" = 1 ] && [ "$MODE" != status ]; then
  for f in "$SRC"/openagent/deploy/RELEASE.md "$SRC"/RELEASE.md; do [ -f "$f" ] && { say ""; say "--- заметки к выпуску (RELEASE.md) ---"; head -40 "$f" | tee -a "$LOG" "$REPORT.tmp"; break; }; done
fi
[ "$CHANGED" = 0 ] && [ "$MODE" != status ] && say "Всё актуально."
mv "$REPORT.tmp" "$REPORT"; [ "$MODE" = check ] || true
exit $FAIL
