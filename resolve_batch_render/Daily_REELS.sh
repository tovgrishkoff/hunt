#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

SERVICE_NAME="reels-autopost"
YT_SERVICE_NAME="yt-autopost"
YT_COMMENTS_SERVICE_NAME="yt-comments"
COMPOSE_FILE="docker-compose.autopost.yml"

echo "== resolve_batch_render daily check =="
echo "time: $(date -Is)"
echo "dir : $PROJECT_DIR"
echo

# --- docker / compose presence
if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker not found"
  exit 2
fi

if ! command -v docker-compose >/dev/null 2>&1; then
  echo "ERROR: docker-compose not found"
  exit 2
fi

# Load .env early (no secrets printed) — needed for IG/Notion checks and yt-comments dry-run hint.
ENV_FILE="$PROJECT_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set +u
  source "$ENV_FILE"
  set -u
fi

# --- container status
echo "[1] Container status"
docker ps -a --filter "name=^/${SERVICE_NAME}$" --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' || true
docker ps -a --filter "name=^/${YT_SERVICE_NAME}$" --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' || true
docker ps -a --filter "name=^/${YT_COMMENTS_SERVICE_NAME}$" --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' || true
echo

for svc in "$SERVICE_NAME" "$YT_SERVICE_NAME"; do
  running="$(docker inspect -f '{{.State.Running}}' "$svc" 2>/dev/null || echo "false")"
  if [[ "$running" != "true" ]]; then
    echo "ERROR: $svc is not running"
    echo "Hint: docker-compose -f $COMPOSE_FILE up -d --build"
    exit 3
  fi
done

echo "[1b] YouTube comment auto-reply ($YT_COMMENTS_SERVICE_NAME)"
comments_running="$(docker inspect -f '{{.State.Running}}' "$YT_COMMENTS_SERVICE_NAME" 2>/dev/null || echo "false")"
if [[ "$comments_running" != "true" ]]; then
  echo "  WARN: $YT_COMMENTS_SERVICE_NAME is not running (optional)."
  echo "  Hint: docker-compose -f $COMPOSE_FILE --profile comments up -d $YT_COMMENTS_SERVICE_NAME"
else
  echo "  OK: container is running"
  case "${YT_COMMENTS_DRY_RUN:-}" in
    1|[Tt][Rr][Uu][Ee]|[Yy][Ee][Ss]|[Oo][Nn])
      echo "  WARN: YT_COMMENTS_DRY_RUN=${YT_COMMENTS_DRY_RUN:-} — replies are not posted to YouTube."
      ;;
    *)
      echo "  Config: YT_COMMENTS_DRY_RUN=${YT_COMMENTS_DRY_RUN:-<unset>} (use 0 for live replies)"
      ;;
  esac
  echo "  Recent log lines (tail /app/app.log, filter [yt-comments]):"
  yt_log="$(docker exec "$YT_COMMENTS_SERVICE_NAME" sh -c \
    'tail -n 800 /app/app.log 2>/dev/null | grep -F "[yt-comments]" | tail -n 12' \
    2>/dev/null || true)"
  if [[ -n "$yt_log" ]]; then
    echo "$yt_log" | sed 's/^/    /'
  else
    echo "    (no [yt-comments] lines in last 800 log rows)"
  fi
  if echo "$yt_log" | grep -qE 'tick failed|invalid_grant|RefreshError'; then
    echo "  ERROR: YouTube OAuth token expired/revoked — comment replies are NOT posted."
    echo "  Fix: re-authorize (see uploader/README.md § YouTube comment auto-reply):"
    echo "    rm -f youtube_shorts_uploader/token_comments.json"
    echo "    docker-compose -f $COMPOSE_FILE --profile comments run --rm \\"
    echo "      -e YT_OAUTH_PORT=8765 -e YT_OAUTH_BIND=0.0.0.0 -p 8765:8765 \\"
    echo "      $YT_COMMENTS_SERVICE_NAME python -m uploader.yt_comments.main oauth"
    echo "    (from your PC: ssh -L 8765:localhost:8765 user@server, then open the printed URL)"
  elif echo "$yt_log" | tail -n 1 | grep -q 'tick failed'; then
    echo "  WARN: last yt-comments tick failed — check full traceback in app.log"
  fi
fi
echo

echo "[2] Container processes (docker top)"
echo "--- $SERVICE_NAME ---"
docker top "$SERVICE_NAME" || true
echo "--- $YT_SERVICE_NAME ---"
docker top "$YT_SERVICE_NAME" || true
if [[ "$comments_running" == "true" ]]; then
  echo "--- $YT_COMMENTS_SERVICE_NAME ---"
  docker top "$YT_COMMENTS_SERVICE_NAME" || true
fi
echo

# --- queue summary (inside container)
echo "[3] Queue summary (inside container)"
docker exec "$SERVICE_NAME" python -m uploader.main --tz Asia/Makassar daily-report || true
echo

# --- quick connectivity checks (best-effort); .env already sourced above

echo "[4] Network checks"
echo "- Docker DNS/egress:"
docker exec -i "$SERVICE_NAME" python - <<'PY' || true
import socket, ssl, urllib.request

def check(host: str, port: int = 443, timeout: float = 8.0) -> str:
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        ctx = ssl.create_default_context()
        ssock = ctx.wrap_socket(sock, server_hostname=host)
        ssock.close()
        return "OK"
    except Exception as e:
        return f"FAIL ({type(e).__name__}: {e})"

for h in ["graph.instagram.com", "api.notion.com"]:
    print(f"  - tls {h}: {check(h)}")
PY

echo
echo "- Instagram Graph token check (if IG_ACCESS_TOKEN present):"
if [[ "${IG_ACCESS_TOKEN:-}" != "" ]]; then
  # do not print token
  docker exec -i "$SERVICE_NAME" python - <<'PY' || true
import os, json, urllib.request

token = os.environ.get("IG_ACCESS_TOKEN","").strip()
url = "https://graph.instagram.com/me?fields=id&access_token=" + token
try:
    with urllib.request.urlopen(url, timeout=10) as r:
        data = r.read().decode("utf-8","ignore")
    print("  OK: /me reachable, response:", data[:200].replace("\n"," "))
except Exception as e:
    print("  FAIL:", type(e).__name__, e)
PY
else
  echo "  SKIP: IG_ACCESS_TOKEN is empty"
fi

echo
echo "- Notion token check (if NOTION_TOKEN present):"
if [[ "${NOTION_TOKEN:-}" != "" ]]; then
  docker exec -i "$SERVICE_NAME" python - <<'PY' || true
import os, json, urllib.request

token = os.environ.get("NOTION_TOKEN","").strip()
req = urllib.request.Request("https://api.notion.com/v1/users/me")
req.add_header("Authorization", f"Bearer {token}")
req.add_header("Notion-Version", os.environ.get("NOTION_VERSION","2022-06-28"))
try:
    with urllib.request.urlopen(req, timeout=10) as r:
        data = r.read().decode("utf-8","ignore")
    print("  OK: notion users/me reachable, response:", data[:200].replace("\n"," "))
except Exception as e:
    print("  FAIL:", type(e).__name__, e)
PY
else
  echo "  SKIP: NOTION_TOKEN is empty"
fi

echo
echo "[5] Next post per platform"

# ANSI colors (auto-disable when not a TTY)
if [[ -t 1 ]]; then
  C_RESET=$'\033[0m'
  C_BOLD=$'\033[1m'
  C_DIM=$'\033[2m'
  C_RED=$'\033[31m'
  C_YEL=$'\033[33m'
  C_GRN=$'\033[32m'
  C_CYN=$'\033[36m'
  C_MAG=$'\033[35m'
else
  C_RESET=""; C_BOLD=""; C_DIM=""; C_RED=""; C_YEL=""; C_GRN=""; C_CYN=""; C_MAG=""
fi

format_eta() {
  local mins="$1"
  if [[ "$mins" == "-" || -z "$mins" ]]; then
    printf "%s" "—"
    return
  fi
  if (( mins < 0 )); then
    local ago=$(( -mins ))
    if   (( ago < 60 ));   then printf "%s" "${ago}m ago"
    elif (( ago < 1440 )); then printf "%dh %02dm ago" $((ago/60)) $((ago%60))
    else printf "%dd %02dh ago" $((ago/1440)) $(((ago%1440)/60))
    fi
    return
  fi
  if   (( mins < 60 ));   then printf "in %dm" "$mins"
  elif (( mins < 1440 )); then printf "in %dh %02dm" $((mins/60)) $((mins%60))
  else printf "in %dd %02dh" $((mins/1440)) $(((mins%1440)/60))
  fi
}

color_for_eta() {
  local mins="$1"
  if [[ "$mins" == "-" || -z "$mins" ]]; then printf "%s" "$C_DIM"; return; fi
  if (( mins < 0 ));   then printf "%s" "$C_RED";    return; fi
  if (( mins <= 30 )); then printf "%s" "$C_YEL";    return; fi
  if (( mins <= 240 ));then printf "%s" "$C_GRN";    return; fi
  printf "%s" "$C_CYN"
}

while IFS=$'\t' read -r plat sched rid mins; do
  case "$plat" in
    instagram) plat_disp="${C_MAG}INSTAGRAM${C_RESET}" ;;
    youtube)   plat_disp="${C_RED}YOUTUBE${C_RESET}"   ;;
    pinterest) plat_disp="${C_RED}PINTEREST${C_RESET}" ;;
    *)         plat_disp="${plat}"                     ;;
  esac
  if [[ "$sched" == "NONE" ]]; then
    printf "  %-30b %sno upcoming posts%s\n" "$plat_disp" "$C_DIM" "$C_RESET"
    continue
  fi
  eta_color="$(color_for_eta "$mins")"
  eta_str="$(format_eta "$mins")"
  printf "  %-30b %s%-25s%s  %s%s%s  %s%s%s\n" \
    "$plat_disp" \
    "$C_BOLD" "$sched" "$C_RESET" \
    "$C_BOLD" "$rid" "$C_RESET" \
    "$eta_color" "$eta_str" "$C_RESET"
done < <(docker exec "$SERVICE_NAME" python -m uploader.main --tz Asia/Makassar next-due-summary 2>/dev/null || true)

echo
echo "DONE: basic checks finished."