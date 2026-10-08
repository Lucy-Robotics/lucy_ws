# Adding a robot URDF package to Lucy

Guide for contributors who want to add a new robot description package
(humanoid, arm, end effector, etc.) to the Lucy workspace.

Use **`so_arm101_urdf`** as the newest minimal reference, and **`inmoov_urdf`** /
**`thais_urdf`** for full humanoid examples.

Related docs:

- [developer_lucy_packages.md](developer_lucy_packages.md) - workspace / Pixi / launch
- [launcher_packages.md](launcher_packages.md) - Control Center package entries
- [pixi_setup.md](pixi_setup.md) - dependencies
- Package-level: `src/<robot>_urdf/docs/DEVELOPER.md`

---

## 1. What Lucy expects from a “robot package”

A package is selectable as `robot_package:=…` when it provides:

| Required | Purpose |
|----------|---------|
| `launch/control.launch.py` | Real / mock control via `lucy_control_supervisor` |
| `description/` | Xacro tree + meshes |
| `config/control.launch.yaml` | Default `urdf_path`, `base_path`, `controllers_yaml` |
| `config/hardware/active.yaml` | Boards, actuators, sensors for the config pipeline |
| `config/controllers.yaml` | Controller manager params (usually **generated**) |

Recommended extras: `gazebo.launch.py`, `joint_preview.launch.py`, RViz configs,
`worlds/default.sdf`, xacro smoke tests, `docs/DEVELOPER.md`.

---

## 2. Package layout (canonical)

```text
my_robot_urdf/
├── package.xml
├── CMakeLists.txt
├── version.txt
├── description/
│   ├── urdf/<entry>.urdf.xacro          # sole entry point
│   ├── robot_description/
│   │   ├── urdf/properties.xacro
│   │   ├── urdf/robot_description.urdf.xacro
│   │   └── meshes/{stl|dae}/
│   ├── ros2_control/<name>_ros2_control.xacro   # generated
│   └── gazebo/
│       ├── <name>_gazebo_physics.xacro          # hand-written
│       ├── gazebo.xacro                         # generated
│       └── gazebo_bridge.yaml                   # generated
├── launch/
│   ├── control.launch.py
│   ├── gazebo.launch.py
│   ├── joint_preview.launch.py
│   ├── rviz.launch.py
│   └── rviz_standalone.launch.py
├── config/
│   ├── control.launch.yaml
│   ├── controllers.yaml
│   ├── <name>_rviz.rviz
│   └── hardware/
│       ├── active.yaml
│       ├── active_meta.yaml
│       └── configs/default.yaml
├── worlds/default.sdf
├── docs/DEVELOPER.md
└── test/test_xacro_smoke.py
```

**CMake:** install `launch`, `config`, `description`, `docs`, `worlds` to
`share/<package>/`.

**package.xml:** mirror `thais_urdf` / `so_arm101_urdf`. Do **not** add an
`exec_depend` on `lucy_ros2_control` (dependency cycle). Keep
`lucy_control_supervisor` as an exec depend for control launches.

---

## 3. Step-by-step

### 3.1 Repository + workspace wiring

1. Create a GitHub repo (or clone the org template).
2. Add an entry under `src/` and list it in `config/repos.json` (upstream) or
   `config/repos.json.local` (local / WIP):

```json
{
  "name": "my_robot_urdf",
  "branch": "dev",
  "url_https": "https://github.com/Sentience-Robotics/my_robot_urdf.git",
  "url_ssh": "git@github.com:Sentience-Robotics/my_robot_urdf.git"
}
```

3. Run `python3 install.py` (or clone manually into `src/`).

### 3.2 Description (URDF → xacro)

1. Pick an **entry** xacro (e.g. `description/urdf/my_robot.urdf.xacro`).
2. Follow the InMoov include pattern:
   - `properties.xacro` (scale / constants)
   - `robot_description.urdf.xacro` (links / joints / materials)
   - Unless `use_gazebo_sim`: include generated ros2_control xacro
   - If `use_gazebo_sim`: include physics + generated `gazebo.xacro`
3. Resolve meshes with `file://$(arg base_path)/robot_description/meshes/...`
   (launch files pass absolute `base_path`).
4. Drop ROS 1 `<transmission>` blocks; ros2_control replaces them.
5. Keep joint names stable - they must match hardware YAML and controllers.

**Bringup / pipeline note:** both `lucy_bringup` and `lucy_config_pipeline`
read `config/control.launch.yaml` for `urdf_path` / `base_path` /
`controllers_yaml`. Older packages that omit that file still fall back to
`description/urdf/inmoov.urdf.xacro`. Always set `urdf_path` in
`control.launch.yaml` when your entry filename differs.

### 3.3 Hardware YAML

Create `config/hardware/active.yaml` (`version: 1`) with:

- `robot_name`, `generated_files` basenames
- `boards:` (topics, controller type, `board_class`, slot counts)
- `actuators:` one row per controlled URDF joint
- `sensors:` list (may be empty; schema still requires the key)

**`servo_type`** must be `"180"`, `"270"`, or `"300"` today (PWM hobby schema).
Smart bus servos (e.g. STS3215 on SO-ARM101) still use a PWM type as a stand-in
until bus-servo support lands. Document the real hardware in `DEVELOPER.md`.

Sensor rows need `id`, `type`, `associated_actuator`, `board`, `virtual_pin`,
`physical_pin`, `min_value`, `max_value`, `enabled`. Encoder placeholders can use
`type: encoder` with `enabled: false` (see `so_arm101_urdf`).

Copy the preset to `config/hardware/configs/default.yaml` and set
`active_meta.yaml`.

### 3.4 Generate ros2_control / controllers / Gazebo

```bash
generate_config \
  --input src/my_robot_urdf/config/hardware/active.yaml \
  --urdf src/my_robot_urdf/description/urdf/my_robot.urdf.xacro \
  --base-path src/my_robot_urdf/description \
  --controller-config src/my_robot_urdf/config/controllers.yaml \
  --output-dir /tmp/my_robot_gen \
  --targets all

cp /tmp/my_robot_gen/<ros2_control_xacro> \
  src/my_robot_urdf/description/ros2_control/
cp /tmp/my_robot_gen/controllers.yaml src/my_robot_urdf/config/
cp /tmp/my_robot_gen/gazebo.xacro /tmp/my_robot_gen/gazebo_bridge.yaml \
  src/my_robot_urdf/description/gazebo/
```

Or use Control Panel **VALIDATE → ACTIVATE → RELOAD** with the new
`robot_package`.

Do not hand-edit generated files; regenerate after YAML / URDF limit changes.

### 3.5 Launch files

Copy from `thais_urdf` or `so_arm101_urdf` and replace:

- Package name in `get_package_share_directory(...)`
- Entry xacro filename
- RViz config filename
- Default `generated_files` basenames
- Gazebo spawn entity name (optional)

`control.launch.py` must forward `urdf_path`, `base_path`, `controllers_yaml`,
`use_mock_hardware`, and `ros2_control_file` into `lucy_control_supervisor`.

### 3.6 Launcher modifier

Add a modifier (usually in `config/launcher_config.json.local` while iterating):

```json
{
  "id": "robot_my_robot",
  "name": "Robot: My Robot",
  "description": "(robot_package:=my_robot_urdf)",
  "type": "modifier",
  "dependencies": ["core"],
  "conflicts": ["robot_inmoov", "robot_thais", "robot_so_arm101"],
  "command": "robot_package:=my_robot_urdf",
  "requires_pkg": "my_robot_urdf",
  "default_on": false
}
```

Update `conflicts` on existing robot modifiers so only one robot is selected.
See [launcher_packages.md](launcher_packages.md).

### 3.7 Build and verify

```bash
colcon build --symlink-install --packages-select my_robot_urdf
source install/setup.bash

ros2 run xacro xacro $(ros2 pkg prefix my_robot_urdf)/share/my_robot_urdf/description/urdf/my_robot.urdf.xacro \
  base_path:=$(ros2 pkg prefix my_robot_urdf)/share/my_robot_urdf/description \
  use_mock_hardware:=true

ros2 launch my_robot_urdf joint_preview.launch.py
LUCY_ROBOT_PACKAGE=my_robot_urdf pixi run core
```

---

## 4. Joint-state feedback (control panel blue dots)

Lucy’s `LucySystemHardware` is **open-loop** on real PWM hardware today:
`read()` echoes the last command into `/joint_states`. Blue dots therefore track
commands unless you are in Gazebo (physics can lag) or you implement encoder
feedback.

If your robot has encoders (e.g. STS3215 magnetic encoders):

1. Document the capability and add disabled sensor placeholders.
2. Plan firmware + hardware-plugin work separately (bus read → `sensors/<board>`
   → `LucySystemHardware::read()`).

---

## 5. Reference implementations

| Package | Role | Notes |
|---------|------|-------|
| `inmoov_urdf` | Full humanoid | DAE meshes, many joints, cameras, plugins |
| `thais_urdf` | Humanoid fork | Same contract as InMoov with renamed package |
| `so_arm101_urdf` | 6-DOF arm | STL meshes, single board/controller, encoder placeholders |

---

## 6. Checklist before opening a PR

- [ ] `package.xml` / `CMakeLists.txt` install the right directories
- [ ] Entry xacro expands for mock and Gazebo modes
- [ ] All meshes resolve (`file://` + `base_path`)
- [ ] Joint names match across URDF ↔ `active.yaml` ↔ controllers
- [ ] `generate_config` succeeds; generated files committed
- [ ] `joint_preview` and mock `control` launches work
- [ ] Optional: Gazebo launch + RViz
- [ ] `docs/DEVELOPER.md` explains joints, hardware, regeneration
- [ ] Workspace `repos.json(.local)` entry + launcher modifier
- [ ] Tests (at least xacro smoke) pass in CI / colcon test
- [ ] No dependency cycle with `lucy_ros2_control`

---

## 7. PR strategy (recommended)

1. **Robot repo PR** - package contents (description, launch, config, docs, tests).
2. **`lucy_ws` PR** - workspace docs / `repos.json` / launcher defaults when ready
   for everyone (local overrides can stay in `*.local` during development).

Use Conventional Commits (`feat:`, `docs:`, `build:`, `test:`) with one logical
change per commit when practical.

---

## 8. Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| `xacro` fails on missing include | Wrong relative path from entry xacro |
| Meshes invisible | Bad `base_path` or wrong `mesh_dir` |
| Controller won’t load | Joint name mismatch / stale `controllers.yaml` |
| Schema error on `servo_type` | Must be `180`/`270`/`300` |
| Bringup loads wrong URDF | Missing/incorrect `config/control.launch.yaml` `urdf_path`, or stale bringup that ignored it |
| Gazebo + real HW | Mutually exclusive (`gazebo:=true` vs `real:=true`) |
| Blue dots stuck on slider | Expected open-loop command echo |

---

## 9. Maintenance

Update this guide when:

- The robot-package discovery contract changes
- Hardware YAML schema gains new servo / sensor types
- Launch or config-generator patterns change
- A new reference robot lands in the workspace
