# POC hardware with 3d view

## Firmware
1. Linux Serial Port Access (one-time setup)
```bash
pixi run setup-udev
```

2. Build firmware (example: Servo2040)
```bash
cd src/lucy_embedded_firmware
pixi run firmware-setup   # from lucy_ws root if needed
cargo build --release -p lucy_embedded_firmware_rp2040_servo2040 \
  --target thumbv6m-none-eabi
```

3. Convert firmware to UF2
```bash
elf2uf2-rs target/thumbv6m-none-eabi/release/lucy_embedded_firmware_rp2040_servo2040 \
  lucy_embedded_firmware_rp2040_servo2040
```

4. Flash rp2040
```bash
picotool load -fx lucy_embedded_firmware_rp2040_servo2040.uf2
```

Prefer `pixi run firmware-build` / `firmware-flash` from the workspace root so
the config pipeline installs `config/config_<board>.yaml` first.

## Run

1. Run core
```bash
pixi shell
LUCY_ROBOT_PACKAGE=so_arm101_urdf ros2 launch lucy_bringup lucy.launch.py real:=true robot_package:=so_arm101_urdf
```

2. Run control panel
```bash
pixi run panel-dev
```

3. Run firmware sim (host)
```bash
cd src/lucy_embedded_firmware/firmwares/sim
cargo run -- so_arm
```
