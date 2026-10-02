#!/usr/bin/env bash
# Point rustup/cargo at the active Pixi env so firmware tools need no manual PATH
# or global ~/.cargo install. Sourced by Pixi activation on unix/linux.
#
# Layout:
#   $CONDA_PREFIX/cargo/bin/{rustc,cargo,elf2uf2-rs,...}
#   $CONDA_PREFIX/rustup/...

if [[ -z "${CONDA_PREFIX:-}" ]]; then
  return 0 2>/dev/null || exit 0
fi

export CARGO_HOME="${CONDA_PREFIX}/cargo"
export RUSTUP_HOME="${CONDA_PREFIX}/rustup"
export PATH="${CARGO_HOME}/bin:${CONDA_PREFIX}/bin:${PATH}"
# Prebuilt picotool needs libusb from the Pixi env (esp. on NixOS).
if [[ -d "${CONDA_PREFIX}/lib" ]]; then
  export LD_LIBRARY_PATH="${CONDA_PREFIX}/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
  # macOS uses DYLD_LIBRARY_PATH (ignored by SIP for hardened binaries, but needed otherwise).
  if [[ "$(uname)" == "Darwin" ]]; then
    export DYLD_LIBRARY_PATH="${CONDA_PREFIX}/lib${DYLD_LIBRARY_PATH:+:${DYLD_LIBRARY_PATH}}"
  fi
fi
