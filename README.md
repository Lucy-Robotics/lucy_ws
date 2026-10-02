# Lucy ROS 2 workspace (Jazzy)

Workspace bringup for the Lucy / InMoov humanoid. ROS 2 Jazzy, Gazebo, RViz, and the web control panel run **natively** via [Pixi](https://pixi.prefix.dev/) and [RoboStack](https://robostack.github.io/).

## Requirements

| Requirement | Linux | macOS | Windows |
|-------------|-------|-------|---------|
| [Git](https://git-scm.com/downloads) | ✓ | ✓ | ✓ ([Git for Windows](https://git-scm.com/install/windows)) |
| [Python 3](https://www.python.org/downloads/) (for `Lucy.py`) | ✓ | ✓ | ✓ |
| [Pixi](https://pixi.prefix.dev/latest/installation/) **≥ 0.78** | ✓ | ✓ | ✓ |
| **tmux** (multi-window launcher) | ✓ | ✓ (`brew install tmux`) | — (launcher runs directly) |

ROS packages are installed by Pixi into `.pixi/`.

GUI apps (RViz, Gazebo, rqt) are native. Platform-specific notes (Wayland, AirPlay port conflicts) are in the [developer guide](docs/developer_lucy_packages.md#platform-setup).

## Get the repository

**Clone (recommended):**

```bash
git clone https://github.com/Sentience-Robotics/lucy_ws.git
cd lucy_ws
```

**Or** download the ZIP from GitHub (**Code → Download ZIP**), extract, and `cd lucy_ws`.

## Quickstart

### Linux / macOS

```bash
python3 Lucy.py
```

**NixOS:** enable [nix-ld](https://github.com/nix-community/nix-ld) so Pixi/RoboStack conda binaries can load the host dynamic linker:

```nix
programs.nix-ld.enable = true;
```

If you choose to install pixi beforehand, you will need to source it:
```
export PATH="$HOME/.pixi/bin:$PATH"
```

For Gazebo/RViz GL, also see the [NixOS notes](docs/developer_lucy_packages.md#platform-setup) in the developer guide.

### Windows

`Lucy-Setup.exe` is built from [Lucy-Windows-Installer](https://github.com/Sentience-Robotics/Lucy-Windows-Installer).

Keep the workspace in a path **without spaces**. Pixi console scripts (colcon, pytest, ROS 2 nodes) embed the interpreter path unquoted and cannot start from one.
Pixi resolves **`win-64`** on Windows-on-ARM too. `pixi.lock` has no `win-arm64`.

**Note:** The Lucy launcher is not available on Windows. Instead, use the following commands to start the components with Pixi, one per terminal:

```powershell
pixi run core            # robot stack, rosbridge on port 9090
pixi run control-panel   # http://localhost:4004
pixi run rviz            # optional viewer
```

Windows is **visualisation only** for now. `pixi run core` starts a `/joint_states` stand-in so the panel renders and follows the sliders, but nothing reaches hardware, and `pixi run sim*` refuses to start: ros2_control crashes on Windows ([pal_statistics#27](https://github.com/pal-robotics/pal_statistics/issues/27)), and Gazebo runs a `controller_manager` in-process through `gz_ros2_control`, so it goes down with it. See the [developer guide](docs/developer_lucy_packages.md).

## Using the Lucy launcher

**Launch** starts a **tmux** session (Linux/macOS) and the **Lucy Control Center** TUI (`python -m launcher`, or `python launcher.py` / `./launch_lucy.sh`):

| Key | Action |
|-----|--------|
| **Up/Down** | Navigate |
| **Space** | Toggle a package or tool |
| **Enter** | Apply changes / Start / Restart |
| **X** | Stop all processes and exit |

**Components you can enable:**

- **Core** — base robot stack (`lucy_bringup`)
- **Modifiers** — Simulator (Gazebo), **… headless** (server-only sim, under Simulator), Visualizer (RViz), Real Hardware
- **Interfaces** — Control Panel (web UI), Lucy CLI
- **Tools** — Console, rqt

> **Recommended starting point:** **Core + Control Panel**  (the web 3D viewer is enough for most work without heavy GUI apps)

**Real hardware:** `install.py` installs the RP2040 firmware toolchain (`pixi run firmware-setup`). Launcher **Real Hardware** and LCP hardware ACTIVATE (when SIMULATION ONLY is off) require it; re-run `pixi run firmware-setup` if a check fails.

**tmux windows** (Linux/macOS):

- **`Ctrl+B` then `W`** — window list
- **`Ctrl+B` then `N`** / **`P`** — next / previous window

On Windows, the Control Center runs without tmux (one process tree). Gazebo, RViz, and rqt still open as native GUI apps when enabled.

## Developer setup

For developer mode, see the **[developer guide](docs/developer_lucy_packages.md)**.

## Contributing

Contributions are very welcome: bug reports, feature ideas, documentation, and code.

Read **[CONTRIBUTING.md](CONTRIBUTING.md)**, and the **[Code of Conduct](CODE_OF_CONDUCT.md)**.

## License

This project is licensed under the **GNU General Public License v3.0**. See [LICENSE](LICENSE) for the full text.

Lucy is part of [Sentience Robotics](https://sentience-robotics.fr) and builds on the [InMoov](https://inmoov.fr/) open-source humanoid project.
