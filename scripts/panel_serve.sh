#!/usr/bin/env bash
# Serve the control panel: panel_serve.sh dev|preview [vite args...] [--https]
#
# --https (the launcher's HTTPS option) sets VITE_HTTPS=true, which the panel's
# vite.config.ts serves over TLS. Without cert paths in the panel's .env it uses
# certs/{cert,key}.pem and creates a self-signed pair there on first use.
# Runs from src/lucy_control_panel (the Pixi task's cwd).
set -euo pipefail

mode=$1
shift
args=()
for arg in "$@"; do
  if [[ $arg == --https ]]; then
    export VITE_HTTPS=true
  else
    args+=("$arg")
  fi
done

if [[ ${VITE_HTTPS:-} == true ]] && ! grep -qs '^VITE_SSL_CERT_PATH=' .env; then
  export VITE_SSL_CERT_PATH="$PWD/certs/cert.pem" VITE_SSL_KEY_PATH="$PWD/certs/key.pem"
  if [[ ! -f $VITE_SSL_CERT_PATH || ! -f $VITE_SSL_KEY_PATH ]]; then
    echo "Creating a self-signed certificate in $PWD/certs (browsers will ask you to accept it)"
    openssl req -x509 -newkey rsa:2048 -nodes -days 365 -subj /CN=localhost \
      -keyout "$VITE_SSL_KEY_PATH" -out "$VITE_SSL_CERT_PATH" 2>/dev/null
  fi
fi

exec yarn "$mode" ${args[@]+"${args[@]}"}
