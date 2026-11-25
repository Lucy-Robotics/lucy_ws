# POC hardware with 3d view

## Firmware
1. Linux Serial Port Access (one-time setup)
pixi run setup-udev

Linux realtime control loop (optional, one-time setup, then log out and back in)
pixi run setup-realtime

2. Build firmware (colcon package, also builds the host mcu_bridge; `pixi run build` builds every firmware)
pixi run firmware-build-rp2040

3. Flash rp2040 (colcon installs the UF2 image)
sudo picotool load -fx install/lucy_embedded_firmware_rp2040/share/lucy_embedded_firmware_rp2040/firmware/lucy-embedded-firmware-rp2040.uf2

## Run

1. Run core on the real robot. The robot package names its bridge with `bridge:` in
   `config/control.launch.yaml`: `linux` drives USB-serial servos from the host (SO-ARM101),
   `mcu_bridge` relays to the microcontroller boards. Fork the package to drive it another way.
   lucy_control_supervisor starts the host firmware (`lucy_embedded_firmware_<bridge>` package) with the stack.
LUCY_ROBOT_PACKAGE=so_arm101_urdf pixi run real
# or: ros2 launch lucy_bringup lucy.launch.py robot_package:=so_arm101_urdf mode:=real

2. Run control panel
pixi run panel-dev

3. Run the host firmware by hand (only when debugging it outside the stack)
ros2 run lucy_embedded_firmware_linux lucy-embedded-firmware-linux so_arm
