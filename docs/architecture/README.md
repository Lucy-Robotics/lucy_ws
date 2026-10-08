# Architecture index

Entry point for Lucy architecture documentation. Schematics first;
conventions for authors live beside them in the [guide](GUIDE.md).

## Schematics

| Doc | Content |
|-----|---------|
| [overview.md](overview.md) | **System** - Lucy workspace packages + external UI (`lucy_control_panel` / browser), MCU, peripherals |
| [`lucy_ros_packages/docs/architecture/`](../../src/lucy_ros_packages/docs/architecture/) | Package-level charts (pipeline, SHM/Modbus) |
| [`lucy_embedded_firmware/docs/architecture/`](../../src/lucy_embedded_firmware/docs/architecture/) | Package-level charts (board crates, banks) |
| [`lucy_control_panel/docs/architecture/overview.md`](../../src/lucy_control_panel/docs/architecture/overview.md) | Package-level charts (UI container) |

Robot package `docs/hardware_mapping.md` stays **schema-only** (no duplicate system charts).

## Conventions

| Doc | Content |
|-----|---------|
| [GUIDE.md](GUIDE.md) | Mermaid + UML mapping, caption rules, keep-updated rules |

Use the guide when **writing or editing** schematics. Readers start from the
schematics table above.

## Keep-updated rules (summary)

Full rules are in [GUIDE.md](GUIDE.md). Short version:

1. System connectivity change → [overview.md](overview.md).
2. Package-internal flow → that package’s `docs/architecture/`.
3. Prefer editing an existing chart; one concern per diagram.
