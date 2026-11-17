#!/usr/bin/env bash
# Mouse selection in a Lucy tmux session copies to the clipboard and says how
# many chars it copied: F12 tells the launcher in the Lucy window, the status
# line says it elsewhere. Key bindings are server-wide, so the binding checks the session's
# @lucy_copy option and other sessions keep tmux's default drag-end copy.
#
#   scripts/tmux_copy.sh <session>
set -euo pipefail

session="${1:?usage: tmux_copy.sh <session>}"

clipboard=""
for command in wl-copy "xclip -selection clipboard" pbcopy; do
  if command -v "${command%% *}" >/dev/null 2>&1; then
    clipboard="$command"
    break
  fi
done

pipe="send-keys -X copy-pipe-and-cancel${clipboard:+ '${clipboard}'}"
tmux set-option -t "=${session}:" mouse on \; set-option -t "=${session}:" @lucy_copy 1
for table in copy-mode copy-mode-vi; do
  tmux bind-key -T "$table" MouseDragEnd1Pane \
    if-shell -F "#{@lucy_copy}" \
    "${pipe} ; if-shell -F '#{==:#{window_name},Lucy}' 'send-keys F12' 'display-message \"Copied #{buffer_size} chars to clipboard\"'" \
    "send-keys -X copy-pipe-and-cancel"
done
