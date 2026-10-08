# Pixi + RoboStack setup

Lucy uses [Pixi](https://pixi.prefix.dev/) with the [RoboStack Jazzy](https://robostack.github.io/) channel for ROS 2 Jazzy dependencies. Workspace packages under `src/` are built with **colcon** into `install/`; Pixi provides the base ROS environment and activation scripts.

## Do not use rosdep

**Do not run `rosdep install`** in this workspace. rosdep resolves system packages via apt and bypasses Pixi, which breaks the reproducible RoboStack environment.

Instead:

- Add missing ROS packages with `pixi add --feature ros ros-jazzy-<package>` (or edit `[feature.ros.dependencies]` in `pixi.toml`).
- Clone packages that are not on RoboStack into `src/` via [`config/repos.json`](../config/repos.json).

## Dependency audit workflow

When adding or changing workspace packages:

1. Read `package.xml` / `CMakeLists.txt` for new `depend` / `find_package` entries.
2. Check whether RoboStack provides `ros-jazzy-<name>` on [prefix.dev/robostack-jazzy](https://prefix.dev/robostack-jazzy).
3. If available, add to `pixi.toml` under `[feature.ros.dependencies]`.
4. If not available (e.g. `micro_ros_agent`), add a clone entry to `config/repos.json` (use `"optional": true` when the stack works without it).
5. Regenerate the lock and install:

```bash
pixi install          # updates pixi.lock for every platform in pixi.toml
```

`install.py` runs `pixi lock` automatically if `pixi.lock` is missing, then `pixi install`.

**Pixi ≥ 0.78** is recommended for multi-platform lock resolution (`curl -fsSL https://pixi.sh/install.sh | bash`).

### Mutex pin

`ros2-distro-mutex = "0.15.*"` in `pixi.toml` keeps all RoboStack packages on the same rebuild cycle ([RoboStack #125](https://github.com/RoboStack/ros-jazzy/issues/125)).

### Platform-specific deps

Use Pixi target tables in `pixi.toml`:

- `[target.linux]` - `gstreamer`, `libgl-devel`
- **tmux** - host package (apt, Homebrew); not in Pixi
- `[feature.ros.target.osx-*]` - `pygraphviz`, Cyclone DDS RMW

## Build, launch, and activation

| Task | Command |
|------|---------|
| Install env | `pixi install` |
| Build workspace | `pixi run build` |
| Control panel deps | `pixi run panel-install` |
| Tests | `pixi run test` |
| ROS doctor | `pixi run doctor` |
| Dev shell (ROS CLI) | `pixi run shell` |

### Launch component tasks

Run in **separate terminals** (or use `./launch_lucy.sh` Control Center instead). ROS stacks use [`scripts/pixi_lucy_launch.sh`](../scripts/pixi_lucy_launch.sh).

| Task | Command |
|------|---------|
| Core | `pixi run core` |
| Gazebo GUI | `pixi run sim` |
| Gazebo headless | `pixi run sim-headless` |
| Sim + RViz | `pixi run sim-rviz` |
| RViz | `pixi run rviz` |
| Control panel | `pixi run control-panel` |
| rqt | `pixi run rqt` |
| Lucy CLI | `pixi run lucy-cli` |

Robot package: `LUCY_ROBOT_PACKAGE=thais_urdf pixi run sim-headless` (default `inmoov_urdf`).

See [`docs/developer_lucy_packages.md`](developer_lucy_packages.md#launch) for Control Center vs Pixi workflows and the debug shell.

Colcon uses `--symlink-install` on Linux/macOS and `--merge-install` on Windows (`pixi.toml` `[feature.build]` tasks).

Activation scripts (`install/setup.bash` or `install/setup.bat`) are wired via `[target.unix.activation]` / `[target.win.activation]` in `pixi.toml`, so `pixi run` and `pixi shell` automatically overlay the workspace. `GZ_SIM_SYSTEM_PLUGIN_PATH` points at conda Gazebo plugins. On **Linux**, `scripts/gz_rendering_env.sh` discovers ogre2 plugin/resource paths (version-agnostic).

On **Jetson**, also source [`scripts/nix_gl_env.sh`](../scripts/nix_gl_env.sh) (automatic for `pixi run sim*`, `rqt`, `lucy-cli`, and the launcher) so Tegra/NVIDIA GL libraries precede conda Mesa. Jetson detection is implemented in [`launcher/platform.py`](../launcher/platform.py); bash scripts source [`scripts/detect_jetson.sh`](../scripts/detect_jetson.sh).

## Lock refresh checklist

After editing `pixi.toml`:

```bash
pixi install
git add pixi.toml pixi.lock
```

Commit both files together so CI and other platforms stay in sync.

## Release builds (follow-up)

End-user **pre-built** packages via `pixi-build-ros` and conda channels are planned as a separate release workflow. See [`docs/pixi_release.md`](pixi_release.md).
