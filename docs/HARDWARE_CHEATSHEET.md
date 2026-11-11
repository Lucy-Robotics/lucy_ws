# POC hardware with 3d view

## Firmware
1. Linux Serial Port Access (one-time setup)
pixi run setup-udev

2. Build firmware (colcon package, also builds the host mcu_bridge; `pixi run build` builds every firmware)
pixi run firmware-build-rp2040

3. Flash rp2040 (colcon installs the UF2 image)
sudo picotool load -fx install/lucy_embedded_firmware_rp2040/share/lucy_embedded_firmware_rp2040/firmware/lucy-embedded-firmware-rp2040.uf2

## Run

1. Run core
pixi shell
LUCY_ROBOT_PACKAGE=so_arm101_urdf ros2 launch lucy_bringup lucy.launch.py real:=true robot_package:=so_arm101_urdf

2. Run control panel
pixi run panel-dev

3. Run firmware
cd src/lucy_embedded_firmware/firmwares/sim
cargo run -- so_arm
