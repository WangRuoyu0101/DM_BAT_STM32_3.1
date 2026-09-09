# DM3.1 Qt 总览 GPIO 与 RTK 调试页设计

日期：2026-07-22

## 目标

在现有 `QT_Host/` 子工程中完成两项改动：

- 总览页不再显示 GPIO 位图，改为分别显示六路 GPIO 的实际状态；
- 新增一个 RTK 调试页，支持 UM982 文本和二进制数据收发。

不新增串口连接、后台进程或通信协议实现。

## 总览 GPIO

沿用现有 `GPIO_CHANNELS` 顺序和 `Telemetry.gpio_bitmap`，分别显示：爆闪切换、
照明、蜂鸣器、导盲杆马达、红蓝爆闪、声音功放。未收到状态时显示 `--`，位为
1 时显示“开启”，位为 0 时显示“关闭”。控制页现有 GPIO 开关保持不变。

## RTK 数据流

继续由现有 `SerialWorker` 独占 USB 串口，并在应用模式下创建已有的
`RtkBridge`。普通查询、RTK 读取、RTK 发送和固件升级均在同一工作线程串行
执行，避免响应串包。断开或升级时停止 RTK 操作。

RTK 默认每 50 ms 尝试读取一次。暂停显示只让界面丢弃新显示内容，工作线程
仍持续排空 STM32 RTK 缓冲区，避免因界面暂停造成溢出。

## RTK 页面

主窗口增加第五个“RTK”页，包含：

- ASCII 命令输入与发送，复用 `encode_text_command()` 自动补 `CRLF`；
- HEX 输入与发送，复用 `parse_hex_bytes()` 校验并转换；
- 文本/HEX 接收显示模式；
- 暂停显示与清空；
- RTK 接收区和错误提示。

接收区只保留最近 64 KiB 原始字节，超出后删除最旧数据，再根据当前显示模式
刷新。文本模式使用 ASCII 解码并以替换字符处理非文本字节；HEX 模式使用空格
分隔的大写字节。输入为空、HEX 非法、未连接、RTK 缓冲区溢出或协议异常均在
现有日志/命令结果机制中显示，不静默失败。

## 复用与接口

复用现有：

- `stm32_jetson_serial_comm.rtk_bridge.RtkBridge`；
- `stm32_jetson_serial_comm.rtk_cli.encode_text_command`；
- `stm32_jetson_serial_comm.serial_link_cli.parse_hex_bytes`；
- `SerialWorker` 的单串口线程、状态和日志信号。

只在 `SerialWorker` 增加 RTK 接收信号和文本/HEX 发送槽，不增加新线程或新协议
类。RTK 读取加入现有基于单调时钟的轮询调度，每个定时器 tick 仍最多执行一个
请求。

## 测试

最小回归检查包括：

1. GPIO 位图能正确映射为六个独立状态，未知状态保持 `--`；
2. 主窗口包含第五个“RTK”页及必要控件；
3. ASCII 发送补 `CRLF`，HEX 发送使用现有解析器；
4. RTK 收到的原始字节通过信号交给界面，文本/HEX 模式显示正确；
5. 显示缓存最多保留最近 64 KiB；
6. RTK 溢出或异常不影响其他串口状态，并产生可见错误；
7. 原有 Qt、Jetson/协议和 STM32 测试继续通过。

真实 UM982 连续数据、STM32 缓冲区压力及 Windows/Linux USB 行为仍需硬件验收。
