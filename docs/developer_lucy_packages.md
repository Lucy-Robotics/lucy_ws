# Lucy developer guide

ROS 2 **Jazzy** workspace for Lucy / InMoov. This guide covers developer mode, platform-specific setup, launch workflows, and pointers to deeper documentation. Basic install and launcher usage are in the top-level [`README.md`](../README.md).

## Developer mode

Developer mode is toggled in **`Lucy.py`** (Install menu) or by setting **`DEV=true`** in `.env` (copy from [`.env.example`](../.env.example)).

When enabled:

| Behavior | Effect |
|----------|--------|
| **SSH clones** | `install.py` uses `url_ssh` from [`config/repos.json`](../config/repos.json) instead of HTTPS |
| **No auto-launch** | Core and Control Panel are not started automatically on Launch |

SSH keys must be configured for GitHub on your host before running `install.py` with `DEV=true`.

### Local overrides (gitignored)

| File | Purpose |
|------|---------|
| [`config/repos.json.local`](../config/repos.json.local) | Forks, feature branches, skip optional repos |
| [`config/launcher_config.json.local`](../config/launcher_config.json.local) | Custom Control Center package list (e.g. multi-robot) |
| [`config/install.profile.json`](../config/install.profile.json) | Windows installer choices (written by the installer) |

Example for a fork — same structure as `repos.json`:

```json
{
  "repos": [
    {
      "name": "inmoov_urdf",
      "branch": "my-feature-branch",
      "url_https": "https://github.com/your-user/inmoov_urdf.git",
      "url_ssh": "git@github.com:your-user/inmoov_urdf.git"
    }
  ]
}
```

For a multi-robot dev setup, copy [`config/launcher_config.json.local.example`](../config/launcher_config.json.local.example) to `launcher_config.json.local`.

## Platform setup

### Linux

Standard path: `python3 install.py` then `python3 Lucy.py`.

**Wayland:** RViz/Gazebo may need `xhost +local:` or an X11 session.

**Jetson (Orin / AGX / Nano / Thor):** Pixi ships conda Mesa/GLVND ahead of the Tegra driver, which breaks Gazebo ogre2 (missing plugin, EGL segfaults). [`scripts/nix_gl_env.sh`](../scripts/nix_gl_env.sh) auto-detects Jetson and prepends `/usr/lib/aarch64-linux-gnu/nvidia` + `tegra`, sets the NVIDIA EGL vendor; [`scripts/gz_rendering_env.sh`](../scripts/gz_rendering_env.sh) discovers ogre2 plugin/resource paths on Linux. Use **`sim-headless`** or Control Center **Simulator → … headless** for camera sim without a display; GUI **`sim`** needs X11/Wayland and keeps your session `XDG_RUNTIME_DIR`. Do not set `LUCY_NIX_GL=0` on Jetson. Override: `LUCY_GPU_MODE=jetson`.

**NixOS:** Pixi/RoboStack needs host GL libraries prepended **and** Mesa EGL — both are applied by [`scripts/nix_gl_env.sh`](../scripts/nix_gl_env.sh) (launcher and `pixi run sim*`). Install **`nixGLIntel`** (or another nixGL wrapper) on PATH, or rely on the `/run/opengl-driver/lib` fallback. **Do not set `LUCY_NIX_GL=0`** — EGL/`GZ_IP` alone is not enough; sim will hang on "requesting world names". Optional overrides: `LUCY_NIX_GL_WRAPPER`, `__EGL_VENDOR_LIBRARY_FILENAMES`, `GZ_IP` — see `.env.example`.

### macOS

- Install **tmux** (`brew install tmux`) for the multi-window launcher.
- **Port 5000** is often used by AirPlay Receiver. Disable it in **System Settings → General → AirDrop & Handoff**, or set `PORT_CONTROL_PANEL=5001` in `.env`.
- Pixi uses Cyclone DDS on macOS (`RMW_IMPLEMENTATION=rmw_cyclonedds_cpp` in `pixi.toml`).

### Windows

End users get `Lucy-Setup.exe` from [Lucy-Windows-Installer](https://github.com/Sentience-Robotics/Lucy-Windows-Installer).

`python3 install.py` installs, `--repair` re-clones and rebuilds, `--build-only`
skips git. `python3 Lucy.py` runs install when the workspace is missing and
otherwise names the pixi tasks; there is no TUI on Windows (no curses, no tmux).

Pixi resolves `win-64` on Intel/AMD and Windows-on-ARM alike — `pixi.lock` has
no `win-arm64`. Colcon uses `--merge-install` there, see
[`docs/pixi_setup.md`](pixi_setup.md).

### Workspace install (`install.py`)

Pixi installs RoboStack Jazzy; `colcon build --symlink-install` builds `src/`; `yarn install` sets up the control panel.

| Command | What it does |
|---------|--------------|
| `python3 install.py` | Clone missing repos, pull existing ones, `pixi install`, colcon build, firmware toolchain |
| `python3 install.py --repair` | Wipe each repo under `src/` then re-clone and rebuild |
| `python3 install.py --build-only` | Skip git; `pixi install` + colcon + panel yarn + firmware-setup |
| `python3 install.py --skip-build` | Clone/pull only (CI) |

After the colcon/panel build, install runs **`pixi run firmware-setup`** (rustup, `thumbv6m-none-eabi`, `elf2uf2-rs`, and Raspberry Pi **`picotool`** into the Pixi env, plus `libusb`). Skip with **`LUCY_SKIP_FIRMWARE_SETUP=1`**. Verify anytime with **`pixi run firmware-check`**. Linux udev for Pico USB is still deferred when the shell is non-interactive. Restart **Core** after a first-time setup so the config pipeline node picks up `picotool` on `PATH`.

**Do not use `rosdep`** — it bypasses Pixi/RoboStack. Add deps via `pixi.toml` or clone into `src/`. See [`docs/pixi_setup.md`](pixi_setup.md).

**RealSense** (optional, not in Pixi): after a normal build, run `./scripts/build_local_realsense.sh` or `LUCY_BUILD_REALSENSE=1 python3 install.py`. Primary target is Linux; see script for aarch64 notes.

**Packages under `src/`** (from [`config/repos.json`](../config/repos.json)):

| Repo | Role |
|------|------|
| **inmoov_urdf** | URDF, Gazebo/RViz launches |
| **lucy_ros_packages** | `lucy_bringup`, ros2_control, cameras |
| **lucy_control_panel** | Web UI |
| **micro_ros_agent** | Optional (`optional: true` in repos.json) |

## Launch

Two supported workflows.

### 1. Control Center (recommended)

Day-to-day use: one tmux session (Linux/macOS), toggle components in the TUI.

| Entry | Command |
|-------|---------|
| TUI manager | `python3 Lucy.py` → **Launch** |
| Direct | `./launch_lucy.sh` |
| Windows | `python3 Lucy.py`, then the pixi tasks it lists |

| `launch_lucy.sh` flag | Purpose |
|-----------------------|---------|
| *(none)* | tmux + Control Center |
| `--headless <cmd>` | One-shot command (default: `ros2 doctor --report`) |
| `--shell` | Interactive dev shell (`pixi run shell`) |

The launcher wraps panes in `pixi run`, forwards display/GL env from `.env`, and sources `nix_gl_env.sh` for `ros2 launch`. Package list: [`docs/launcher_packages.md`](launcher_packages.md).

### 2. Pixi component tasks

Run stacks or tools in **separate terminals** (debug / scripting). ROS tasks use [`scripts/pixi_lucy_launch.sh`](../scripts/pixi_lucy_launch.sh).

| Task | Command | What it starts |
|------|---------|----------------|
| Core | `pixi run core` | `lucy_bringup` (rosbridge, config pipeline, mock stack) |
| Gazebo (GUI) | `pixi run sim` | Core + Gazebo window |
| Gazebo headless | `pixi run sim-headless` | Core + Gazebo server only |
| Sim + RViz | `pixi run sim-rviz` | Headless Gazebo + RViz |
| RViz only | `pixi run rviz` | Core + RViz |
| Control panel | `pixi run control-panel` | Vite dev server |
| rqt | `pixi run rqt` | rqt (needs core running) |
| Lucy CLI | `pixi run lucy-cli` | `ros2 run lucy_cli tui` (needs core) |

**Robot package** (default `inmoov_urdf`):

```bash
LUCY_ROBOT_PACKAGE=thais_urdf pixi run sim-headless
```

Example multi-terminal sim:

```bash
pixi run sim-headless    # terminal 1
pixi run control-panel   # terminal 2
```

### Debug shell

Interactive RoboStack + colcon overlay for ROS CLI:

```bash
pixi run shell
# or: ./launch_lucy.sh --shell
```

```bash
ros2 topic list
ros2 service list
ros2 launch lucy_bringup lucy.launch.py rviz:=true
```

For manual Gazebo launches outside `pixi run sim*`, source GL env when needed (e.g. NixOS with `nixGLIntel`):

```bash
source scripts/nix_gl_env.sh
ros2 launch lucy_bringup lucy.launch.py gazebo:=true
```

### TUI ↔ Pixi CLI

| Action | Command |
|--------|---------|
| Install / update | `python3 install.py` |
| Rebuild | `pixi run build` then `pixi run panel-install` |
| Launch | `./launch_lucy.sh` |
| Dev shell | `pixi run shell` |
| Headless one-shot | `./launch_lucy.sh --headless ros2 doctor --report` |
| Clean build dirs | `pixi run clean` |
| Workspace tests | `pixi run workspace-test` |

### `ros2 launch` modifiers

`lucy_bringup` brings up rosbridge and `/config/*` via `web_ros_api`:

| Goal | Command |
|------|---------|
| Default dev stack (mock hardware) | `ros2 launch lucy_bringup lucy.launch.py` |
| Jetson / real hardware | `… real:=true` |
| Real + RViz | `… real:=true rviz:=true` |
| Gazebo headless | `pixi run sim-headless` or `… gazebo:=true headless:=true` |

`gazebo:=true` cannot be combined with `real:=true`. With Gazebo, `rviz` is forwarded to the robot package's `gazebo.launch.py`.

### Control panel: SIMULATION ONLY + RELOAD

From **Configuration → ACTIVATE**, enable **SIMULATION ONLY** to run **VALIDATE → ACTIVATE → RELOAD** without BUILD/FLASH. The pipeline writes mock ros2_control artifacts and calls **`/lucy_control/restart`**. Hardware mode runs the same **RELOAD** after BUILD/FLASH.

When **SIMULATION ONLY** is off, the pipeline checks the firmware toolchain before BUILD (`pixi run firmware-check`). If it fails, ACTIVATE aborts with a message to run **`pixi run firmware-setup`** or re-run **`python3 install.py`**. The launcher **Real Hardware** modifier uses the same check as a preflight before applying `real:=true`.

**Gazebo caveat:** joint changes in URDF hardware blocks may require a full Gazebo restart when `use_gazebo_sim:=true`.

## Ports and environment

| Env var | Default | Purpose |
|---------|---------|---------|
| `DEV` | unset | `true` → SSH clones during `install.py` |
| `PORT_CONTROL_PANEL` | auto | Host port for control panel URL |
| `PORT_CONTROL_PANEL_CONTAINER` | `VITE_PORT` from `src/lucy_control_panel/.env`, else `4004` | Port the Vite dev server listens on inside the container |
| `PORT_ROSBRIDGE` | `9090` | rosbridge WebSocket |
| `LUCY_ROBOT_PACKAGE` | `inmoov_urdf` | Robot package for `pixi run core` / `sim-*` |
| `LUCY_NIX_GL` | `auto` | Set `0` to skip host GL prepend (**breaks NixOS Gazebo sim**) |
| `LUCY_NIX_GL_WRAPPER` | auto | `nixGLIntel`, `nixGLDefault`, or `nixGL` |

Vite proxies `/rosbridge` to `ws://127.0.0.1:9090`. Launcher sets `LUCY_LCP_*` vars for panel URLs — see [`launch_lucy.sh`](../launch_lucy.sh).

## More

| Document | Contents |
|----------|----------|
| [`docs/adding_robot_packages.md`](adding_robot_packages.md) | How to add a new robot URDF package |
| [`docs/launcher_packages.md`](launcher_packages.md) | Adding packages to the Control Center |
| [`docs/pixi_setup.md`](pixi_setup.md) | Pixi/RoboStack deps, lock workflow, component tasks |
| [`docs/pixi_release.md`](pixi_release.md) | Release packaging (pixi-build-ros) |
| [`src/lucy_ros_packages/docs/DEVELOPER.md`](../src/lucy_ros_packages/docs/DEVELOPER.md) | bringup, ros2_control, CI |
| [`src/lucy_ros_packages/doc/ROS2_CONTROL.md`](../src/lucy_ros_packages/doc/ROS2_CONTROL.md) | ros2_control on Lucy |
| [`src/inmoov_urdf/docs/DEVELOPER.md`](../src/inmoov_urdf/docs/DEVELOPER.md) | URDF, meshes, sim launches |
| [`src/so_arm101_urdf/docs/DEVELOPER.md`](../src/so_arm101_urdf/docs/DEVELOPER.md) | SO-ARM101 follower arm |
