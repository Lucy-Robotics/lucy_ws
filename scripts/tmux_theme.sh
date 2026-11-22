#!/usr/bin/env bash
# Lucy tmux theme, scoped to one session: the user's global tmux config is
# left untouched.
#
#   scripts/tmux_theme.sh <session>          theme a session and its windows
#   scripts/tmux_theme.sh --window <target>  theme one window (used by the hook)
#
# Window options (current tab, pane borders, copy mode) cannot be set per
# session, so each window gets them, and an after-new-window hook on the
# session covers the windows the launcher opens later.
set -euo pipefail

BG="#141414"
SECONDARY="#2b3e50"
HIGHLIGHT="#00ff41"
TEXT="#f7f1e5"

theme_window() {
  local w="$1"
  tmux set-option -w -t "$w" window-status-style "fg=${TEXT},bg=${BG}" \; \
    set-option -w -t "$w" window-status-current-style "fg=${HIGHLIGHT},bg=${SECONDARY},bold" \; \
    set-option -w -t "$w" window-status-activity-style "fg=${HIGHLIGHT},bg=${BG}" \; \
    set-option -w -t "$w" window-status-format " #I:#W " \; \
    set-option -w -t "$w" window-status-current-format " #I:#W " \; \
    set-option -w -t "$w" window-status-separator "" \; \
    set-option -w -t "$w" pane-border-style "fg=${SECONDARY}" \; \
    set-option -w -t "$w" pane-active-border-style "fg=${HIGHLIGHT}" \; \
    set-option -w -t "$w" mode-style "fg=${BG},bg=${HIGHLIGHT}"
}

if [[ "${1:-}" == "--window" ]]; then
  theme_window "$2"
  exit 0
fi

session="${1:?usage: tmux_theme.sh <session>}"
# Exact-name match ("=": lucy_ws must not match lucy_ws_1); the trailing ":"
# makes it a valid target for set-option, whose -t is a pane target.
t="=${session}:"
self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"

tmux set-option -t "$t" status-style "fg=${TEXT},bg=${BG}" \; \
  set-option -t "$t" status-left " #S " \; \
  set-option -t "$t" status-left-style "fg=${BG},bg=${HIGHLIGHT},bold" \; \
  set-option -t "$t" status-left-length 30 \; \
  set-option -t "$t" status-right " %H:%M " \; \
  set-option -t "$t" status-right-style "fg=${HIGHLIGHT},bg=${SECONDARY}" \; \
  set-option -t "$t" message-style "fg=${HIGHLIGHT},bg=${SECONDARY}" \; \
  set-option -t "$t" message-command-style "fg=${HIGHLIGHT},bg=${SECONDARY}"

tmux set-hook -t "$t" after-new-window \
  "run-shell -b \"bash '${self}' --window '#{window_id}'\""

tmux list-windows -t "$t" -F '#{window_id}' | while read -r w; do
  theme_window "$w"
done
