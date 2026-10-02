### Adding a New Package to the Launcher

The launcher's configuration is entirely driven by the `launcher_config.json` file. To add a new package, tool, or modifier, you just need to add a new JSON object to the `packages` list in this file.

### Local launcher overrides (`config/launcher_config.json.local`)

To customize the launcher package list (add experimental tools, tweak commands, or hide entries) without editing the tracked `config/launcher_config.json`, create **`config/launcher_config.json.local`**. When present it is used instead of `launcher_config.json` by the launcher (`python -m launcher` or `python launcher.py`), and it is gitignored so overrides are never committed.

Use the same structure as `launcher_config.json` - copy the file and edit as needed, or include only the `packages` entries you want to change if you prefer a full replacement (the local file replaces the tracked file entirely, it is not merged).

Delete the file to fall back to the tracked `config/launcher_config.json`.

For example, if you wanted to add an `rqt_graph` tool, you would append this to the `packages` array:

```json
{
  "id": "rqt_graph",
  "name": "ROS Qt Graph",
  "description": "Visualizes the ROS 2 computation graph",
  "type": "tool",
  "dependencies": ["core"],
  "conflicts": [],
  "command": "ros2 run rqt_graph rqt_graph",
  "default_on": false
}
```

### Configuration Fields Explained

Every package entry in `config/launcher_config.json` uses the following fields to dictate how it behaves in the launcher:

| Field | Type | Description |
| :--- | :--- | :--- |
| `id` | `string` | A unique identifier for the package. Used internally for window names, resolving dependencies, and tracking the state. Must be unique. |
| `name` | `string` | The display name shown in the launcher's terminal UI. |
| `description` | `string` | A short description shown alongside the package name. |
| `type` | `string` | The classification of the package. It defines how the launcher handles it. Must be one of: <br> - `"core"`: The primary process. Usually only one exists. Selecting it clears and launches a base command.<br> - `"modifier"`: Arguments appended to the `"core"` command when active (e.g. `gazebo:=true`).<br> - `"interface"`: A user interface process launched in its own dedicated tmux window (e.g. CLI tools or background web services).<br> - `"tool"`: A utility process launched in its own dedicated tmux window (e.g. ROS standard tools or terminal sessions). |
| `dependencies` | `array` of `strings` | A list of `id`s that must be enabled before this package can be toggled on. The launcher will block you and show a warning if dependencies are missing. |
| `conflicts` | `array` of `strings` | A list of `id`s that cannot run alongside this package. Toggling this package on will automatically toggle the conflicting packages off. |
| `command` | `string` or `object` | The shell command to execute. <br> - **For `"core"`**: The base command (e.g. `ros2 launch ...`). <br> - **For `"modifier"`**: The argument string appended to the core command. <br> - **For `"interface"` / `"tool"`**: A simple string executed in a new tmux window, or a complex object containing `"start"`, `"stop"`, and `"is_running"` shell commands for custom background handling (like the web control panel). |
| `default_on` | `boolean` | If set to `true`, the package will be selected by default when the launcher boots up (currently unused as the launcher loads an empty initial state, but available for future functionality). |
| `readiness_check` | `string` | Optional shell command that exits 0 when the package or modifier is ready and running. |
| `exit_check` | `string` | Optional shell command returning the exit code of an underlying process (e.g. `cat /tmp/.lucy_real_hardware_status 2>/dev/null`), enabling immediate crash detection without a tmux window. |
| `readiness_timeout` | `integer` | Timeout in seconds before an unready package is considered crashed (default: 30s). |

### Under the Hood (`launcher` and `launch_lucy.sh`)

When you run `./launch_lucy.sh`:

1. It ensures the workspace is built (`install/setup.bash` exists).
2. On Linux/macOS with **host tmux**, it starts or attaches to a **tmux** session named `lucy_ws`.
3. The main window runs `pixi run -- python -m launcher` (Control Center TUI).

Package commands in other tmux windows are wrapped in `pixi run` so each pane gets RoboStack and the colcon overlay. Display and OpenGL-related variables from your shell and `.env` are forwarded into those panes.

When you apply changes in the launcher:
- **Core + Modifiers:** The script takes the core command, appends all active modifier commands, and spins up a dedicated `core` tmux window.
- **Interfaces / Tools:** The script spins up a new tmux window named after the package's `id` and executes its command via Pixi. Legacy complex `{start, stop, is_running}` objects are still supported for local overrides.

### Stopping packages and exiting

On **Linux and macOS**, services run in **tmux** windows. On **Windows** (Git Bash, no tmux), the same launcher TUI runs but process detection uses cross-platform logic; orphan cleanup is scoped to this workspace path so other projects are not affected.

- **Q**, **X**, or **Esc** - prompts *Stop all processes and exit?*; on **y**, every running package is torn down, then workspace-scoped orphans are killed in a **single cleanup pass** (including **Gazebo `gz sim`**, which often appears as **ruby** in `top` because Pixi wraps it), then the tmux session ends.
- Short-lived **`gz sim server`** / **`gz sim gui`** processes often have no workspace path in their command line; cleanup also checks **cwd**, **Pixi/Conda env**, and **`GZ_SIM_*`** variables so they are still reaped safely.
- **Enter (Apply)** with boxes unticked - stops those packages asynchronously; orphan cleanup runs after each stop completes.
- **Ctrl+C** outside the TUI - also triggers a full stop on exit.

Unticking a single package (e.g. Control Panel) sends **Ctrl+C** to its tmux window, waits briefly, removes the window, then reaps any workspace-scoped stragglers (`vite`, `gz sim`, `rosbridge`, etc.).
