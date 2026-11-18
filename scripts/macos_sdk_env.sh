# Pixi activation (macOS): point SDKROOT at an SDK the Pixi linker can read.
#
# conda-forge's ld64 (956.x) rejects the `arm64e.x1` architecture that the macOS 27
# SDK lists in libSystem.tbd, so every CMake compiler check fails with
# "ld: dynamic executables or dylibs must link with libSystem.dylib". Fall back to
# the newest installed SDK without it. An SDKROOT set by the user is left alone.
# shortcut: matches only `arm64e.x1`; drop this once conda-forge ships an ld64 that reads it.
if [ "$(uname)" = Darwin ] && [ -z "${SDKROOT:-}" ]; then
  _lucy_sdk="$(xcrun --show-sdk-path 2>/dev/null)"
  if [ -n "$_lucy_sdk" ] && grep -q 'arm64e\.x1' "$_lucy_sdk/usr/lib/libSystem.tbd" 2>/dev/null; then
    for _lucy_candidate in $(
      for _d in /Library/Developer/CommandLineTools/SDKs/MacOSX[0-9]*.sdk \
                /Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX[0-9]*.sdk; do
        [ -d "$_d" ] && printf '%s %s\n' "$(basename "$_d" .sdk | sed 's/^MacOSX//')" "$_d"
      done | sort -rV | cut -d' ' -f2-
    ); do
      if ! grep -q 'arm64e\.x1' "$_lucy_candidate/usr/lib/libSystem.tbd" 2>/dev/null; then
        export SDKROOT="$_lucy_candidate"
        break
      fi
    done
    [ -n "${SDKROOT:-}" ] || echo "warning: macOS SDK $_lucy_sdk is too new for the Pixi linker; install Command Line Tools for macOS 26 (xcode-select --install)" >&2
  fi
  unset _lucy_sdk _lucy_candidate _d
fi
