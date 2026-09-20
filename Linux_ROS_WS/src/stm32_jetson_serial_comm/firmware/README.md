# STM32 应用固件投放目录

本目录用于存放 Jetson 端 bootloader 工具升级 STM32 时使用的应用固件。

应用业务通信和 bootloader 升级默认使用 USB CDC `/dev/ttyACM0`。
当前应用固件包含 CS1237 ADC 支持：PB14 为 CLK，PD8 为 DIO/DRDY。
DM3.1 风扇使用 PA5 PWM、PA6/PA7 双路测速，PE15/PE13/PE11 分别为低有效 KEY1/KEY2/KEY3。
DM3.1 已移除 STM32 USART6 RTK 分帧透传；RTK 由主机通过 CH343P 直连。

## 目录

- [文件规范](#文件规范)
- [固件生成](#固件生成)
- [同步到 Jetson](#同步到-jetson)
- [Jetson 端使用](#jetson-端使用)

## 文件规范

```text
firmware/
  README.md
  .gitignore
  DM3.1_BAT_app.bin    由 STM32 构建生成，不提交到 Git
```

实际固件二进制由构建生成，并由 `.gitignore` 排除。

## 固件生成

在开发机仓库根目录构建 STM32 应用：

```bash
make -C STM32 app
```

构建完成后会自动覆盖：

```text
Linux_ROS_WS/src/stm32_jetson_serial_comm/firmware/DM3.1_BAT_app.bin
```

## 同步到 Jetson

执行同步脚本时，固件会随 ROS2 包一起推送到 Jetson：

```bash
Linux_ROS_WS/scripts/sync_to_jetson.sh
```

Jetson 端默认路径为：

```text
/home/jetson/ros_ws/src/stm32_jetson_serial_comm/firmware/DM3.1_BAT_app.bin
```

## Jetson 端使用

在 Jetson 上通过 bootloader 工具使用该固件：

```bash
ros2 run stm32_jetson_serial_comm stm32_bootloader \
  /home/jetson/ros_ws/src/stm32_jetson_serial_comm/firmware/DM3.1_BAT_app.bin \
  --device /dev/ttyACM0 \
  --request-from-app
```

升级完成后重新构建并加载 ROS2 包，再验证 ADC：

```bash
cd ~/ros_ws
source /opt/ros/foxy/setup.bash
colcon build --packages-select stm32_jetson_serial_comm
source install/setup.bash

ros2 run stm32_jetson_serial_comm serial_link \
  --device /dev/ttyACM0 --cs1237-set-channel temp --read-seconds 3
sleep 1
ros2 run stm32_jetson_serial_comm serial_link \
  --device /dev/ttyACM0 --cs1237-query --read-seconds 3
```

如果 `serial_link --help` 中没有 `--cs1237-query`，说明当前终端仍加载了旧的
ROS2 安装结果，需要清理本包的 `build/`、`install/` 后重建并重新
`source install/setup.bash`。
