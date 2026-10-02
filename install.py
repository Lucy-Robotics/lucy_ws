#!/usr/bin/env python3
"""Lucy workspace setup: clone sub-repos, install RoboStack deps via Pixi, colcon build.

Single cross-platform implementation behind the Windows launcher and the
Keep behaviour changes here so no
platform drifts from the others.

Usage:
    python install.py                  clone/pull repos + pixi install + build
    python install.py --update         same as above
    python install.py --repair         wipe build/install/log, re-clone src repos, re-lock Pixi
    python install.py --build-only     skip git; pixi run build + panel-install
    python install.py --skip-build     clone/pull only (CI)

Optional .env: DEV=true uses url_ssh from the repos config.
Optional config/repos.json.local overrides config/repos.json.

Pixi must be >= LUCY_PIXI_MIN_VERSION (default 0.78.0); when it is missing or too
old install.py offers to run the official installer. LUCY_PIXI_AUTO_UPGRADE=1
skips the prompt, LUCY_SKIP_PIXI_UPGRADE=1 fails instead.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Iterable, Optional

ROOT = Path(__file__).resolve().parent

MIN_PIXI_VERSION = "0.78.0"
DEFAULT_REPOS_BRANCH = "master"
BUILD_ARTIFACT_DIRS = ("build", "install", "log")

PIXI_INSTALL_URL_POSIX = "https://pixi.sh/install.sh"
PIXI_INSTALL_URL_WINDOWS = "https://pixi.sh/install.ps1"

REQUIREMENT_DOCS = {
    "python": ("Python 3", "https://www.python.org/downloads/"),
    "git": ("Git", "https://git-scm.com/downloads"),
    "pixi": ("Pixi", "https://pixi.prefix.dev/latest/installation/"),
    "msvc": ("Visual Studio Build Tools (Desktop development with C++)",
             "https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2022"),
    "workspace-path": ("Workspace path without spaces", ""),
    "nix-ld": (" REQUIREMENT, MANUAL ACTION REQUIRED:\nPlease enable `programs.nix-ld.enable = true;` in your NixOS configuration and rebuild your system before continuing. See README.md for details."),
}

InstallMode = str  # "install" | "update" | "repair" | "build-only"

Log = Callable[[str], None]


class PrerequisiteError(Exception):
    """Raised when required prerequisites are missing."""

    def __init__(self, issues: list[dict]):
        self.issues = issues
        super().__init__("\n".join(format_issue(i) for i in issues))


class NixLdError(Exception):
    """Raised when nix-ld is not enabled in a NixOS environment."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def requirement_issue(req_id: str, detail: str) -> dict:
    name, url = REQUIREMENT_DOCS[req_id]
    return {"id": req_id, "name": name, "url": url, "detail": detail}


def format_issue(issue: dict) -> str:
    if issue.get("url"):
        return f"Missing {issue['name']}. Install it: {issue['url']}"
    return f"{issue['name']}: {issue.get('detail', '')}"


def fail(req_id: str, detail: str):
    """
    Raise a PrerequisiteError for a single missing requirement, with a formatted message.

    Ensure the requirement ID is in REQUIREMENT_DOCS, and provide a detail message explaining the issue.
    """
    raise PrerequisiteError([requirement_issue(req_id, detail)])


# --- shell helpers -----------------------------------------------------------


def env_flag(name: str, env: Optional[dict] = None) -> bool:
    source = os.environ if env is None else env
    return str(source.get(name, "")).strip().lower() in ("1", "true", "yes")


def default_run_command(command: list[str], check: bool = True, cwd: Optional[str] = None) -> int:
    print(f"--- Running: {' '.join(command)} ---", flush=True)
    code = subprocess.run(command, cwd=cwd, check=False).returncode
    if check and code != 0:
        raise subprocess.CalledProcessError(code, command)
    return code


def run_quiet(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def command_ok(cmd: list[str]) -> bool:
    try:
        return run_quiet(cmd).returncode == 0
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False


def clean_str(value) -> str:
    return str(value or "").strip().strip("\r\n")


def safe_rmtree(path: Path | str) -> None:
    path = Path(path)
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        path.unlink()


def load_dotenv(root: Path, env: Optional[dict] = None) -> dict:
    """Load <root>/.env without overriding real environment variables."""
    target = os.environ if env is None else env
    path = Path(root) / ".env"
    if not path.is_file():
        return target

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip().removeprefix("export ").strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key, value = key.strip(), value.strip().strip("\r")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key and key not in target:
            target[key] = value
    return target


# --- repos manifest ----------------------------------------------------------


def repos_config_path(project_root: Path | str) -> Path:
    root = Path(project_root)
    local = root / "config" / "repos.json.local"
    return local if local.exists() else root / "config" / "repos.json"


def parse_repos(
    project_root: Path | str,
    developer: Optional[bool] = None,
    repos_branch: Optional[str] = None,
) -> list[dict]:
    """Read the manifest into {name, branch, url, optional} rows."""
    if developer is None:
        developer = env_flag("DEV")

    with open(repos_config_path(project_root), "r", encoding="utf-8") as f:
        data = json.load(f)

    repos = []
    for repo in data.get("repos", []):
        name = clean_str(repo.get("name"))
        if not name:
            continue
        https = clean_str(repo.get("url_https") or repo.get("url"))
        ssh = clean_str(repo.get("url_ssh"))
        url = (ssh or https) if developer else (https or ssh)
        if url:
            repos.append({
                "name": name,
                "branch": clean_str(repo.get("branch")) or repos_branch or DEFAULT_REPOS_BRANCH,
                "url": url,
                "optional": bool(repo.get("optional")),
            })
    return repos


def mark_optional_colcon_ignore(
    project_root: Path | str,
    repos: Optional[Iterable[dict]] = None,
    log: Log = print,
) -> list[str]:
    """COLCON_IGNORE each optional repo so colcon skips it (LUCY_BUILD_OPTIONAL=1 builds them)."""
    if env_flag("LUCY_BUILD_OPTIONAL"):
        return []

    root = Path(project_root)
    repos = parse_repos(root) if repos is None else repos

    ignored = []
    for repo in repos:
        repo_dir = root / "src" / repo["name"]
        if not repo.get("optional") or not repo_dir.is_dir():
            continue
        log(f"install: skipping optional repo {repo['name']} (set LUCY_BUILD_OPTIONAL=1 to build)")
        (repo_dir / "COLCON_IGNORE").touch()
        ignored.append(repo["name"])
    return ignored


# --- prerequisites -----------------------------------------------------------


def git_available() -> bool:
    return command_ok(["git", "--version"])


def python_available() -> bool:
    return command_ok([sys.executable, "--version"])


def pixi_available() -> bool:
    return shutil.which("pixi") is not None


def pixi_version() -> str:
    if not pixi_available():
        return ""
    try:
        result = run_quiet(["pixi", "--version"])
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return ""
    parts = result.stdout.strip().split() if result.returncode == 0 else []
    return parts[1] if len(parts) >= 2 else ""


def version_at_least(version: str, minimum: str) -> bool:
    def parse(v: str) -> list[int]:
        out = []
        for piece in v.split("."):
            if not piece.isdigit():
                break
            out.append(int(piece))
        return out

    cur, minv = parse(version), parse(minimum)
    for i in range(max(len(cur), len(minv))):
        c, m = (cur[i] if i < len(cur) else 0), (minv[i] if i < len(minv) else 0)
        if c != m:
            return c > m
    return True


def min_pixi_version() -> str:
    return os.environ.get("LUCY_PIXI_MIN_VERSION", MIN_PIXI_VERSION)


def pixi_version_ok() -> bool:
    version = pixi_version()
    return bool(version) and version_at_least(version, min_pixi_version())


def git_identity_warnings() -> list[str]:
    return [
        f"Git {key} is not set (needed only if you commit changes)."
        for key in ("user.name", "user.email")
        if not run_quiet(["git", "config", "--global", key]).stdout.strip()
    ]


def workspace_path_issue(project_root: Path | str) -> Optional[dict]:
    """Console-script shims pass the interpreter path to CreateProcess unquoted,
    so every entry point in the Pixi env fails from a path containing a space."""
    path = Path(project_root).resolve()
    if sys.platform != "win32" or " " not in str(path):
        return None
    return requirement_issue(
        "workspace-path",
        f"'{path}' contains a space. Pixi console scripts (colcon, pytest, ROS 2 nodes) "
        "cannot run from such a path on Windows. Move the workspace somewhere like "
        "%LOCALAPPDATA%\\Programs\\Lucy.",
    )


VC_TOOLS_COMPONENT = "Microsoft.VisualStudio.Component.VC.Tools.x86.x64"


def find_vcvars() -> Optional[Path]:
    """Locate vcvars64.bat for the newest VS install carrying the C++ toolchain."""
    if sys.platform != "win32":
        return None
    program_files = os.environ.get("ProgramFiles(x86)") or os.environ.get("ProgramFiles", "")
    vswhere = Path(program_files) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if not vswhere.is_file():
        return None

    found = run_quiet([
        str(vswhere), "-latest", "-products", "*",
        "-requires", VC_TOOLS_COMPONENT,
        "-property", "installationPath", "-format", "value",
    ]).stdout.strip().splitlines()
    if not found:
        return None
    vcvars = Path(found[0]) / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
    return vcvars if vcvars.is_file() else None


def msvc_environment() -> Optional[dict]:
    """Environment as vcvars64.bat leaves it, so colcon can find cl.exe.

    Harvesting `set` after vcvars saves anyone having to open a VS shell.
    """
    vcvars = find_vcvars()
    if vcvars is None:
        return None
    # vcvars must be its own argument: folded into one string, list2cmdline re-quotes
    # the spaces in its path and cmd cannot find it.
    result = run_quiet(["cmd", "/c", str(vcvars), "&&", "set"], timeout=120)
    if result.returncode != 0:
        return None
    env = dict(
        line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
    )
    return env or None


def msvc_available() -> bool:
    """Whether a usable C++ toolchain is already present.

    cl.exe on PATH means we are inside a developer prompt and need nothing more;
    otherwise vcvars is what lets us construct that environment ourselves.
    """
    if sys.platform != "win32":
        return False
    return shutil.which("cl") is not None or find_vcvars() is not None


def msvc_issue() -> Optional[dict]:
    if sys.platform != "win32" or msvc_available():
        return None
    return requirement_issue(
        "msvc",
        "cl.exe not found. ROS 2 C++ packages need the MSVC toolchain; install the "
        "Build Tools with the 'Desktop development with C++' workload.",
    )


def check_prerequisites(
    developer: bool = False,
    require_python: bool = False,
    project_root: Path | str | None = None,
    require_build_tools: bool = False,
) -> tuple[list[dict], list[str]]:
    """Return (blocking_issues, warnings)."""
    prepend_pixi_to_path()
    issues, warnings = [], []

    if require_python and not python_available():
        issues.append(requirement_issue("python", "python not found"))

    if not pixi_available():
        issues.append(requirement_issue("pixi", "pixi not found in PATH"))
    elif not pixi_version_ok():
        issues.append(requirement_issue(
            "pixi", f"pixi must be >= {min_pixi_version()} for multi-platform lock support"
        ))

    if not git_available():
        issue = requirement_issue("git", "git not found in PATH")
        if developer:
            issues.append(issue)
        else:
            warnings.append(
                f"{issue['name']} not found; sub-repositories will be downloaded as ZIP "
                f"archives. Install Git for full update support: {issue['url']}"
            )
    elif developer:
        warnings.extend(git_identity_warnings())

    optional_checks = [workspace_path_issue(project_root) if project_root else None,
                       msvc_issue() if require_build_tools else None]
    issues.extend(issue for issue in optional_checks if issue)

    return issues, warnings


def print_prerequisite_report(issues: list[dict], warnings: list[str]) -> None:
    for issue in issues:
        print(f"ERROR: {format_issue(issue)}")
        if issue.get("detail"):
            print(f"       {issue['detail']}")
    for msg in warnings:
        print(f"WARNING: {msg}")


def require_prerequisites(
    developer: bool = False,
    require_python: bool = False,
    project_root: Path | str | None = None,
    require_build_tools: bool = False,
) -> None:
    issues, warnings = check_prerequisites(
        developer, require_python, project_root, require_build_tools
    )
    print_prerequisite_report(issues, warnings)
    if issues:
        raise PrerequisiteError(issues)


# --- pixi bootstrap ----------------------------------------------------------


def pixi_bin_dirs() -> list[Path]:
    """Where the official installers put pixi: %LOCALAPPDATA%\\pixi\\bin on Windows,
    ~/.pixi/bin on POSIX (and for older Windows installs)."""
    dirs = []
    if sys.platform == "win32" and os.environ.get("LOCALAPPDATA"):
        dirs.append(Path(os.environ["LOCALAPPDATA"]) / "pixi" / "bin")
    dirs.append(Path.home() / ".pixi" / "bin")
    return dirs


def prepend_pixi_to_path() -> None:
    """A fresh pixi install is not on PATH until the shell restarts."""
    path = os.environ.get("PATH", "")
    pixi_path = os.path.expanduser("~/.pixi/bin")

    if os.path.isdir(pixi_path) and pixi_path not in path.split(os.pathsep):
        path = pixi_path + os.pathsep + path

    for bin_dir in reversed(pixi_bin_dirs()):
        text = str(bin_dir)
        if bin_dir.is_dir() and text not in path.split(os.pathsep):
            path = text + os.pathsep + path

    os.environ["PATH"] = path


def pixi_install_command() -> list[str]:
    if sys.platform == "win32":
        return ["powershell", "-NoProfile", "-ExecutionPolicy", "ByPass",
                "-Command", f"irm -useb {PIXI_INSTALL_URL_WINDOWS} | iex"]
    if shutil.which("curl") is None:
        fail("pixi", f"curl is required to install pixi. Install curl, or install pixi "
                     f"manually: {REQUIREMENT_DOCS['pixi'][1]}")
    return ["sh", "-c", f"curl -fsSL {PIXI_INSTALL_URL_POSIX} | bash"]


def confirm_install(
    req_id: str,
    prompt: str,
    auto_env: str,
    default: bool = False,
) -> bool:
    """Ask before installing third-party software; skip the prompt in CI or when opted in."""
    if env_flag(auto_env) or env_flag("CI"):
        return True

    if not sys.stdin or not sys.stdin.isatty():
        fail(
            req_id,
            f"{prompt} needs confirmation in non-interactive mode. "
            f"Set {auto_env}=1 or run from an interactive terminal.",
        )

    suffix = "[Y/n]" if default else "[y/N]"
    answer = input(f"{prompt} {suffix} ").strip().lower()

    if not answer:
        return default

    return answer in ("y", "yes")


def is_nix_environment() -> bool:
    """Return True if the current process appears to be running in a Nix environment."""
    return any(
        os.environ.get(name)
        for name in ("IN_NIX_SHELL", "NIX_PATH", "NIX_PROFILES")
    )


def is_nix_ld_enabled() -> bool:
    result = subprocess.run(
        ["nixos-option", "programs.nix-ld.enable"],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        return False

    lines = result.stdout.splitlines()

    for i, line in enumerate(lines):
        if line.strip() == "Value:" and i + 1 < len(lines):
            return lines[i + 1].strip().lower() == "true"

    return False


def ensure_pixi(run_command: Callable = default_run_command, log: Log = print) -> None:
    """Make a new-enough pixi available, installing or upgrading it when allowed."""
    prepend_pixi_to_path()
    minimum = min_pixi_version()
    current = pixi_version()
    if current and version_at_least(current, minimum):
        return

    if env_flag("LUCY_SKIP_PIXI_UPGRADE"):
        fail("pixi", f"pixi {current} is older than required {minimum}" if current else "pixi not found")

    log(f"install: pixi {current} is older than {minimum} - installing latest ..." if current
        else "install: pixi not found - installing via pixi.sh ...")
    log("install: (LUCY_SKIP_PIXI_UPGRADE=1 to abort; LUCY_PIXI_AUTO_UPGRADE=1 to skip prompt)")

    if confirm_install("pixi", "Install/upgrade pixi via https://pixi.sh?", "LUCY_PIXI_AUTO_UPGRADE", default=True):
        run_command(pixi_install_command())
    else:
        fail("pixi", "pixi install/upgrade cancelled by user")
    prepend_pixi_to_path()

    current = pixi_version()
    if not current:
        fail("pixi", "pixi install finished but pixi is not on PATH. Add one of "
                     f"{', '.join(str(d) for d in pixi_bin_dirs())} to PATH and re-run.")
    if not version_at_least(current, minimum):
        fail("pixi", f"pixi {current} still below {minimum} after install.")


MSVC_WINGET_ID = "Microsoft.VisualStudio.2022.BuildTools"
MSVC_WINGET_OVERRIDE = f"--quiet --wait --norestart --add {VC_TOOLS_COMPONENT}"


def msvc_install_command() -> list[str]:
    return [
        "winget", "install", "--id", MSVC_WINGET_ID,
        "--accept-source-agreements", "--accept-package-agreements",
        "--override", MSVC_WINGET_OVERRIDE,
    ]


def ensure_msvc(run_command: Callable = default_run_command, log: Log = print) -> None:
    """Install the MSVC build tools when missing. Windows only; no-op elsewhere.

    Only the compiler component is requested: the Windows SDK usually ships with
    Windows already, and the full C++ workload is several GB larger.
    """
    if sys.platform != "win32" or msvc_available():
        return
    if env_flag("LUCY_SKIP_MSVC_INSTALL"):
        fail("msvc", "MSVC build tools not found and LUCY_SKIP_MSVC_INSTALL is set.")
    if shutil.which("winget") is None:
        fail("msvc", "winget not found, so the build tools cannot be installed automatically.")

    log("install: MSVC build tools not found - installing via winget (roughly 1.5 GB) ...")
    log("install: (LUCY_SKIP_MSVC_INSTALL=1 to abort; LUCY_MSVC_AUTO_INSTALL=1 to skip prompt)")
    if confirm_install("msvc", "Install the Visual Studio Build Tools C++ compiler?", "LUCY_MSVC_AUTO_INSTALL"):
        run_command(msvc_install_command())
    else:
        fail("msvc", "MSVC install cancelled by user")

    if not msvc_available():
        fail("msvc", "winget finished but the C++ toolchain is still not detectable. "
                     "Open a new terminal, or install the workload from the Visual Studio Installer.")
    log("install: MSVC build tools ready.")


# --- repo fetching -----------------------------------------------------------


def github_zip_url(url: str, ref: str, ref_type: str = "branch") -> str:
    slug = url.rstrip("/").removesuffix(".git")
    if "github.com/" not in slug:
        raise ValueError(f"Unsupported repository URL (expected GitHub HTTPS): {url}")
    slug = slug.split("github.com/", 1)[1]
    kind = "tags" if ref_type == "tag" else "heads"
    return f"https://github.com/{slug}/archive/refs/{kind}/{ref}.zip"


def remove_workspace_src_repo(project_root: Path | str, name: str) -> None:
    safe_rmtree(Path(project_root) / "src" / name)


def remove_build_artifacts(project_root: Path | str, log: Log = print) -> None:
    """Remove colcon build/install/log trees (also used by scripts/clean.py)."""
    for name in BUILD_ARTIFACT_DIRS:
        target = Path(project_root) / name
        if target.exists():
            log(f"Removing {target}")
            safe_rmtree(target)


def extract_single_root_zip(zip_path: str, dest_parent: str, repo_name: str) -> None:
    """Extract a GitHub archive and rename its single top-level dir to repo_name."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        top_levels = {name.split("/")[0] for name in zf.namelist() if name.strip()}
        zf.extractall(dest_parent)
    if len(top_levels) != 1:
        raise RuntimeError(f"Unexpected archive layout for {repo_name}: {top_levels}")
    final = os.path.join(dest_parent, repo_name)
    safe_rmtree(final)
    os.rename(os.path.join(dest_parent, next(iter(top_levels))), final)


def fetch_repo_zip(repo_name: str, url: str, branch: str, dest: str, log: Log) -> None:
    zip_url = github_zip_url(url, branch)
    log(f"Downloading {repo_name} from {zip_url}")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, f"{repo_name}.zip")
        urllib.request.urlretrieve(zip_url, zip_path)
        extract_single_root_zip(zip_path, os.path.dirname(dest), repo_name)


def fetch_repo_git(
    repo_name: str, url: str, branch: str, dest: str,
    mode: str, run_command: Callable, log: Log,
) -> None:
    if mode == "repair" or not os.path.isdir(os.path.join(dest, ".git")):
        safe_rmtree(dest)
        log(f"Cloning {repo_name} (branch {branch}) ...")
        run_command(["git", "clone", "-b", branch, url, dest])
        return

    log(f"Updating {repo_name} (branch {branch}) ...")
    git = ["git", "-C", dest]
    current_url = run_quiet(git + ["remote", "get-url", "origin"]).stdout.strip()
    if current_url and current_url != url:
        log(f"install: updating origin remote for {repo_name} -> {url}")
        run_command(git + ["remote", "set-url", "origin", url])
    run_command(git + ["fetch", "origin"])
    if run_command(git + ["checkout", branch], check=False) != 0:
        run_command(git + ["checkout", "-b", branch, f"origin/{branch}"])
    if run_command(git + ["pull", "--ff-only", "origin", branch], check=False) != 0:
        raise RuntimeError(
            f"Cannot fast-forward {repo_name} on {branch}. "
            "Merge/rebase locally or re-run with --repair."
        )


def fetch_repo(
    repo_name: str, url: str, branch: str, dest: str, *,
    mode: str, fetch_method: str, developer: bool, run_command: Callable, log: Log,
) -> str:
    """Fetch one repo; returns the method actually used ('git' or 'zip')."""
    use_git = fetch_method == "git" and git_available()
    if developer and not use_git:
        fail("git", "Developer install requires Git")

    if use_git:
        fetch_repo_git(repo_name, url, branch, dest, mode, run_command, log)
        return "git"

    if mode != "repair" and os.path.isdir(os.path.join(dest, ".git")):
        log(f"Keeping existing git checkout for {repo_name} (git not available).")
        return "git"

    safe_rmtree(dest)
    fetch_repo_zip(repo_name, url, branch, dest, log)
    return "zip"


def install_repos(
    project_root: Path | str,
    mode: InstallMode,
    *,
    developer: bool,
    repos_branch: Optional[str] = None,
    fetch_method: str = "auto",
    run_command: Callable = default_run_command,
    log: Log = print,
) -> str:
    """Clone/update/repair every repo in the manifest. Returns effective fetch method."""
    if mode == "build-only":
        return fetch_method

    root = Path(project_root)
    repos = parse_repos(root, developer, repos_branch)
    if not repos:
        raise RuntimeError(f"No repos with name and url in {repos_config_path(root)}")

    if fetch_method == "auto":
        fetch_method = "git" if git_available() else "zip"
    (root / "src").mkdir(parents=True, exist_ok=True)

    effective = fetch_method
    for repo in repos:
        if mode == "repair":
            log(f"Repair: removing src/{repo['name']} ...")
            remove_workspace_src_repo(root, repo["name"])
        used = fetch_repo(
            repo["name"], repo["url"], repo["branch"], str(root / "src" / repo["name"]),
            mode=mode, fetch_method=effective, developer=developer,
            run_command=run_command, log=log,
        )
        if used == "zip":
            effective = "zip"

    if effective == "zip" and mode == "update":
        log("NOTE: ZIP-based install - local changes under src/ were replaced.")

    mark_optional_colcon_ignore(root, repos, log)
    return effective


# --- pixi / build ------------------------------------------------------------


def pixi_run(project_root: Path | str, args: list[str], run_command: Callable) -> int:
    return run_command(["pixi", *args], cwd=str(project_root))


def ensure_windows_libexec_shims(project_root: Path | str, log: Log = print) -> list[str]:
    """Give conda ROS packages the Windows launcher stubs they ship without.

    RoboStack installs its Python nodes as extensionless Unix scripts, which
    ros2 launch cannot exec because it resolves exec= through PATHEXT.
    Re-run after every pixi install, which recreates the environment.
    """
    if sys.platform != "win32":
        return []

    created = []
    for env_dir in sorted((Path(project_root) / ".pixi" / "envs").glob("*")):
        for script in sorted(env_dir.glob("Library/lib/*/*")):
            shim = script.with_suffix(".bat")
            if script.suffix or not script.is_file() or shim.exists():
                continue
            if script.with_suffix(".exe").exists() or script.with_suffix(".cmd").exists():
                continue
            try:
                if not script.open("rb").readline().startswith(b"#!"):
                    continue
            except OSError:
                continue
            shim.write_text(
                f'@echo off\r\n"%~dp0..\\..\\..\\python.exe" "%~dp0{script.name}" %*\r\n',
                encoding="ascii",
            )
            created.append(f"{script.parent.name}/{script.name}")

    if created:
        log(f"Windows: added {len(created)} launcher stubs for conda ROS nodes "
            f"(e.g. {', '.join(created[:3])})")
    return created


ROSBRIDGE_SIGNAL_ORIGINAL = """    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)
"""

ROSBRIDGE_SIGNAL_PATCHED = """    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            # Windows asyncio has no add_signal_handler; fall back to signal.signal.
            signal.signal(sig, lambda *_: loop.call_soon_threadsafe(handle_signal))
"""


def patch_windows_rosbridge_signals(project_root: Path | str, log: Log = print) -> list[str]:
    """Stop rosbridge crashing on startup under Windows.

    rosbridge_suite 2.6.0 calls loop.add_signal_handler(), unimplemented on
    Windows, just after binding the socket: the port opens but nothing ever
    answers. Upstream bug; drop this once it ships a fix.
    """
    if sys.platform != "win32":
        return []

    patched = []
    for env_dir in sorted((Path(project_root) / ".pixi" / "envs").glob("*")):
        script = env_dir / "Library" / "lib" / "rosbridge_server" / "rosbridge_websocket"
        if not script.is_file():
            continue
        source = script.read_text(encoding="utf-8")
        if ROSBRIDGE_SIGNAL_ORIGINAL not in source:
            continue
        script.write_text(
            source.replace(ROSBRIDGE_SIGNAL_ORIGINAL, ROSBRIDGE_SIGNAL_PATCHED), encoding="utf-8"
        )
        patched.append(str(script))

    if patched:
        log("Windows: guarded rosbridge's asyncio signal handlers "
            "(upstream rosbridge_suite crashes on Windows without this)")
    return patched


def pixi_install(
    project_root: Path | str, run_command: Callable = default_run_command, log: Log = print
) -> None:
    if not (Path(project_root) / "pixi.lock").is_file():
        log("No pixi.lock - running pixi lock (solves every platform in pixi.toml) ...")
        pixi_run(project_root, ["lock"], run_command)
    log("Pixi install (RoboStack Jazzy, all workspace platforms) ...")
    pixi_run(project_root, ["install"], run_command)
    ensure_windows_libexec_shims(project_root, log)
    patch_windows_rosbridge_signals(project_root, log)


def build_local_realsense_optional(
    project_root: Path | str, run_command: Callable = default_run_command, log: Log = print
) -> None:
    """Optional local librealsense build (Linux-targeted shell script)."""
    if not env_flag("LUCY_BUILD_REALSENSE"):
        return
    if sys.platform == "win32":
        log("RealSense: LUCY_BUILD_REALSENSE set but the local build is Linux-only; skipping.")
        return
    log("LUCY_BUILD_REALSENSE enabled - building librealsense locally ...")
    script = Path(project_root) / "scripts" / "build_local_realsense.sh"
    run_command(["bash", str(script)], cwd=str(project_root))


def build_workspace(
    project_root: Path | str, run_command: Callable = default_run_command, log: Log = print
) -> None:
    log("Building ROS workspace (colcon) ...")
    pixi_run(project_root, ["run", "build"], run_command)
    log("Installing control panel dependencies (yarn) ...")
    pixi_run(project_root, ["run", "panel-install"], run_command)
    build_local_realsense_optional(project_root, run_command, log)
    setup_firmware_toolchain(project_root, run_command, log)


def setup_firmware_toolchain(
    project_root: Path | str, run_command: Callable = default_run_command, log: Log = print
) -> None:
    """Install Rust/RP2040 toolchain into the Pixi env (idempotent)."""
    if env_flag("LUCY_SKIP_FIRMWARE_SETUP"):
        log("Firmware toolchain: LUCY_SKIP_FIRMWARE_SETUP set — skipping")
        return
    pixi_run(project_root, ["run", "firmware-setup"], run_command)


# --- flow --------------------------------------------------------------------


def run_flow(
    project_root: Path | str,
    mode: InstallMode = "install",
    *,
    developer: Optional[bool] = None,
    repos_branch: Optional[str] = None,
    fetch_method: str = "auto",
    skip_build: bool = False,
    run_command: Callable = default_run_command,
    log: Log = print,
) -> dict:
    """Run a full install/update/repair/build-only; returns a summary."""
    root = Path(project_root)
    load_dotenv(root)
    if developer is None:
        developer = env_flag("DEV")
    if developer:
        log("DEV=true: using url_ssh from repos config.")

    ensure_pixi(run_command, log)

    if is_nix_environment():
        if not is_nix_ld_enabled():
            raise NixLdError("Please enable `programs.nix-ld.enable = true;` in your NixOS configuration and rebuild your system before continuing. See README.md for details.")

    if not skip_build:
        ensure_msvc(run_command, log)
    require_prerequisites(
        developer=developer, project_root=root, require_build_tools=not skip_build
    )

    if mode == "repair":
        log("Repair: removing colcon artifacts (build/, install/, log/) ...")
        remove_build_artifacts(root, log)

    effective = install_repos(
        root, mode, developer=developer, repos_branch=repos_branch,
        fetch_method=fetch_method, run_command=run_command, log=log,
    )

    if mode == "repair":
        log("Repair: re-solving Pixi lock (pixi lock) ...")
        pixi_run(root, ["lock"], run_command)

    pixi_install(root, run_command, log)

    if skip_build:
        log("Skipping workspace build (--skip-build).")
    else:
        build_workspace(root, run_command, log)

    return {"mode": mode, "developer": developer, "fetch_method": effective, "skip_build": skip_build}


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="install.py",
        description="Lucy workspace setup (clone sub-repos, pixi install, colcon build).",
    )
    parser.add_argument("mode", nargs="?", default=None,
                        choices=["install", "update", "repair", "build-only"],
                        help="Install operation (default: install)")
    parser.add_argument("--update", action="store_true", help="Same as the default install")
    parser.add_argument("--repair", action="store_true",
                        help="Wipe build/install/log, re-clone src, re-lock")
    parser.add_argument("--build-only", action="store_true", help="Skip git; pixi install + build")
    parser.add_argument("--skip-build", action="store_true", help="Clone/pull only (CI)")
    parser.add_argument("--developer", action="store_true",
                        help="Developer install (SSH clones, requires git)")
    parser.add_argument("--repos-branch", default=None,
                        help="Fallback branch for repos without one set")
    parser.add_argument("--fetch-method", choices=["git", "zip", "auto"], default="auto",
                        help="How to fetch repositories (default: auto)")
    args = parser.parse_args(argv)

    for flag, mode in (("repair", "repair"), ("build_only", "build-only"), ("update", "update")):
        if getattr(args, flag) and not args.mode:
            args.mode = mode
            break
    args.mode = args.mode or "install"
    return args


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    try:
        run_flow(
            ROOT, args.mode,
            developer=True if args.developer else None,
            repos_branch=args.repos_branch,
            fetch_method=args.fetch_method,
            skip_build=args.skip_build,
        )
    except PrerequisiteError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (subprocess.CalledProcessError, RuntimeError, ValueError) as exc:
        print(f"Install failed: {exc}", file=sys.stderr)
        return 1
    except NixLdError as exc:
        print(f"MANUAL ACTION NEEDED: {exc}", file=sys.stderr)
        return 1

    if args.skip_build:
        print("Repos ready. Run 'pixi run build' or re-run without --skip-build.")
    else:
        print("Install complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
