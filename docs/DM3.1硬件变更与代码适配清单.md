# DM3.1 硬件变更与代码适配清单

## 1. 对比基线与结论

- 旧版基线：`../DM2.1_BAT/STM32/docs/SCH_导盲犬V2.2电源板_2026-06-29.pdf`
- 新版原理图：`STM32/docs/SCH_导盲犬V3.0电源板.pdf`，更新日期 2026-07-22
- DM3.1 工作区最初与相邻 DM2.1 工程相同；P0 紧急引脚适配和 P1 风扇/按键接入已于 2026-07-22 完成，RGB 等待协议确认。
- 新版原理图由 7 页缩为 6 页，删除了独立的 X 轴振动马达 H 桥驱动页，新增风扇、按键、RGB、爆闪切换和接口保护电路。
- 新 PDF 的标题栏仍写有“导盲犬V2.2电源板_第二版”，但文件名及图纸项目名为 V3.0；建议硬件侧确认最终版本命名，避免拿错板卡版本。

## 2. STM32 引脚变更

### 2.1 必须优先适配的冲突

| V3.0 引脚 | V3.0 信号 | DM2.1 固件原用途 | 影响与处理 |
| --- | --- | --- | --- |
| PA7 | `FAN_SPEED_2` | `SIGNAL_MOTORX_SW` GPIO 输出、协议通道 `0x01` | 严重冲突。当前固件会主动驱动风扇测速线；必须改为输入/定时器捕获，并移除旧 X 轴开关控制。 |
| PB14 | `CLK` | 未配置 | CS1237 时钟由旧固件的 PD11 迁移到 PB14，配置为输出。 |
| PD8 | `DTR` | 未配置 | CS1237 数据线由旧固件的 PD14 迁移到 PD8，保留运行时输入/输出方向切换。 |
| PC4 | 未连接 | `SIGNAL_MOTORX` GPIO 输出、协议通道 `0x01` 的配套方向控制 | V3.0 已删除 X 轴 H 桥，停止配置和驱动 PC4。 |
| PC5 | `SIGNAL_FLASH_CTR` | 未配置 | 新增红蓝爆闪切换控制输出。不要误用原 PC4。 |

> 已完成：`CS1237_CLK=PB14`、`CS1237_DIO=PD8`，PA7 已改为安全输入，PC4 已释放，PC5 已作为 `SIGNAL_FLASH_CTR` 低电平初始化。

### 2.2 新增或改名的 GPIO

| 引脚 | V3.0 信号 | 方向/建议外设 | 说明 |
| --- | --- | --- | --- |
| PA5 | `FAN_PWM` | 输出，优先 TIM2_CH1 | 两个 4 线风扇共用一条 PWM 控制，经两个 22Ω 电阻分别送出。 |
| PA6 | `FAN_SPEED_1` | 输入，优先 TIM3_CH1 输入捕获 | 风扇 1 测速，板上 10kΩ 上拉至 3.3V。 |
| PA7 | `FAN_SPEED_2` | 输入，优先 TIM3_CH2 输入捕获 | 风扇 2 测速，板上 10kΩ 上拉至 3.3V。 |
| PB1 | `SIGNAL_FLASH` | GPIO 输出 | 原 `SIGNAL_RESERVED` 改为红蓝爆闪电源控制；电气控制方式仍为高有效光耦输入。 |
| PB13 | `RGB` | 待确认后配置输出外设 | 接“信号灯”接口；原理图未说明具体灯珠协议，适配前需确认是普通开关、PWM 还是单总线 RGB。 |
| PB14 | `CLK` | GPIO 输出 | CS1237 SCLK。 |
| PC5 | `SIGNAL_FLASH_CTR` | GPIO 输出 | 新增爆闪模式/切换控制，经 U13 光耦隔离输出 `FLASH_CTR`。 |
| PD8 | `DTR` | 双向 GPIO | CS1237 `DRDY#/DOUT`。 |
| PE13 | `KEY2` | GPIO 输入、内部上拉 | 导盲杆按键 2；按下低电平，20 ms 软件去抖。 |
| PE15 | `KEY1` | GPIO 输入、内部上拉 | 导盲杆按键 1；按下低电平，20 ms 软件去抖。 |

### 2.3 保持不变、可继续复用的功能

| 功能 | 引脚 |
| --- | --- |
| 左/前/右超声波串口 | UART4 PA0/PA1、USART2 PA2/PA3、USART3 PB10/PB11 |
| 主机 UART5 | TX PC12、RX PD2 |
| 主机 USART1 | TX PA9、RX PA10 |
| RTK USART6 | TX PC6、RX PC7 |
| USB FS | DM PA11、DP PA12 |
| SWD | SWDIO PA13、SWCLK PA14 |
| 运行灯 | PC10 `LED_RUN` |
| 照明、声光报警、导盲杆马达、音频功放使能 | PE7 `SIGNAL_LED`、PE9 `SIGNAL_BEE`、PE12 `SIGNAL_MOTOR`、PB12 `SIGNAL_SOUND` |

## 3. 电路板电路变更

### 3.1 电源与风扇（第 2 页）

- 新增两路 12V 四线风扇接口 `PWM_FAN1/2`：共用 `FAN_PWM`，独立反馈 `FAN_SPEED_1/2`。
- 12V 主电源输出保护由 5 颗 TVS 扩展为 7 颗；5V 输出新增 D10、D11 两颗 `SMF7.5CA` TVS。
- 12V、5V 电源指示灯限流电阻分别由 4.7kΩ/1kΩ 调整为 33kΩ/6.8kΩ，仅影响亮度和功耗，不需要代码处理。
- ADC 的 3.3V LDO 地从 `GND_MAIN` 改为 `GND_ADC`，并通过 R2 0Ω 与主地单点连接；ADC 页也统一改用 `GND_ADC`。这是模拟地抗干扰调整，不改采样协议。

### 3.2 MCU 与外部接口保护（第 3 页）

- 主机 USB 新增 `USBLC6-2SC6`、肖特基二极管和 TVS 保护；USB D+/D- 引脚不变。
- UART5、三路超声波和 RTK 接口新增 `TPD2E001DRLR` ESD 保护；串口引脚不变。
- SWD 增加浪涌/反接保护，SWDIO 上拉和 SWCLK 下拉由 4.7kΩ 改为 10kΩ；调试引脚不变。
- 运行灯限流电阻由 470Ω 改为 1kΩ；PC10 不变。
- 新增信号灯接口 `RGB`，并新增 KEY1/KEY2、风扇和 CS1237 的明确 MCU 连线。

### 3.3 音频（第 4 页）

- MCU 侧仍使用 PB12 `SIGNAL_SOUND` 控制光耦，代码接口不变。
- 功放 `CTRL` 侧改用 `S_Switch` 网络，并调整隔离 12V 指示灯支路；属于板内电路变更。

### 3.4 继电器、爆闪和导盲杆（第 5 页）

- 原 `SIGNAL_RESERVED` 明确改为 PB1 `SIGNAL_FLASH`，控制红蓝爆闪 12V 电源。
- 新增 PC5 `SIGNAL_FLASH_CTR` 和 U13，用于输出 `FLASH_CTR` 切换控制。
- 原独立 `SIGNAL` 对外控制接口被删除。
- 导盲杆接口合并了马达 `M+`、`KEY1`、`KEY2`；马达仍由 PE12 `SIGNAL_MOTOR` 控制。
- 光耦输入下拉由 4.7kΩ 调整为 10kΩ，控制仍为高有效、默认下拉。

### 3.5 ADC 与 X 轴马达（第 6 页及删除页）

- CS1237 芯片和采样接口保持不变，但数字引脚明确改为 PB14 `CLK`、PD8 `DTR`，模拟地改为 `GND_ADC`。
- DM2.1 第 7 页的 X 轴振动马达 H 桥整体删除：PA7 `SIGNAL_MOTORX_SW`、PC4 `SIGNAL_MOTORX` 不再存在。

### 3.6 新增 4 口 USB HUB（待硬件落图）

采用沁恒 `CH334P` USB 2.0 High-Speed MTT 四下行口 HUB（QFN16 3×3mm，嘉立创 `C5373042`），固定连接如下：

```text
主机 USB
   └─ HUB 上行口
       ├─ D1: STM32 PA11/PA12 USB CDC（现有主机 USB）
       ├─ D2: USB 声卡
       ├─ D3: EC800M-CN-GC 4G Cat.1
       └─ D4: CP2102N USB-UART → RTK 3.3V UART
```

这里的“4 口”是 4 个下行口，上行主机口不计入 4 口。

#### 数据连接

- HUB 上行 `DMU/DPU` 接新的主机 USB 接口 D-/D+。`CH334P` 没有 `VBUS_DET`；主机 VBUS 只留测试点，不接 `V5`，也不得与板载 `VCC_5V` 直接互供。
- D1 的 D-/D+ 接现有 `DM/DP` 网络。取消旧“主机 USB”外部接口，并删除 D16 从 USB VBUS 向 `VCC_5V` 的肖特基供电路径，防止自供电 HUB 反灌主机。现有 USBLC6-2SC6 可保留，但板内短连不再新增一级 ESD。
- D2 使用 `CM108B` USB 声卡芯片，配置为 USB Audio Class 1.0 Headset 模式，同时支持播放和单声道麦克风录音：`MODE=GND`、`MSEL=GND`、`PWRSEL=3.3V`。使用内部时钟和默认 USB 描述符，不装晶振、93C46 EEPROM、I2S 和 HID 按键外围。
- `CM108B LOL/LOR` 不得直接短接；各经 47µF 隔直电容和 1kΩ 电阻后合成单声道，再经 1:1、600Ω 音频隔离变压器差分接入 NS4110B `INP/INN`。同时取消现图 R13 0Ω 对 `INP` 的接地，保留 `GND_MAIN` 与 `GND_12V_SOUND` 隔离。
- D3 改用嘉立创可直接 SMT 的 `EC800M-CN-GC`（JLCPCB `C9900056345`，扩展库，仅标准 PCBA，需 X-ray），Cat.1 最大 10Mbps 下行/5Mbps 上行。立创商城可采购型号为 `EC800MCNGB-I05-SGNSA`（`C53243597`），下单前需核对实际备料型号与固件版本。
- `USB_DP/USB_DM` 直连 HUB D3，`USB_VBUS` 接 D3 5V 仅作连接检测，不给模组 VBAT 供电；保留 USB 升级测试点和 `USB_BOOT` 测试点。
- EC800M 主天线按 50Ω 阻抗布线，预留 π 型匹配与 I-PEX/U.FL 天线座；SIM 卡座紧邻模组并加低电容 ESD。不接 GNSS 外围，现有 UM982 已承担定位。
- D4 接 `CP2102N` USB D-/D+；`CP2102N_TXD -> RTK_RX`、`CP2102N_RXD <- RTK_TX`，共 `GND_MAIN`，UART 保持 `3.3V, 115200, 8N1`。复用现有 RTK 接口和 `TPD2E001DRLR` ESD，取消 USART6 PC6/PC7 到 RTK 的连接。
- `CP2102N` 使用内部时钟，不另加晶振。

#### CH334P 最小接线

| 引脚 | 信号 | 本项目接法 |
| --- | --- | --- |
| 1、2 | `XO`、`XI` | 两脚之间接 12MHz 晶体；芯片已内置负载电容，不再外加两颗晶振电容 |
| 3、4 | `DM4`、`DP4` | D4：`CP2102N` USB D-/D+ |
| 5、6 | `DM3`、`DP3` | D3：`EC800M-CN-GC` USB D-/D+ |
| 7、8 | `DM2`、`DP2` | D2：`CM108B` USB D-/D+ |
| 9、10 | `DM1`、`DP1` | D1：STM32 PA11/PA12 USB D-/D+ |
| 11、12 | `DMU`、`DPU` | 主机 USB D-/D+ |
| 13 | `RESET#/CDP` | 利用内部上电复位，完全悬空；不上拉，避免误开 CDP 并禁用低功耗休眠 |
| 14 | `PGANG` | 悬空；复位后为 Active/Suspend 状态输出，不用它控制下行口电源 |
| 15 | `V5` | 接板载 `VCC_5V_USB`，就近 1µF + 100nF 去耦 |
| 16 | `VDD33` | 内部 LDO 3.3V 输出，只接就近 10µF + 100nF 到地，不并入板载 3.3V |
| EP | `GND` | 接 `GND_MAIN`，暴露焊盘内就近打地过孔 |

`CH334P` 默认为 self-powered，无 `PSELF`、`PWREN#`和 `OVCUR#` 引脚，不支持由 HUB 执行下行口电源开关和过流上报。本项目四路均为板内固定设备，各自由板载电源供电，因此不增加四路 USB VBUS 电源开关。

#### CM108B 最小接线（播放＋麦克风录音）

| 引脚 | 信号 | 本项目接法 |
| --- | --- | --- |
| 29、34 | `AVDD` | 经磁珠接 `VCC_5V_USB`，芯片侧共放 10µF + 100nF，每个 AVDD 再就近放 100nF |
| 35 | `DVDD` | 经独立磁珠接 `VCC_5V_USB`，就近 10µF + 100nF |
| 24、33 | `AVSS` | 接 `GND_MAIN` |
| 14、36 | `DVSS` | 接 `GND_MAIN` |
| 8 | `DREG18` | 1µF 到 `GND_MAIN`，只作内部 1.8V 稳压旁路，不外供 |
| 9 | `DREG33` | 100nF 到 `GND_MAIN`；仅用于模式引脚上拉 |
| 37 | `AREG36` | 10µF 到 `GND_MAIN`，不外供 |
| 26 | `VREF` | 10µF 到 `AVSS`，走线最短 |
| 31 | `LOBS` | 10µF 到 `AVSS`，不连其他负载 |
| 41 | `USBDP` | HUB D2 `DP` 经 22Ω 串联电阻接入 |
| 42 | `USBDM` | HUB D2 `DM` 经 22Ω 串联电阻接入 |
| 7 | `PWRSEL` | 10kΩ 上拉到 `DREG33`；Headset 模式下向主机声明 100mA bus-powered |
| 10 | `MODE` | 10kΩ 下拉到 `GND_MAIN`，Headset/Playback + Recording |
| 38 | `MSEL` | 10kΩ 下拉到 `GND_MAIN`，关闭 AA 直通混音，避免麦克风回放引起啸叫 |
| 22 | `ADSEL` | 10kΩ 下拉到 `GND_MAIN` |
| 23 | `TEST` | 直接 `GND_MAIN` |
| 30 | `LOL` | 47µF 隔直（正极朝芯片）→ 1kΩ → `AUDIO_MONO` |
| 32 | `LOR` | 47µF 隔直（正极朝芯片）→ 1kΩ → `AUDIO_MONO` |
| 25 | `VBIAS` | 2.2kΩ → `MIC_BIAS`；`MIC_BIAS` 就近放 4.7µF + 100nF 到 `AVSS` |
| 27 | `MICIN` | 100nF 串联隔直 → 8.2kΩ → `MIC_JACK` |
| 11、28 | `N.C.` | 不接 |

`AUDIO_MONO` 接 1:1、600Ω音频变压器初级，初级另一端接 `GND_MAIN`；次级两端经现有 C24/C25 分别接 NS4110B `INP/INN`。删除 R13 0Ω，次级及 NS4110B 侧只使用 `GND_12V_SOUND`。

麦克风接口按 3.5mm 单声道驻极体麦克风设计：插座 `TIP` 接 `MIC_JACK`，`SLEEVE` 接 `GND_MAIN`，开关脚不接。`MIC_BIAS` 再经 8.2kΩ 接 `MIC_JACK`；接口第一位放低漏电、低电容 3.3V ESD 保护，并预留 100pF 到地的 RF 滤波电容（默认 DNP）。`VBIAS` 驱动能力小，不接其他负载。

其余未用功能脚 `SPDIFO`、`DR/DW/SK/CS`、`GPIO1/3/4`、`SDIN/SDOUT`、`ADSCLK/ADLRCK/ADMCLK`、`DASCLK/DALRCK/DAMCLK`、`LEDO/LEDR`、`PDSW` 均不接。`MUTER`、`MUTEP`、`VOLUP`、`VOLDN` 有内部上拉，不安装按键时可不接。

USB D+/D- 串联 22Ω 电阻靠近 CM108B，从 HUB 到 CM108B 全程按 90Ω 差分阻抗布线，不放板内 ESD 和共模电感。CM108B 模拟区与 USB/4G 开关电源拉开，但 `AVSS/DVSS` 使用同一块连续 `GND_MAIN` 地平面，不切地。

#### 供电与保护

- `CH334P` 按默认 self-powered 工作。D1 STM32、D2 CM108B、D4 CP2102N/RTK 均使用板载电源，不得通过 USB VBUS 互相反向供电；D3 只给 `USB_VBUS` 提供 5V 连接检测。
- `VCC_5V_USB` 入口放一颗总限流/短路保护负载开关，限流值按 CM108B、CP2102N 和 HUB 实测峰值留裕量；故障不会由 `CH334P` 上报给主机。
- EC800M `VBAT` 使用独立 12V -> 3.8V/3A 同步降压电源 `VCC_4G`，不挂现有 5V/3A 母线。模组突发发射峰值可达 2A，必须保证 VBAT 始终不低于 3.4V；大容量低 ESR 电容与去耦紧贴 VBAT 引脚。

#### PCB 必做项

- 所有 USB 2.0 D+/D- 按 90Ω 差分阻抗、同层、紧邻完整地平面、最少过孔布线，不留分支桩线；HUB 与 4G 优先最短。
- 连接器的低电容 ESD 放在接口第一位，保护前后走线不并行回绕；板内固定连接不重复堆叠 ESD/共模电感。
- CH334P 裸露焊盘接地并就近打地过孔；12MHz 晶体与 `V5/VDD33` 去耦电容紧贴芯片。

## 4. 现有代码的适配优先级

### USB HUB/RTK 直连改版（待硬件定版后执行）

1. STM32 USB CDC 仍是 HUB D1 下的独立 USB 设备，现有应用协议、bootloader 和固件不需修改。
2. RTK 改为 CP2102N 直连主机后，STM32 USART6 透传命令 `0x08/0x09`、`stm32_rtk` 和 ROS `rtk_bridge` 不再是主链路；主机直接打开 CP2102N 对应的 `/dev/ttyUSB*`。
3. Linux 不按 `/dev/ttyUSB0` 固定编号绑定 RTK；按 CP2102N VID/PID/序列号配置 udev 稳定别名，避免 4G 同时枚举多个 USB 串口后设备号变动。
4. 若仍需要旧 STM32 RTK 透传作为备份，硬件定版前明确提出；当前方案不增加 UART 模拟开关和双路复用电路。

### P0：上板前必须完成（已完成）

1. [x] 把 CS1237 的 `CLK` 从 PD11 改到 PB14、`DIO/DTR` 从 PD14 改到 PD8，并同步 `.ioc`、`main.h`、GPIO 初始化。
2. [x] 删除 PA7/PC4 的旧 X 轴 H 桥输出配置和控制映射，防止驱动 `FAN_SPEED_2`。
3. [x] 协议通道 `0x01` 改为 `FLASH_CTR`，`0x05` 改为 `FLASH`；数字 ID 和状态位图位置保持不变。
4. [x] 初始化 PC5 `SIGNAL_FLASH_CTR` 的安全默认低电平；其他继电器/光耦输出也保持上电低电平。

### P1：按产品功能接入（风扇和按键已完成）

1. [x] PA5 25 kHz 风扇 PWM，上电 50%，Jetson 四档 25%/50%/75%/100%。
2. [x] PA6/PA7 双路输入捕获测速，按每转 2 脉冲计算，1.5 秒超时报 0 RPM。
3. [x] PE15/PE13 内部上拉、低有效、20 ms 软件去抖。
4. [x] UART5/USB CDC 协议、Jetson API/CLI 与 ROS 话题接入风扇和按键。
5. [ ] PB13 `RGB` 的实际协议确认后再实现驱动。

工程和产物已统一使用 `DM3.1_BAT`，应用固件同步路径为：

```text
Linux_ROS_WS/src/stm32_jetson_serial_comm/firmware/DM3.1_BAT_app.bin
```

### P2：回归验证

1. 回归 3 路超声波、RTK、UART5 bootloader、USB CDC 和状态灯。
2. 实板验证所有高有效继电器的上电默认关闭状态。
3. 用已知砝码重新校准 CS1237 零点和比例；模拟地改版后不要直接沿用未验证的标定值。

## 5. GitHub 仓库迁移

- 新地址：`git@github.com:WangRuoyu0101/DM_BAT_STM32_3.0.git`
- 只读连通性检查成功；远端当前没有任何 ref，可按空仓库处理。
- 当前 `DM3.1-BAT` 目录没有 `.git`，因此尚无本地 `origin` 可直接修改。
- 相邻的 DM2.1 仓库仍指向 `git@github.com:WangRuoyu0101/DM_BAT_STM32.git`。

为保留 DM2.1 的完整提交历史，应将当前 DM3.1 文件放入原 Git 历史的工作树，或把原 `.git` 历史安全迁入本目录后执行：

```sh
git remote set-url origin git@github.com:WangRuoyu0101/DM_BAT_STM32_3.0.git
git remote -v
```

不要直接在当前目录裸执行 `git init` 后首次提交，否则会丢失与 DM2.1 提交历史的连续关系。
