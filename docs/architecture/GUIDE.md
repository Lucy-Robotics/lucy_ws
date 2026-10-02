# Architecture documentation guide

Conventions for Lucy architecture docs across **`lucy_ws`** and package repos.
Follow this guide when **adding or editing** schematics.

**Index (schematics):** [README.md](./README.md)

## Choices

| Choice | Rule |
|--------|------|
| Source of truth | Mermaid embedded in Markdown under `docs/architecture/` (or package equivalent) |
| Review | Same PR as the code change |
| Layers | **System** (`lucy_ws`) → **Package** → **Component** - one concern per diagram |
| External actors | Always named on system diagrams (`lucy_control_panel` / Browser, `MCU`, `Actuators`, `Cameras`, `Gazebo`) |
| Non-canonical | Draw.io / Figma / PNG / slides are exports or sketches only - never the source of truth |

## UML ↔ Mermaid mapping (required)

Mermaid does not implement full UML. We use **UML conventions** via Mermaid types. Every schematic must declare its UML kind in a caption line before the fence.

| UML diagram | Mermaid type | Lucy use |
|-------------|--------------|----------|
| **Component / Context** | `flowchart` | System overview; package black boxes; actors outside the boundary |
| **Deployment** | `flowchart` with host subgraphs | Workstation, Robot SBC, MCU |
| **Sequence** | `sequenceDiagram` | Joint cmd → SHM → Modbus → actuator; timed interactions |
| **Activity / pipeline** | `flowchart LR` or `stateDiagram-v2` | VALIDATE → GENERATE → BUILD → FLASH → RELOAD |
| **Class / structure** | `classDiagram` | Firmware crates / banks when structure matters |
| **Not used** | ER, timing, full UML profiles | Prefer Markdown tables for YAML schema |

### Caption format

Immediately before each Mermaid block:

```markdown
**UML Component (system context)** - Lucy workspace and external actors.
```

Replace `Component` / the parenthetical with the matching UML kind and a short scope phrase.

## UML-style conventions in Mermaid

- **Actors / external systems:** Outside the system (or package) boundary subgraph; capital noun names (`Browser`, `MCU`).
- **Components:** Package id or PascalCase (`lucy_ros_packages`); no implementation detail on system diagrams.
- **Connectors:** Labeled edges with protocol or artifact (`"USB CDC Modbus RTU"`, `"active.yaml"`). Solid `-->` for runtime; dotted `-.->` for generate / build / config.
- **Boundary:** One subgraph = one UML component (or system) boundary.
- **Stereotypes:** Optional rare text tags in labels (`«firmware»`, `«robot»`).
- **Mermaid hygiene:**
  - No spaces in node IDs (use camelCase / underscores).
  - Quote edge labels that contain special characters.
  - No HTML entities in labels.
  - Do **not** color individual nodes with `style` / `classDef` fills.
  - **Do** set edge visibility for dark/light readers:
    - Flowcharts: `%%{init}%%` with themeVariables + `linkStyle default stroke:#00FF41`
    - Sequence/class diagrams: no init directive (renderer default provides visibility)

### Edge legend (shared)

| Edge | Meaning |
|------|---------|
| `A --> B` | Runtime dependency or data path |
| `A -.-> B` | Generate, build, flash, or config-time link |
| Labeled edge | Protocol, topic family, or artifact name |

### Units (cross-cutting)

| Layer | Unit |
|-------|------|
| Robot hardware YAML | radians |
| Control panel editors | degrees (UI only) |
| SHM + Modbus registers | milliradians |

## Document layout

| Layer | Location | Owns |
|-------|----------|------|
| Index | [`README.md`](./README.md) | Entry point - schematics + link to this guide |
| System | [`overview.md`](overview.md) | Full Lucy schematic (browser, packages, MCU, peripherals) |
| Conventions | This guide | UML ↔ Mermaid rules |
| Package | `<repo>/docs/architecture/` | Component-level flows inside that package |
| Robot schema | `<robot>/docs/hardware_mapping.md` | YAML schema only - **no** system charts |

**One system Mermaid only** - in [`overview.md`](overview.md). Package repos link up; they must not copy the system chart.

## Keep-updated rules

1. System connectivity change (browser ↔ ROS, SHM/Modbus, board flash, sim vs real) → update [`overview.md`](overview.md).
2. Package-internal flow or package-local gap → that package’s `docs/architecture/`.
3. Prefer editing an existing chart over adding a new file; one concern per diagram.
4. GitHub renders Mermaid; no diagram CI for now.

## Related

- [Architecture index](./README.md)
- [System overview](overview.md)
