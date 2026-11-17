#!/usr/bin/env bash
# Mouse selection in a Lucy tmux session copies to the clipboard and says
# "copied". Key bindings are server-wide, so the binding checks the session's
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
    if-shell -F "#{@lucy_copy}" "${pipe} ; display-message copied" "send-keys -X copy-pipe-and-cancel"
done
