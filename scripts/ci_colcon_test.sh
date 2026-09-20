#!/usr/bin/env bash
# CI-friendly colcon test: stable skips, optional thais_urdf, pytest plugin guard.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

skip=(lucy_cli lucy_config_pipeline lucy_control_supervisor)
if [ -d "src/thais_urdf" ]; then
  skip+=(thais_urdf)
fi

export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1

args=(
  test
  --return-code-on-test-failure
  --packages-skip "${skip[@]}"
)
for opt in "$@"; do
  args+=("$opt")
done

dump_failure_logs() {
  echo "::group::colcon test-result"
  colcon test-result --verbose || true
  echo "::endgroup::"

  echo "::group::Failed test logs"
  latest_test_log=""
  if [ -d log ]; then
    latest_test_log="$(find log -maxdepth 1 -type d -name 'test_*' | sort | tail -1)"
  fi
  if [ -n "$latest_test_log" ]; then
    find "$latest_test_log" -type f \( -name 'stdout.log' -o -name 'stderr.log' \) | while read -r f; do
      if grep -qE 'FAILED|ERROR|Failed|Traceback|NO TESTS RAN' "$f" 2>/dev/null; then
        echo "--- ${f} ---"
        tail -120 "$f"
      fi
    done
  fi
  for ctest_log in build/*/Testing/Temporary/LastTest.log; do
    if [ -f "$ctest_log" ] && grep -qE 'Failed|FAILED' "$ctest_log" 2>/dev/null; then
      echo "--- ${ctest_log} ---"
      tail -80 "$ctest_log"
    fi
  done
  echo "::endgroup::"
}

set +e
colcon "${args[@]}"
rc=$?
set -e

if [ "$rc" -ne 0 ]; then
  dump_failure_logs
  exit "$rc"
fi
