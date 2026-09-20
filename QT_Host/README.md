# DM3.1 Qt 调试上位机

内部研发工具，通过 USB CDC 直连一块 DM3.1 STM32，支持状态监控、实时曲线、
GPIO/风扇/CS1237/WS2812B RGB 控制、CSV 记录和固件升级。

## 目录边界

Qt 源码、测试和部署配置全部位于本 `QT_Host/` 子工程。通信协议和 bootloader
继续复用：

```text
Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/
```

## macOS 开发运行

```sh
cd QT_Host
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

macOS USB CDC 通常显示为 `/dev/cu.usbmodem*`。

## Windows 运行与打包

```powershell
cd QT_Host
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
pyside6-deploy -c pysidedeploy.spec
```

设备显示为 `COMx`。Windows 可执行产物必须在 Windows 上构建和实测。

## Linux 运行与打包

```sh
cd QT_Host
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
pyside6-deploy -c pysidedeploy.spec
```

设备通常显示为 `/dev/ttyACM*`，用户需要具有相应串口权限。Linux 产物必须
在目标 Linux 发行版或兼容 CI 环境中构建和实测。

## 使用

1. 连接 STM32 USB，刷新并选择串口。
2. 点击“连接”，在总览、曲线和控制页调试应用协议。
3. 控制页可分别启停状态、GPIO、超声波、CS1237、板载 IO 和 RGB 状态轮询，并调整
   轮询频率与串口响应超时；重新启用后立即查询一次，关闭时界面保留最近一次数据。
4. 点击“开始 CSV”保存带各数据源采样时间的遥测快照。
5. 在固件页选择 `DM3.1_BAT_app.bin`；通常保持“从运行态请求进入
   bootloader”选中，再开始升级。

App 镜像最大为 352 KiB。首次只用 SWD 写入 Bootloader，或设备因升级失败停留在
Bootloader 时，Qt 会在连接后自动识别 Bootloader，并显示 `WAITING/RECEIVING/VERIFIED/ERROR`、
App 有效性、最近错误和已接收字节数。此时取消勾选“从运行态请求进入 bootloader”，直接
开始升级。

轮询开关、轮询频率、串口超时和三组曲线 Y 轴范围会保存到当前用户的系统配置中，并在下次启动时自动恢复；串口、固件路径和临时显示状态不会保存。

升级自动使用应用 115200 baud、bootloader 460800 baud。升级期间普通轮询
和控制暂停。升级失败后保留 Bootloader 连接、状态和日志，不自动重复写入；排除原因后
再次点击“开始升级”即可重新发起完整升级。
日志包含串口 TX/RX、帧 ID 和原始十六进制数据，可保存为 `.log` 或 `.txt`。

### GPIO 与 RTK

总览页分别显示六路 GPIO：爆闪切换、照明、蜂鸣器、导盲杆马达、红蓝爆闪和声音功放；
每路状态为“开启”、“关闭”或未取得数据时的“--”。
控制页的“爆闪切换”使用 200 ms 触发按钮，脉宽由 STM32 固件保证；其余五路 GPIO
仍为持续电平开关。

实时曲线页可分别设置风扇、超声波和 CS1237 三张图的整数 Y 轴上下限。

RTK 通过 CH343P 独立串口直连，不依赖 STM32 是否已连接。顶部选择 RTK 串口和
`115200` 或 `921600` 波特率后单独连接。ASCII 输入按文本命令发送，HEX 输入可使用空格、
逗号或 `0x` 前缀分隔字节。接收区可切换“文本”（ASCII，无法解码的字节显示为替代字符）
和“HEX”。“暂停显示”只停止界面刷新，数据仍持续接收；恢复显示或切换显示模式时会渲染
最新缓存。缓存仅保留最新 64 KiB（65,536 字节），超出部分会从最早数据开始丢弃。

RTK 功能必须在真实 CH343P/UM982 板上验收：持续接收、ASCII/HEX 发送、921600bps
吞吐量，以及与 STM32 轮询和固件升级并存。离屏测试不验证真实串口吞吐量。

### RGB 灯

“RGB 灯”页控制 PB13 上的一组三颗级联 WS2812B（一个逻辑像素，三颗同步同色）。固件
上电默认绿色 `#00FF00`、25% 亮度、1 Hz 慢闪。基础色预设为红、绿、蓝、白、黄、青、紫、
橙；马卡龙预设为樱花粉 `#FFB7C5`、蜜桃橙 `#FFCBA4`、奶油黄 `#FFF1A8`、薄荷绿
`#B8E8D0`、湖水蓝 `#A7D8F0`、薰衣草紫 `#C8B6E2`、杏仁米 `#E8D5C4`、珊瑚粉
`#FF9AA2`，共 16 个预设。

点击预设或“自定义颜色”只修改编辑器；必须点击“应用”才发送 `0x0C` 设置帧并等待
`0x8C` 响应。可选
关闭、常亮、慢闪（1 Hz）、中闪（2 Hz）或快闪（约 4 Hz），并设置 0..100% 亮度。
“实际状态”显示设备经 `0x0D`/`0x8D` 回读的颜色、亮度、模式和当前亮/灭相位；勾选
“启用状态回读”才会轮询。控制页的“RGB 状态 Hz”单独设置回读频率，默认 2 Hz。

RGB 编辑值、回读开关与频率通过 QSettings 保存，并在下次启动恢复；恢复配置不会
自动向 STM32 发送颜色，避免打开工具时改变正在运行的灯效。固件 RGB 设置本身仍为
RAM 设置，STM32 复位后恢复默认值。

当前原理图没有 PB13 的 3.3 V -> 5 V 电平转换。连接实板前后应使用示波器验收
800 kHz 位周期、0/1 高电平宽度和至少 100 us 的复位低电平，并检查三颗灯同步、16 个
预设、0/25/100% 亮度、五种模式、回读开关与持续 USB CDC 通信；若波形或高电平余量
不稳定，须增加 `74AHCT`/`74HCT` 电平转换缓冲器，不应继续靠软件调参。

## 测试

```sh
PYTHONPATH=.:../Linux_ROS_WS/src/stm32_jetson_serial_comm \
QT_QPA_PLATFORM=offscreen \
python -m unittest discover -s tests

PYTHONPATH=.:../Linux_ROS_WS/src/stm32_jetson_serial_comm \
QT_QPA_PLATFORM=offscreen \
python main.py --smoke-test
```

离屏测试不能替代以下验收：Windows/Linux USB CDC 拔插、真实固件升级、
30 分钟曲线稳定性，以及打包产物在无源码目录中启动。
