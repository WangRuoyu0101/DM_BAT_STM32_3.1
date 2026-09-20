# DM3.1_BAT STM32 工程说明

本文档是 `STM32/` 工程的统一入口，汇总应用固件、USB CDC/UART5 通信、UART5 bootloader、编译、烧录和调试流程。

## 目录

- [工程概览](#工程概览)
- [目录结构](#目录结构)
- [工具链准备](#工具链准备)
- [编译](#编译)
- [烧录](#烧录)
- [调试](#调试)
- [Flash 分区与启动流程](#flash-分区与启动流程)
- [CS1237 ADC](#cs1237-adc)
- [WS2812B RGB 灯](#ws2812b-rgb-灯)
- [UART5 应用通信协议](#uart5-应用通信协议)
- [USB CDC/UART5 Bootloader 协议](#usb-cdcuart5-bootloader-协议)
- [Jetson 端升级配合](#jetson-端升级配合)
- [测试](#测试)
- [常见问题](#常见问题)
- [参考文档](#参考文档)

## 工程概览

本工程面向 STM32F407VETx，使用 Makefile 和 ARM GCC 构建。当前包含两套镜像：

| 镜像 | 地址 | 说明 |
| --- | --- | --- |
| Bootloader | `0x08000000` | USB CDC/UART5 升级引导程序，占用 Flash 前 32 KB |
| Application | `0x08008000` | 主应用固件，最大 352 KiB |
| App metadata | `0x08060000` | Sector 7，有效标志、镜像长度和 CRC32 |

主应用默认通过 USB CDC 虚拟串口作为 Jetson 的从机节点，同时保留 UART5 同协议入口，支持状态查询、GPIO 控制、GPIO 状态查询、超声波距离汇总、CS1237 ADC 采样/通道切换，以及运行态进入 bootloader 的请求。

当前默认接口和参数：

- 应用业务通信默认走 USB CDC `/dev/ttyACM0`，UART5 作为备用同协议入口。
- Bootloader 升级默认走 USB CDC `/dev/ttyACM0`，UART5 可作为备用设备。
- `BOOTLOADER_LED_TOGGLE_PERIOD_MS` 当前为 `75U`，bootloader 升级态运行灯每 75 ms 翻转一次。

## CS1237 ADC

### 硬件连接

| CS1237 | STM32 | 方向 | 说明 |
| --- | --- | --- | --- |
| `SCLK` | PB14 | STM32 输出 | GPIO 模拟时钟，空闲为低 |
| `DOUT/DRDY` | PD8 | 双向 | 平时输入；写配置寄存器时临时切为推挽输出 |
| `VCC` | 3.3V | 电源 | 与 STM32 使用相同逻辑电平 |
| `GND` | GND | 电源 | 必须共地 |

PB14、PD8 不使用 SPI/DMA。10 Hz 下每次只需读取 24 bit，
主循环轮询 `DOUT/DRDY`，仅在其拉低时执行短暂 GPIO 时序，不等待转换完成。

### 驱动接口

驱动位于 `Core/Inc/app_cs1237.h` 和 `Core/Src/app_cs1237.c`：

```c
App_CS1237_Result App_CS1237_Init(void);
void App_CS1237_Run(void);
App_CS1237_Result App_CS1237_SetChannel(App_CS1237_Channel channel);
void App_CS1237_GetSnapshot(App_CS1237_Snapshot *snapshot);
```

应用默认选择内部温度通道、10 Hz、PGA1、REF 输出开启；差分输入和内部短接
使用 PGA128。切换通道后旧快照立即失效，建立阶段结束后才重新置 `valid=1`。
原始 ADC 为 24 位二进制补码，固件将其符号扩展为 `int32_t`。

| channel | 枚举 | 用途 | PGA |
| --- | --- | --- | --- |
| `0` | `APP_CS1237_CHANNEL_DIFFERENTIAL` | 差分输入/力传感器 | 128 |
| `1` | `APP_CS1237_CHANNEL_RESERVED` | 芯片保留，不允许选择 | - |
| `2` | `APP_CS1237_CHANNEL_TEMPERATURE` | 芯片内部温度 | 1 |
| `3` | `APP_CS1237_CHANNEL_INTERNAL_SHORT` | 内部短接诊断 | 128 |

### 快照和错误

`App_CS1237_Snapshot` 包含 `raw_adc`、`channel`、`valid` 和 `error`。

| error/result | 含义 |
| --- | --- |
| `0` | 正常 |
| `1` | 通道非法 |
| `2` | 等待 `DOUT/DRDY` 超时 |
| `3` | 配置寄存器回读校验失败 |

STM32 只负责输出原始 ADC；温度、力值换算和标定参数均由 Jetson 保存和处理。

| 帧 | ID | payload |
| --- | --- | --- |
| CS1237 查询 | `0x06` | `seq` |
| CS1237 查询响应 | `0x86` | `seq + raw_adc(int32 LE) + channel + valid + error` |
| CS1237 切换通道 | `0x07` | `seq + channel` |
| CS1237 切换响应 | `0x87` | `seq + channel + result` |

## 目录结构

```text
STM32/
  Bootloader/                 USB CDC/UART5 bootloader 工程源码
  Core/                       主应用源码和公共模块
    Inc/app_cs1237.h          CS1237 接口、通道、快照和错误定义
    Src/app_cs1237.c          PB14/PD8 GPIO 时序与周期采样
  Drivers/                    STM32 HAL/CMSIS 驱动
  Middlewares/                USB Device 中间件
  USB_DEVICE/                 USB CDC 配置
  docs/                       专题文档和历史设计文档
  tests/                      Python 文本/结构测试
  Makefile                    主构建入口
  STM32F407XX_APP_FLASH.ld    主应用链接脚本，起始地址 0x08008000
  STM32F407XX_BOOT_FLASH.ld   bootloader 链接脚本，起始地址 0x08000000
```

## WS2812B RGB 灯

`PB13`（`RGB_Pin`）以 GPIO 时序驱动 WS2812B。外部灯板上的三颗灯按 DIN 到 DOUT 级联，
但它们是一个逻辑像素：三颗灯始终显示相同颜色，固件连续发送三组相同的 24 bit GRB 数据。
上电默认绿色 `#00FF00`、25% 亮度、1 Hz 慢闪（初始为亮相位）。
设置只保存在 RAM，复位后恢复此默认值。
上位机颜色按 sRGB 输入；固件发送前使用 gamma≈2 的整数近似转换为线性 PWM，
避免马卡龙等低饱和度颜色在透明高亮灯珠上全部趋近白色。状态回读仍返回原始 sRGB 值。

| mode | 显示 |
| --- | --- |
| `0` | 关闭 |
| `1` | 常亮 |
| `2` | 慢闪，1 Hz |
| `3` | 中闪，2 Hz |
| `4` | 快闪，约 4 Hz |

发送一帧时会短暂屏蔽中断以保持 WS2812B 波形；固件使用 DWT 周期计数器产生
800 kHz 标称时序。`docs/RGB手册.pdf` 要求 0 码高电平不超过 410 ns，固件目标值为
200 ns，以留出 GPIO 和函数执行开销；1 码目标值为 550 ns，复位低电平配置为 125 us。
当前原理图没有 `PB13` 的 3.3 V -> 5 V 电平转换。先在实板上
用示波器确认逻辑高电平和波形余量；若不稳定，停止软件调参并在 PB13 与灯带之间
增加 `74AHCT`/`74HCT` 电平转换缓冲器。

实机验收还需检查：800 kHz 标称位周期、0/1 不同高电平宽度、复位低电平至少
100 us、三颗灯同步变化、16 个预设、0/25/100% 亮度、五种模式、RGB 回读开关，
以及持续 USB CDC 通信。

## 工具链准备

工程优先查找本地工具链：

```text
STM32/toolchains/arm-none-eabi-15.2/bin/arm-none-eabi-gcc
```

如果没有本地工具链，需要确保以下命令可在 `PATH` 中找到：

```sh
arm-none-eabi-gcc
arm-none-eabi-objcopy
arm-none-eabi-size
arm-none-eabi-gdb
openocd
```

默认下载/调试器为 CMSIS-DAP，OpenOCD 默认参数来自 `Makefile`：

```text
interface/cmsis-dap.cfg
target/stm32f4x.cfg
transport swd
adapter speed 2000
```

如需调整调试器速度，可在命令行覆盖：

```sh
make -C STM32 OPENOCD_ADAPTER_SPEED=4000 flash
```

## 编译

所有命令默认在仓库根目录执行。

### 编译主应用

```sh
make -C STM32 app
```

输出文件：

```text
STM32/build/app/DM3.1_BAT_app.elf
STM32/build/app/DM3.1_BAT_app.hex
STM32/build/app/DM3.1_BAT_app.bin
```

编译主应用后，`Makefile` 会自动把应用 bin 覆盖到 Jetson ROS2 包固件目录：

```text
Linux_ROS_WS/src/stm32_jetson_serial_comm/firmware/DM3.1_BAT_app.bin
```

该目录中的生成固件由 `.gitignore` 排除，不提交到 Git。

### 编译 bootloader

```sh
make -C STM32 bootloader
```

输出文件：

```text
STM32/build/bootloader/DM3.1_BAT_bootloader.elf
STM32/build/bootloader/DM3.1_BAT_bootloader.hex
STM32/build/bootloader/DM3.1_BAT_bootloader.bin
```

### 默认编译

```sh
make -C STM32
```

当前默认目标是 `app`。

### 清理

```sh
make -C STM32 clean
```

## 烧录

### 烧录主应用

`make flash` 只会构建并烧录主应用，地址由 `STM32F407XX_APP_FLASH.ld` 决定，即 `0x08008000`。

```sh
make -C STM32 flash
```

等价 OpenOCD 命令：

```sh
cd STM32
openocd -f interface/cmsis-dap.cfg \
  -c "transport select swd" \
  -f target/stm32f4x.cfg \
  -c "adapter speed 2000" \
  -c "program build/app/DM3.1_BAT_app.elf verify reset exit"
```

注意：只烧录主应用不会更新 `0x08000000` 的 bootloader。如果板子复位后仍从旧 bootloader 启动，应用行为可能不会按最新代码变化。

### 只烧录 bootloader

```sh
cd STM32
openocd -f interface/cmsis-dap.cfg \
  -c "transport select swd" \
  -f target/stm32f4x.cfg \
  -c "adapter speed 2000" \
  -c "program build/bootloader/DM3.1_BAT_bootloader.elf verify reset exit"
```

bootloader 链接到 `0x08000000`，烧录该 ELF 不会覆盖 `0x08008000` 之后的主应用区。

### 全片擦除

```sh
make -C STM32 erase
```

该命令会执行 STM32F4 mass erase，会清空 bootloader、application 和元数据。擦除后先通过 SWD 重新烧录 bootloader，再通过 bootloader 安装应用。

### 首次部署建议顺序

```sh
make -C STM32 bootloader
make -C STM32 app
```

只通过 SWD 烧录 bootloader：

```sh
cd STM32
openocd -f interface/cmsis-dap.cfg -c "transport select swd" -f target/stm32f4x.cfg -c "adapter speed 2000" -c "program build/bootloader/DM3.1_BAT_bootloader.elf verify reset exit"
```

复位后 Bootloader 因没有有效元数据而保持 USB CDC 升级模式。随后使用 Qt 上位机选择
`DM3.1_BAT_app.bin`，取消勾选“从运行态请求进入 bootloader”并开始升级。第一版 App
和后续版本均通过 Bootloader 写入，不再通过 SWD 写入 App。

## 调试

### VS Code

工程包含 VS Code 配置：

- `.vscode/c_cpp_properties.json`：根工作区 IntelliSense。
- `STM32/.vscode/c_cpp_properties.json`：STM32 子工程 IntelliSense。
- `STM32/.vscode/tasks.json`：构建、烧录、擦除任务。
- `STM32/.vscode/launch.json`：CMSIS-DAP Cortex-Debug 配置。

使用 VS Code 调试前需要安装 Cortex-Debug 扩展，并确认 `arm-none-eabi-gdb` 和 `openocd` 可用。

### Makefile 调试

启动 OpenOCD 调试服务器：

```sh
make -C STM32 debug-server
```

使用 GDB 通过 OpenOCD pipe 下载并调试主应用：

```sh
make -C STM32 debug
```

当前 `debug` 目标使用 `APP_ELF`，适合调试主应用。如果要调试 bootloader，可使用手动 GDB 流程：

```sh
cd STM32
arm-none-eabi-gdb -q build/bootloader/DM3.1_BAT_bootloader.elf
```

进入 GDB 后连接 OpenOCD，例如：

```gdb
target extended-remote :3333
monitor reset halt
load
break main
continue
```

## Flash 分区与启动流程

| 区域 | 地址范围 | STM32F407 sector | 大小 |
| --- | --- | --- | --- |
| Bootloader | `0x08000000` - `0x08007FFF` | sector 0-1 | 32 KB |
| Application | `0x08008000` - `0x0805FFFF` | sector 2-6 | 352 KiB |
| App metadata | `0x08060000` - `0x0807FFFF` | sector 7 | 128 KiB |

主应用链接脚本将中断向量表放在 `0x08008000`。应用启动时 `SystemInit()` 会执行：

```c
SCB->VTOR = APP_FLASH_BASE;
```

bootloader 复位后行为：

1. 初始化 GPIO、UART5、协议解析器并检查 Sector 7 元数据及 App 全镜像 CRC32。
2. App 无效时立即启用 USB CDC，并永久停留在 Bootloader。
3. App 有效时检查 RTC backup register 中的 bootloader 请求标志；标志有效则停留在升级模式。
4. App 有效且没有标志时等待 `BOOTLOADER_HANDSHAKE_TIMEOUT_MS`，当前为 2000 ms。
5. 等待窗口内收到 HELLO 则进入升级流程，否则跳转到 `0x08008000` 主应用。

bootloader 跳转前会校验：

- 元数据 magic、格式、长度和元数据 CRC32 全部正确。
- MSP 位于 `0x20000000` - `0x20020000`。
- Reset_Handler Thumb 地址位于已验证的镜像长度内。
- `0x08008000` 起完整镜像 CRC32 与元数据一致。
- 设置 `SCB->VTOR = APP_FLASH_BASE`。
- 设置 MSP 后恢复全局中断，再调用应用 Reset_Handler。

## UART5 应用通信协议

### 串口参数

应用运行态 UART5 参数：

| 项目 | 配置 |
| --- | --- |
| 串口 | UART5 |
| 波特率 | 115200 |
| 数据格式 | 8N1 |
| 流控 | 无 |
| STM32 TX | PC12 |
| STM32 RX | PD2 |

统一帧格式：

```text
AA 55 + frame_id + length + payload + CRC8
```

其中 `length` 为数据长度，表示 payload 字节数。

CRC8 多项式为 `0x07`，初值为 `0x00`，计算范围为：

```text
frame_id + length + payload
```

帧头 `AA 55` 不参与校验。应用通信最大 payload 为 32 字节。

所有主机请求 payload 第 1 字节为 `seq`。STM32 响应时回显 `seq`，Jetson 可用它匹配请求和响应。帧 ID 也可写作帧ID，表示 `frame_id` 字段。

### 帧 ID

| ID | 方向 | payload | 说明 |
| --- | --- | --- | --- |
| `0x01` | Jetson -> STM32 | `seq` | 查询综合状态 |
| `0x02` | Jetson -> STM32 | `seq + channel_id + level` | 控制 GPIO 输出 |
| `0x03` | Jetson -> STM32 | `seq` | 查询 GPIO 输出状态 |
| `0x04` | Jetson -> STM32 | `seq` | 查询三路超声波距离 |
| `0x05` | Jetson -> STM32 | `seq + password` | 请求进入 bootloader |
| `0x06` | Jetson -> STM32 | `seq` | 查询 CS1237 最新快照 |
| `0x07` | Jetson -> STM32 | `seq + channel` | 切换 CS1237 通道 |
| `0x0C` | Jetson -> STM32 | `seq + red + green + blue + brightness + mode` | 设置 WS2812B RGB；亮度 0..100，模式 0..4 |
| `0x0D` | Jetson -> STM32 | `seq` | 查询 WS2812B RGB 实际状态 |
| `0x81` | STM32 -> Jetson | `seq + tick(uint32 小端) + status + gpio_bitmap` | 综合状态响应 |
| `0x82` | STM32 -> Jetson | `seq + channel_id + result` | GPIO 控制响应 |
| `0x83` | STM32 -> Jetson | `seq + gpio_bitmap` | GPIO 状态响应 |
| `0x84` | STM32 -> Jetson | `seq + front_mm(uint16 小端) + left_mm(uint16 小端) + right_mm(uint16 小端) + valid_bitmap + error_bitmap` | 超声波距离响应 |
| `0x85` | STM32 -> Jetson | `seq + result` | bootloader 请求响应 |
| `0x86` | STM32 -> Jetson | `seq + raw_adc(int32 小端) + channel + valid + error` | CS1237 快照响应 |
| `0x87` | STM32 -> Jetson | `seq + channel + result` | CS1237 通道切换响应 |
| `0x8C` | STM32 -> Jetson | `seq + result` | RGB 设置响应；`0` 成功、`1` 亮度非法、`2` 模式非法 |
| `0x8D` | STM32 -> Jetson | `seq + red + green + blue + brightness + mode + output_on` | RGB 实际状态响应 |
| `0xE1` | STM32 -> Jetson | `seq + source_frame_id + error_code` | 应用错误响应 |

### GPIO 通道

| channel_id | 位图 bit | 信号名称 | GPIO |
| --- | --- | --- | --- |
| `0x01` | bit0 | `SIGNAL-FLASH-CTR` | PC5 |
| `0x02` | bit1 | `SIGNAL-LED` | PE7 |
| `0x03` | bit2 | `SIGNAL-BEE` | PE9 |
| `0x04` | bit3 | `SIGNAL-MOTOR` | PE12 |
| `0x05` | bit4 | `SIGNAL-FLASH` | PB1 |
| `0x06` | bit5 | `SIGNAL-SOUND` | PB12 |

`level = 0x00` 表示输出低电平，`level = 0x01` 表示输出高电平。

### 超声波

三路受控型超声波串口映射：

| 方位 | STM32 串口 | 引脚 |
| --- | --- | --- |
| 前 | UART2 / USART2 | PA2 TX、PA3 RX |
| 左 | UART4 | PA0 TX、PA1 RX |
| 右 | UART3 / USART3 | PB10 TX、PB11 RX |

`0x84` 响应 payload 为 `seq + front_mm(uint16 小端) + left_mm(uint16 小端) + right_mm(uint16 小端) + valid_bitmap + error_bitmap`。STM32 触发周期必须大于 150ms，当前按约 200 ms 周期错峰触发三路传感器，并缓存距离快照。传感器返回 `0xFFFE` 表示同频干扰，返回 `0xFFFD` 表示未测到物体。

### 应用错误码

| error_code | 含义 |
| --- | --- |
| `0x01` | 命令错误 |
| `0x02` | CRC8 校验错误 |
| `0x03` | 长度错误 |
| `0x04` | bootloader 请求密码错误 |

## USB CDC/UART5 Bootloader 协议

### 通信参数

bootloader 升级态默认通过 USB CDC 虚拟串口通信，Jetson 侧通常枚举为 `/dev/ttyACM0`。UART5 保留为备用链路：

| 项目 | 配置 |
| --- | --- |
| 默认链路 | USB CDC `/dev/ttyACM0` |
| 备用串口 | UART5 |
| 波特率 | 460800 |
| 数据格式 | 8N1 |
| STM32 TX | PC12 |
| STM32 RX | PD2 |

USB CDC 和 UART5 使用同样的 bootloader 帧格式：

```text
AA 55 + frame_id + length + payload + CRC8
```

bootloader 最大 payload 为 250 字节。WRITE 帧 payload 为：

```text
seq + offset(uint32 小端) + data
```

因此每个 WRITE 帧最多携带 245 字节固件数据。

### Bootloader 命令

| ID | 名称 | 方向 | payload |
| --- | --- | --- | --- |
| `0x10` | HELLO | Jetson -> STM32 | `seq` |
| `0x11` | START | Jetson -> STM32 | `seq + image_size(uint32 小端) + image_crc32(uint32 小端)` |
| `0x12` | ERASE | Jetson -> STM32 | `seq` |
| `0x13` | WRITE | Jetson -> STM32 | `seq + offset(uint32 小端) + data` |
| `0x14` | VERIFY | Jetson -> STM32 | `seq` |
| `0x15` | JUMP | Jetson -> STM32 | `seq` |
| `0x16` | RESET | Jetson -> STM32 | `seq` |
| `0x90` | INFO | STM32 -> Jetson | `seq + app_base + app_size + write_data_max + version` |
| `0x91` | ACK | STM32 -> Jetson | `seq + command + status` |
| `0x92` | BOOTLOADER_STATUS | STM32 -> 上位机 | `state + app_valid + last_error + reserved + received_bytes(uint32 小端)` |
| `0xE2` | ERROR | STM32 -> Jetson | `seq + command + error_code` |

`BOOTLOADER_STATUS` 状态值为 `WAITING=0`、`RECEIVING=1`、`VERIFIED=2`、`ERROR=3`。
USB CDC 空闲时每 1 秒主动上报一次；执行单次 Flash 擦除、写入或校验时暂停，上述操作结束后再上报。

### 升级流程

默认流程：

```text
HELLO -> START -> ERASE -> WRITE... -> VERIFY -> JUMP
```

说明：

1. HELLO 用于确认 STM32 已在 bootloader。
2. START 携带应用镜像大小和 CRC32，但不破坏旧 App。
3. ERASE 先使 Sector 7 元数据失效并回读确认，再擦除应用区 sector 2-6。
4. WRITE 从 offset 0 开始连续写入，offset 必须单调递增且不能跳包。
5. VERIFY 校验完整镜像和向量表，随后写入元数据字段，最后提交有效 magic。
6. VERIFY 成功后仍等待显式 JUMP；若此时复位，下次启动也允许进入已验证 App。
7. JUMP 会重新执行完整有效性检查。

没有有效元数据时，即使 `0x08008000` 已存在通过 SWD 写入的 App，Bootloader 也不会
仅凭向量表信任它；必须由上位机重新发起完整升级。元数据失效后的任何擦写失败或断电
都会使设备继续停留在 Bootloader，直至重新升级成功。

### 从应用请求进入 bootloader

应用运行态支持 `0x05` 请求帧：

```text
seq + password
```

密码固定为 ASCII 字符串：

```text
wb88
```

收到合法请求后，应用会：

1. 写入 RTC backup register bootloader 标志。
2. 回复 `0x85`，payload 为 `seq + result`。
3. 延时约 500 ms 后调用 `NVIC_SystemReset()`。
4. 延时期间 `LED_RUN` 每 250 ms 切换一次。

bootloader 启动后消费该标志并停留在升级流程。升级过程中 `LED_RUN` 继续每 75 ms 切换一次。

## Jetson 端升级配合

Jetson ROS2 包位于：

```text
Linux_ROS_WS/src/stm32_jetson_serial_comm
```

主应用固件生成后会自动投放到：

```text
Linux_ROS_WS/src/stm32_jetson_serial_comm/firmware/DM3.1_BAT_app.bin
```

同步到 Jetson：

```sh
Linux_ROS_WS/scripts/sync_to_jetson.sh
```

Jetson 上重新构建 ROS2 包：

```sh
cd ~/ros_ws
rm -rf build/stm32_jetson_serial_comm install/stm32_jetson_serial_comm log
source /opt/ros/foxy/setup.bash
colcon build --packages-select stm32_jetson_serial_comm
source install/setup.bash
```

如果 STM32 正在运行应用，推荐命令：

```sh
ros2 run stm32_jetson_serial_comm stm32_bootloader \
  /home/jetson/ros_ws/src/stm32_jetson_serial_comm/firmware/DM3.1_BAT_app.bin \
  --device /dev/ttyACM0 \
  --request-from-app
```

上位机工具默认：

- `--app-baudrate 115200`：发送应用运行态 `0x05` bootloader 请求。
- `--baudrate 460800`：进入 bootloader 后执行升级。
- bootloader 升级默认设备为 USB CDC `/dev/ttyACM0`；如需走 UART5，可指定 `--device /dev/ttyTHS0`。

如果 STM32 已经在 bootloader 中，可直接升级：

```sh
ros2 run stm32_jetson_serial_comm stm32_bootloader \
  /home/jetson/ros_ws/src/stm32_jetson_serial_comm/firmware/DM3.1_BAT_app.bin \
  --device /dev/ttyACM0 \
  --baudrate 460800
```

如需校验后复位启动应用：

```sh
ros2 run stm32_jetson_serial_comm stm32_bootloader \
  /home/jetson/ros_ws/src/stm32_jetson_serial_comm/firmware/DM3.1_BAT_app.bin \
  --device /dev/ttyACM0 \
  --reset-after-verify
```

## 测试

STM32 工程测试为 Python 文本/结构测试，用于检查协议、链接脚本、Makefile、文档和关键源码结构。

运行全部 STM32 测试：

```sh
python3 -m unittest discover STM32/tests -v
```

常用定向测试：

```sh
python3 -m unittest STM32/tests/test_uart5_bootloader.py -v
python3 -m unittest STM32/tests/test_uart5_protocol_readme.py -v
python3 -m unittest STM32/tests/test_tim6_periodic_tick.py -v
python3 -m unittest STM32/tests/test_usb_cdc_echo.py -v
python3 -m unittest STM32/tests/test_cs1237_driver.py -v
python3 -m unittest STM32/tests/test_cs1237_protocol.py -v
```

USB CDC 虚拟串口复用 UART5 应用协议。烧录应用后，主机应枚举出 `/dev/ttyACM*`，可直接走同一套状态查询：

```sh
ros2 run stm32_jetson_serial_comm serial_link \
  --device /dev/ttyACM0 \
  --query-status \
  --seq 0x10
```

CS1237 内部温度通道验证：

```sh
ros2 run stm32_jetson_serial_comm serial_link \
  --device /dev/ttyACM0 --cs1237-set-channel temp --read-seconds 3
sleep 1
ros2 run stm32_jetson_serial_comm serial_link \
  --device /dev/ttyACM0 --cs1237-query --read-seconds 3
```

构建验证：

```sh
make -C STM32 bootloader
make -C STM32 app
```

## DM3.1 风扇与按键

- PA5 使用 TIM2_CH1 输出 25 kHz PWM，四档为 25%/50%/75%/100%，上电默认 4 档（100%）。
- PA6/PA7 使用 TIM3_CH1/CH2 下降沿输入捕获，两路转速按每转 2 个脉冲计算；1.5 秒无脉冲回报 0 RPM。
- PE15/PE13/PE11 分别为 KEY1/KEY2/KEY3，内部上拉、低电平按下、20 ms 软件消抖。
- 应用协议 `0x0A/0x8A` 设置风扇档位，`0x0B/0x8B` 查询档位、双路 RPM 和按键位图；KEY1/KEY2/KEY3 分别对应 bit0/bit1/bit2。
- PB13 以 WS2812B 协议驱动三颗级联且同步同色的 RGB 灯；见“WS2812B RGB 灯”。

应用构建产物为 `build/app/DM3.1_BAT_app.bin`，并自动同步至
`Linux_ROS_WS/src/stm32_jetson_serial_comm/firmware/DM3.1_BAT_app.bin`。

## 常见问题

### 修改 LED 闪烁周期后烧录无变化

确认当前复位入口是否仍是 `0x08000000` 的 bootloader。如果只执行 `make flash`，它只烧录主应用到 `0x08008000`，不会更新 bootloader。若板子实际运行的是旧 bootloader 或旧应用，需要按烧录章节分别更新。

### JUMP 后主程序不运行

检查应用向量表：

- `0x08008000` 第一个 word 应为 SRAM 栈顶，例如 `0x20020000`。
- `0x08008004` 应为应用 Reset_Handler，地址应落在 `0x08008000` - `0x0805FFFF`。
- Sector 7 元数据必须存在，且镜像 CRC32 必须匹配。

bootloader 跳转前会恢复全局中断，否则主应用中的 SysTick、TIM6、UART 中断会无法工作。

### ERASE 超时

bootloader 会在元数据失效后擦除 sector 2-6，Flash 擦除可能超过普通单帧超时。Jetson 上位机提供独立参数：

```sh
--erase-timeout 10
```

如果板子擦除较慢，可临时提高到 20 秒。

### 串口升级无响应

区分两个波特率：

- 应用运行态通信：`115200`
- bootloader 升级态通信：`460800`

如果使用 `--request-from-app`，工具会自动先用 `115200` 请求应用复位，再用 `460800` 升级。若手动进入 bootloader，需使用 `--baudrate 460800`。

### OpenOCD 烧录不稳定

降低 adapter speed：

```sh
make -C STM32 OPENOCD_ADAPTER_SPEED=1000 flash
```

只烧 bootloader 时也可以把命令中的 `adapter speed 2000` 改成 `1000`。

## 参考文档

以下历史设计文档仍保留，便于查看设计过程：

- `docs/2026-06-29-uart5-slave-status-design.md`
- `docs/2026-06-29-uart5-slave-status-plan.md`
- `docs/superpowers/specs/2026-06-23-tim6-periodic-tick-design.md`
- `docs/superpowers/plans/2026-06-23-tim6-periodic-tick.md`
- `docs/superpowers/specs/2026-07-02-uart5-bootloader-design.md`
- `docs/superpowers/plans/2026-07-02-uart5-bootloader.md`
