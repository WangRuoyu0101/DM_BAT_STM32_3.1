# Jetson 与 STM32 通信

`stm32_jetson_serial_comm` 是 Jetson 侧 ROS2 Python 包，默认通过 USB CDC 虚拟串口与 STM32 电源板通信，并保留 UART5 作为备用通信口。本文档仅保留 Jetson 端部署、运行、调试，以及开发机与 Jetson 之间的同步/拉取流程。

## 目录

- [功能概览](#功能概览)
- [目录规范](#目录规范)
- [硬件连接](#硬件连接)
- [Jetson 环境准备](#jetson-环境准备)
- [同步到 Jetson](#同步到-jetson)
- [从 Jetson 拉取](#从-jetson-拉取)
- [Jetson 端构建](#jetson-端构建)
- [Jetson 端链路验证](#jetson-端链路验证)
- [Jetson 端业务查询](#jetson-端业务查询)
- [CS1237 ADC 使用](#cs1237-adc-使用)
- [UM982 RTK 透传](#um982-rtk-透传)
- [WS2812B RGB](#ws2812b-rgb)
- [Jetson 端 GPIO 控制](#jetson-端-gpio-控制)
- [Jetson 端 Bootloader 升级](#jetson-端-bootloader-升级)
- [Jetson 端 ROS2 节点](#jetson-端-ros2-节点)
- [Jetson 端调试速查](#jetson-端调试速查)
- [协议参考](#协议参考)

## 功能概览

- USB CDC/UART5 二进制帧协议打包、解析和 CRC8 校验。
- Jetson 端串口链路验证和原始十六进制调试。
- STM32 综合状态、GPIO 状态、三路超声波距离查询。
- CS1237 原始 ADC 查询、运行时通道切换、温度/力值换算和 Jetson 本地标定。
- UM982 配置命令、NMEA 0183 和 RTCM 任意二进制双向透传。
- STM32 GPIO 短命令控制和 ROS2 service 控制。
- STM32 bootloader 上位机升级，默认走 USB CDC。
- ROS2 长运行节点，周期查询 STM32 并发布 topic。

当前默认接口：

- 应用业务通信默认设备为 `/dev/ttyACM0`，可用 `STM32_SERIAL_DEVICE` 覆盖。
- Bootloader 升级默认设备为 `/dev/ttyACM0`，可用 `STM32_BOOTLOADER_DEVICE` 覆盖。
- UART5 与 USB CDC 使用同一套应用协议；UART5 可作为备用链路。

## 目录规范

```text
Linux_ROS_WS/
  scripts/
    sync_to_jetson.sh        推送 src/ 到 Jetson 工作空间
    pull_from_jetson.sh      从 Jetson 工作空间拉回 src/
  src/
    stm32_jetson_serial_comm/
      firmware/              STM32 应用固件投放目录
      stm32_jetson_serial_comm/
        bootloader.py        bootloader 协议客户端
        cs1237.py            温度/力值换算和标定文件读写
        bootloader_cli.py    stm32_bootloader 命令入口
        protocol.py          UART5 应用协议编解码
        rtk_bridge.py        UM982 二进制分片读写 API
        rtk_cli.py           stm32_rtk 命令入口
        serial_driver.py     pyserial 驱动封装
        serial_host.py       主机侧帧收发封装
        serial_link_cli.py   serial_link 命令入口
        stm32_serial_node.py ROS2 节点入口
      tests/                 Python 单元测试
      README.md              本文档
```

## 硬件连接

| 项目              | 配置           |
| ----------------- | -------------- |
| 默认应用通信      | `/dev/ttyACM0` |
| 备用串口          | `/dev/ttyTHS0` / UART5 |
| 应用通信波特率    | 115200         |
| Bootloader 波特率 | 460800         |
| 数据格式          | 8N1，无流控    |
| STM32 UART5 TX    | PC12           |
| STM32 UART5 RX    | PD2            |
| CS1237 CLK        | STM32 PB14      |
| CS1237 DIO/DRDY   | STM32 PD8       |
| UM982 RXD         | STM32 PC6 / USART6 TX |
| UM982 TXD         | STM32 PC7 / USART6 RX |

应用业务和 bootloader 升级默认通过 USB CDC 虚拟串口通信。UART5 仍保留为备用通信口，接线需要交叉并共地：

```text
Jetson TX  -> STM32 PD2  / UART5_RX
Jetson RX  <- STM32 PC12 / UART5_TX
Jetson GND -> STM32 GND
```

双方均使用 3.3V TTL 电平，不要直接接 RS232 电平。

## Jetson 环境准备

在 Jetson 上安装依赖并配置串口权限：

```bash
sudo apt-get install -y python3-serial
sudo usermod -aG dialout jetson
```

修改用户组后需要退出 SSH 重新登录，或重启 Jetson。重新登录后检查设备和权限：

```bash
ls -l /dev/ttyTHS* /dev/ttyUSB* /dev/ttyACM*
id
```

`id` 输出中应包含 `dialout`。默认使用 `/dev/ttyACM0`；如果使用 UART5 备用口，且 `/dev/ttyTHS0` 不存在，需要确认 Jetson 对应 UART 已在系统配置或设备树中启用。

## 同步到 Jetson

在开发机仓库根目录执行：

```bash
Linux_ROS_WS/scripts/sync_to_jetson.sh
```

默认目标：

```text
jetson@192.168.17.130:/home/jetson/ros_ws/src
```

如需覆盖目标：

```bash
REMOTE_HOST=jetson@192.168.1.50 \
REMOTE_WS=/home/jetson/ros_ws \
Linux_ROS_WS/scripts/sync_to_jetson.sh
```

脚本会同步整个 `Linux_ROS_WS/src/`。因此 `firmware/DM3.1_BAT_app.bin` 如果已经由 STM32 构建生成，也会随 ROS2 包一起推送到 Jetson。

## 从 Jetson 拉取

如果在 Jetson 上调整了 ROS2 包源码，可在开发机仓库根目录执行：

```bash
Linux_ROS_WS/scripts/pull_from_jetson.sh
```

默认来源：

```text
jetson@192.168.17.130:/home/jetson/ros_ws/src
```

如需覆盖来源：

```bash
REMOTE_HOST=jetson@192.168.1.50 \
REMOTE_WS=/home/jetson/ros_ws \
Linux_ROS_WS/scripts/pull_from_jetson.sh
```

拉取脚本会排除 Jetson 工作空间中的 `build/`、`install/`、`log/`、`__pycache__/` 和 `*.pyc`。

## Jetson 端构建

以下命令均在 Jetson 上执行：

```bash
cd ~/ros_ws
source /opt/ros/foxy/setup.bash
colcon build --packages-select stm32_jetson_serial_comm
source install/setup.bash
```

每个新的 Jetson 终端都需要重新挂载 ROS2 环境：

```bash
cd ~/ros_ws
source /opt/ros/foxy/setup.bash
source install/setup.bash
```

如果更新了 `setup.py` 入口或安装文件，建议清理本包后重建：

```bash
cd ~/ros_ws
rm -rf build/stm32_jetson_serial_comm install/stm32_jetson_serial_comm log
source /opt/ros/foxy/setup.bash
colcon build --packages-select stm32_jetson_serial_comm
source install/setup.bash
```

## Jetson 端链路验证

应用默认通过 USB CDC 验证链路。发送状态查询原始帧：

```bash
ros2 run stm32_jetson_serial_comm serial_link \
  --device /dev/ttyACM0 \
  --baudrate 115200 \
  --send-hex "AA 55 01 01 10 0E" \
  --read-seconds 3
```

如需验证 UART5 备用口，可先短接 Jetson 串口 TX/RX：

```bash
ros2 run stm32_jetson_serial_comm serial_link \
  --device /dev/ttyACM0 \
  --baudrate 115200 \
  --loopback-test
```

正常响应示例：

```text
RX 12 bytes: AA 55 81 07 10 ... CRC
```

## Jetson 端业务查询

综合状态、GPIO 和超声波查询仍使用原有命令；CS1237 的完整流程见下一节。

## WS2812B RGB

STM32 的 `PB13` 驱动三颗 DIN 到 DOUT 级联的 WS2812B，主机仍按一个逻辑像素控制，
固件向三颗灯发送相同颜色，因此三颗灯始终同步。设备上电默认绿色 `#00FF00`、
25% 亮度、1 Hz 慢闪；RGB 设置
仅保存在 STM32 RAM，复位后恢复默认值。

| 帧 | ID | payload |
| --- | --- | --- |
| 设置 | `0x0C` | `seq + red + green + blue + brightness + mode` |
| 设置响应 | `0x8C` | `seq + result` |
| 查询 | `0x0D` | `seq` |
| 状态响应 | `0x8D` | `seq + red + green + blue + brightness + mode + output_on` |

`brightness` 范围为 0..100，`mode` 为 0 关闭、1 常亮、2 慢闪（1 Hz）、3 中闪
（2 Hz）、4 快闪（约 4 Hz）；`output_on` 表示当前亮/灭相位。Python 包提供
`set_rgb()` 与 `query_rgb()`，输入参数在写串口前校验。

当前原理图没有 PB13 的 3.3 V -> 5 V 电平转换。实板应先示波器验收 800 kHz
波形、0/1 高电平宽度与至少 100 us 的复位低电平；若信号余量不稳定，增加
`74AHCT`/`74HCT` 电平转换缓冲器后再继续调试。

## CS1237 ADC 使用

### 通道和数据

| CLI 名称 | channel | 数据解释 |
| --- | --- | --- |
| `cha` / `force` | `0` | 差分输入；完成两点标定后输出牛顿 |
| `temp` / `temperature` | `2` | 内部温度；完成单点标定后输出摄氏度 |
| `ins` | `3` | 内部短接诊断；只输出原始 ADC |

STM32 返回 `raw_adc`、`channel`、`valid` 和 `error`。Jetson 仅在
`valid=yes` 时换算物理量；`error=0` 表示采样正常。

### 查询和切换

切换到内部温度通道并等待约 0.4 秒建立：

```bash
ros2 run stm32_jetson_serial_comm serial_link \
  --device /dev/ttyACM0 --cs1237-set-channel temp --read-seconds 3
sleep 1
```

查询原始值和摄氏温度：

```bash
ros2 run stm32_jetson_serial_comm serial_link \
  --device /dev/ttyACM0 --cs1237-query --read-seconds 3
```

正常输出示例：

```text
CS1237 channel=TEM raw=593359 valid=yes error=0 temperature=26.00 C
```

### 温度单点标定

CS1237 手册要求内部温度传感器进行单点校准，不能直接复用另一块板的 ADC
码值。在已知环境温度且原始值稳定时执行：

```bash
ros2 run stm32_jetson_serial_comm serial_link \
  --device /dev/ttyACM0 --cs1237-calibrate-temperature 26 --read-seconds 3
```

温度换算采用手册公式：

```text
T = raw_adc * (273.15 + reference_temperature_c) / reference_adc - 273.15
```

### 力通道两点标定

先切换到差分通道，空载记录零点，再加载已知力记录量程点：

```bash
ros2 run stm32_jetson_serial_comm serial_link \
  --device /dev/ttyACM0 --cs1237-set-channel cha --read-seconds 3
sleep 1
ros2 run stm32_jetson_serial_comm serial_link \
  --device /dev/ttyACM0 --cs1237-calibrate-zero --read-seconds 3
ros2 run stm32_jetson_serial_comm serial_link \
  --device /dev/ttyACM0 --cs1237-calibrate-force 10 --read-seconds 3
```

上例的已知载荷为 `10 N`。未完成标定时查询会显示
`force=UNCALIBRATED`，不会输出伪造的力值。

### 标定文件

温度与力标定参数保存在：

```text
~/.config/stm32_jetson_serial_comm/cs1237_calibration.json
```

写入采用临时文件加原子替换。删除该文件即可恢复默认温度参考值并清除力标定。

综合状态：

```bash
ros2 run stm32_jetson_serial_comm serial_link \
  --device /dev/ttyACM0 \
  --baudrate 115200 \
  --query-status \
  --seq 0x10 \
  --read-seconds 3
```

返回示例：

```text
STM32 status: seq=0x10 tick=12345 status=OK(0x00) app_gpio=0x03
```

GPIO 状态：

```bash
ros2 run stm32_jetson_serial_comm serial_link \
  --device /dev/ttyACM0 \
  --baudrate 115200 \
  --query-gpio \
  --seq 0x12 \
  --read-seconds 3
```

返回示例：

```text
STM32 GPIO: seq=0x12 bitmap=0x08 outputs=[flash_ctr=OFF, led=OFF, bee=OFF, motor=ON, flash=OFF, sound=OFF]
```

超声波距离：

```bash
ros2 run stm32_jetson_serial_comm serial_link \
  --device /dev/ttyACM0 \
  --baudrate 115200 \
  --query-ultrasonic \
  --seq 0x13 \
  --read-seconds 3
```

返回示例：

```text
STM32 ultrasonic: seq=0x13 front=0mm(TIMEOUT) left=0mm(TIMEOUT) right=0mm(TIMEOUT)
```

## UM982 RTK 透传

UM982 使用 STM32 USART6：PC6 TX 接模块 RXD，PC7 RX 接模块 TXD，双方共地。
串口参数为模块默认的 `115200 8N1`。`stm32_rtk` 经 USB CDC 的应用协议分帧
传输，不会把 NMEA 文本与 GPIO、ADC 等业务响应混在一起。

开启 GGA 并读取 3 秒响应：

```bash
ros2 run stm32_jetson_serial_comm stm32_rtk \
  --device /dev/ttyACM0 \
  --send-text "GPGGA 1" \
  --read-seconds 3
```

保存配置：

```bash
ros2 run stm32_jetson_serial_comm stm32_rtk \
  --device /dev/ttyACM0 \
  --send-text "saveconfig" \
  --read-seconds 1
```

持续输出 NMEA 原始字节：

```bash
ros2 run stm32_jetson_serial_comm stm32_rtk \
  --device /dev/ttyACM0 --listen
```

正常定位时可看到 `$GPGGA` 或 `$GNGGA`。关闭 GGA：

```bash
ros2 run stm32_jetson_serial_comm stm32_rtk \
  --device /dev/ttyACM0 --send-text "unlog gpgga"
```

发送 RTCM 或其他二进制数据：

```bash
ros2 run stm32_jetson_serial_comm stm32_rtk \
  --device /dev/ttyACM0 --send-hex "D3 00 00 ..."
```

`--send-text` 自动补一个 `CRLF`；`--send-hex` 不修改数据。RTCM 是二进制，
直接作为终端文本查看出现乱码属于正常现象。STM32 接收缓冲区溢出时工具会明确
报错，提示 Jetson 需要更快轮询。

验证透传未影响其他业务：

```bash
ros2 run stm32_jetson_serial_comm serial_link \
  --device /dev/ttyACM0 --query-status --read-seconds 3
```

## Jetson 端 GPIO 控制

现场手动控制 GPIO 推荐使用短命令 `stm32_gpio`：

```bash
ros2 run stm32_jetson_serial_comm stm32_gpio led on
ros2 run stm32_jetson_serial_comm stm32_gpio led off
ros2 run stm32_jetson_serial_comm stm32_gpio motor on
ros2 run stm32_jetson_serial_comm stm32_gpio bee off
```

默认应用通信口为 `/dev/ttyACM0`，默认波特率为 `115200`。可用 `STM32_SERIAL_DEVICE` 改默认设备，或通过 `--device` 临时指定：

```bash
export STM32_SERIAL_DEVICE=/dev/ttyTHS0
ros2 run stm32_jetson_serial_comm stm32_gpio sound on
ros2 run stm32_jetson_serial_comm stm32_gpio sound on --device /dev/ttyACM0
```

可用通道名：

| 通道名       | STM32 信号           | channel_id |
| ------------ | -------------------- | ---------- |
| `flash_ctr`  | `SIGNAL-FLASH-CTR`    | `0x01`     |
| `led`        | `SIGNAL-LED`         | `0x02`     |
| `bee`        | `SIGNAL-BEE`         | `0x03`     |
| `motor`      | `SIGNAL-MOTOR`       | `0x04`     |
| `flash`      | `SIGNAL-FLASH`        | `0x05`     |
| `sound`      | `SIGNAL-SOUND`       | `0x06`     |

输出状态支持 `on/off`、`high/low` 和 `1/0`。成功响应示例：

```text
GPIO led -> ON: OK(0x00)
```

ROS 节点运行时也提供 `std_srvs/srv/SetBool` 服务，适合其他 ROS 节点调用：

```bash
ros2 service call /stm32/gpio/led/set std_srvs/srv/SetBool "{data: true}"
ros2 service call /stm32/gpio/motor/set std_srvs/srv/SetBool "{data: false}"
```

服务列表：

| Service                         | 说明                 |
| ------------------------------- | -------------------- |
| `/stm32/gpio/flash_ctr/set`     | 控制 `flash_ctr`     |
| `/stm32/gpio/led/set`           | 控制 `led`           |
| `/stm32/gpio/bee/set`           | 控制 `bee`           |
| `/stm32/gpio/motor/set`         | 控制 `motor`         |
| `/stm32/gpio/flash/set`         | 控制 `flash`         |
| `/stm32/gpio/sound/set`         | 控制 `sound`         |

## Jetson 端 Bootloader 升级

Bootloader 返回的应用区上限为 352 KiB。Sector 7 保存 App 有效元数据，不属于固件镜像。
主动状态帧 `0x92` 的 8 字节 payload 为
`state + app_valid + last_error + reserved + received_bytes(uint32 小端)`；协议客户端等待
`INFO/ACK` 时会分流状态帧，不会让心跳打断升级响应。

构建 STM32 应用固件后，`make -C STM32 app` 会自动将 `build/app/DM3.1_BAT_app.bin` 覆盖到本包的固件目录：

```text
Linux_ROS_WS/src/stm32_jetson_serial_comm/firmware/DM3.1_BAT_app.bin
```

执行 `Linux_ROS_WS/scripts/sync_to_jetson.sh` 时，该固件会随 `Linux_ROS_WS/src/` 一起同步到 Jetson。

若 STM32 正在运行应用，可先发送带密码的 bootloader 请求。工具会先以应用波特率 `115200` 发送 `0x05` 请求帧，payload 为 `seq + wb88`，等待 STM32 软件复位后，再以 bootloader 波特率 `460800` 开始升级：

```bash
ros2 run stm32_jetson_serial_comm stm32_bootloader \
  /home/jetson/ros_ws/src/stm32_jetson_serial_comm/firmware/DM3.1_BAT_app.bin \
  --device /dev/ttyACM0 \
  --request-from-app
```

如果 STM32 已经处于 bootloader 中，可直接升级：

```bash
ros2 run stm32_jetson_serial_comm stm32_bootloader \
  /home/jetson/ros_ws/src/stm32_jetson_serial_comm/firmware/DM3.1_BAT_app.bin \
  --device /dev/ttyACM0 \
  --baudrate 460800
```

首次只通过 SWD 写入 Bootloader、尚无有效 App 时，也使用上述直接升级命令，不添加
`--request-from-app`。若升级在擦除、写入或校验阶段失败，设备会保持 Bootloader；修复
连接或固件文件后重新发起完整升级即可。不要只发送 JUMP，也不要通过 SWD 补写 App。

默认流程为：

```text
HELLO -> START -> ERASE -> WRITE -> VERIFY -> JUMP
```

`START` 不破坏旧 App；`ERASE` 先使元数据失效。只有 `VERIFY` 完成镜像 CRC、向量表和
元数据提交后 App 才重新有效。`VERIFY` 成功但尚未 `JUMP` 时发生复位，已验证 App 可在
下次启动。

只校验后留在 bootloader：

```bash
ros2 run stm32_jetson_serial_comm stm32_bootloader \
  /home/jetson/ros_ws/src/stm32_jetson_serial_comm/firmware/DM3.1_BAT_app.bin \
  --device /dev/ttyACM0 \
  --no-jump
```

校验后复位 MCU：

```bash
ros2 run stm32_jetson_serial_comm stm32_bootloader \
  /home/jetson/ros_ws/src/stm32_jetson_serial_comm/firmware/DM3.1_BAT_app.bin \
  --device /dev/ttyACM0 \
  --reset-after-verify
```

常用参数：

| 参数                 | 默认值          | 说明                                  |
| -------------------- | --------------- | ------------------------------------- |
| `--device`           | `/dev/ttyACM0`  | bootloader 设备，可用 `STM32_BOOTLOADER_DEVICE` 覆盖 |
| `--baudrate`         | `460800`        | bootloader 升级阶段波特率             |
| `--app-baudrate`     | `115200`        | `--request-from-app` 阶段应用波特率   |
| `--erase-timeout`    | `10.0`          | Flash 擦除等待时间                    |
| `--write-chunk-size` | `245`           | 单帧写入数据长度                      |

## Jetson 端 ROS2 节点

启动周期查询节点：

```bash
ros2 run stm32_jetson_serial_comm stm32_serial_node
```

也可以使用 launch 文件启动，默认参数已固化为 Jetson 端常用配置：

```bash
ros2 launch stm32_jetson_serial_comm stm32_serial.launch.py
```

覆盖串口或轮询频率：

```bash
ros2 launch stm32_jetson_serial_comm stm32_serial.launch.py \
  device:=/dev/ttyACM0 \
  ultrasonic_rate_hz:=5.0
```

默认参数：

| 参数                  | 默认值          |
| --------------------- | --------------- |
| `device`              | `/dev/ttyACM0`  |
| `baudrate`            | `115200`        |
| `status_rate_hz`      | `0.5`           |
| `gpio_status_rate_hz` | `1.0`           |
| `ultrasonic_rate_hz`  | `5.0`           |
| `timeout`             | `0.2`           |
| `query_gpio`          | `true`          |
| `query_ultrasonic`    | `true`          |
| `cs1237_rate_hz`      | `10.0`          |

覆盖参数：

```bash
ros2 run stm32_jetson_serial_comm stm32_serial_node --ros-args \
  -p device:=/dev/ttyACM0 \
  -p baudrate:=115200 \
  -p status_rate_hz:=0.5 \
  -p gpio_status_rate_hz:=1.0 \
  -p ultrasonic_rate_hz:=5.0 \
  -p cs1237_rate_hz:=10.0 \
  -p timeout:=0.2
```

节点内部使用独立定时器：综合状态 0.5Hz，GPIO 状态 1Hz，超声波 5Hz，
CS1237 10Hz。所有任务共用串口锁；轮询拿不到锁时跳过本轮，避免响应帧交叉。

发布 topic：

| Topic                    | 类型                       | 内容                                                         |
| ------------------------ | -------------------------- | ------------------------------------------------------------ |
| `/stm32/status_text`     | `std_msgs/String`          | 人眼可读的 STM32 综合状态摘要                                |
| `/stm32/gpio_text`       | `std_msgs/String`          | 人眼可读的 GPIO 通道状态摘要                                 |
| `/stm32/gpio_bitmap`     | `std_msgs/UInt8`           | 程序可读的 GPIO 输出状态位图                                 |
| `/stm32/ultrasonic_text` | `std_msgs/String`          | 人眼可读的超声波距离和有效/错误位图摘要                      |
| `/stm32/ultrasonic_mm`   | `std_msgs/Int32MultiArray` | 程序可读的 `[front, left, right, valid_bitmap, error_bitmap]` |
| `/stm32/cs1237_raw`      | `std_msgs/Int32`           | CS1237 最新有符号原始 ADC                                    |
| `/stm32/cs1237_text`     | `std_msgs/String`          | 通道、有效性、错误和温度/力换算摘要                          |
| `/stm32/link_ok`         | `std_msgs/Bool`            | 最近一次轮询是否成功                                         |

查看输出：

```bash
ros2 topic echo /stm32/status_text
ros2 topic echo /stm32/gpio_text
ros2 topic echo /stm32/gpio_bitmap
ros2 topic echo /stm32/ultrasonic_text
ros2 topic echo /stm32/ultrasonic_mm
ros2 topic echo /stm32/cs1237_raw
ros2 topic echo /stm32/cs1237_text
ros2 topic echo /stm32/fan_rpm
ros2 topic echo /stm32/fan_level
ros2 topic echo /stm32/key_bitmap
ros2 topic echo /stm32/board_io_text
ros2 topic echo /stm32/link_ok
```

文本 topic 示例：

```text
STM32 status: seq=0x00 tick=12345 status=OK(0x00) app_gpio=0x03
STM32 GPIO: seq=0x01 bitmap=0x21 outputs=[flash_ctr=ON, led=OFF, bee=OFF, motor=OFF, flash=OFF, sound=ON]
STM32 ultrasonic: seq=0x02 front=1000mm(OK) left=2000mm(OK) right=0mm(NO_TARGET)
CS1237 channel=2 raw=593359 valid=yes error=0 temperature=26.00 C
STM32 board IO: seq=0x03 fan_level=2 fan1=3000rpm fan2=3100rpm keys=0x01
```

风扇上电默认为 2 档（50%），Jetson 可设置 1/2/3/4 档，分别对应
25%/50%/75%/100%：

```bash
ros2 run stm32_jetson_serial_comm stm32_fan set 3
ros2 run stm32_jetson_serial_comm stm32_fan status
```

只查询综合状态：

```bash
ros2 run stm32_jetson_serial_comm stm32_serial_node --ros-args \
  -p query_gpio:=false \
  -p query_ultrasonic:=false
```

## Jetson 端调试速查

以下调试命令均在 Jetson 上执行。

监听串口：

```bash
ros2 run stm32_jetson_serial_comm serial_link \
  --device /dev/ttyACM0 \
  --baudrate 115200 \
  --listen
```

发送任意十六进制数据：

```bash
ros2 run stm32_jetson_serial_comm serial_link \
  --device /dev/ttyACM0 \
  --baudrate 115200 \
  --send-hex "AA 55 01 01 10 0E" \
  --read-seconds 3
```

检查串口是否被占用：

```bash
sudo lsof /dev/ttyACM0
sudo lsof /dev/ttyTHS0
sudo systemctl status serial-getty@ttyTHS0.service
```

运行包内单元测试：

```bash
cd ~/ros_ws/src/stm32_jetson_serial_comm
python3 -m unittest discover -s tests -v
```

只运行 ADC 相关测试：

```bash
python3 -m unittest tests/test_cs1237.py tests/test_messages.py tests/test_serial_host.py -v
```

## 协议参考

STM32 UART5 应用协议、bootloader 协议、Flash 分区、固件生成和烧录说明统一维护在仓库根目录的：

```text
STM32/README.md
```
