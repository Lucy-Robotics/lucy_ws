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
export PATH="${CARGO_HOME}/bin:${PATH}"
