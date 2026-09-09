# DM3.1 P1 风扇、按键与工程重命名设计

## 目标与范围

本阶段完成三件事：

1. 接入 PA5 四档风扇 PWM 和 PA6/PA7 双路测速。
2. 接入 PE15/PE13 的 KEY1/KEY2，内部上拉、低有效、20 ms 去抖。
3. 将当前工程标识、构建产物和固件同步路径从 `DM2.1_BAT` 统一改为 `DM3.1_BAT`。

RGB 协议尚未确认，本阶段不配置 PB13、不编写 RGB 驱动。历史设计文档和硬件对比文档中用于描述旧基线的 `DM2.1` 保留原意；当前工程文件名、命令、产物和路径不得继续使用 `DM2.1_BAT`。

## 硬件与定时器

### 风扇 PWM

- PA5 使用 TIM2_CH1 输出 25 kHz PWM。
- 四档固定为 1=25%、2=50%、3=75%、4=100%。
- 上电默认第 2 档，即 50%。
- 两个风扇共用同一 PWM 档位，与原理图的 `FAN_PWM` 网络一致。
- GPIO 使用 3.3V 推挽复用输出，与当前板卡直连原理图一致；实板首测需确认风扇 PWM 输入不会外部上拉到超过 STM32 允许的电压。

TIM2 位于 84 MHz APB1 定时器时钟域，配置 `Prescaler=0`、`Period=3359`，得到 25 kHz。档位直接映射为 840、1680、2520、3360 个计数，100% 档保持持续高电平。

### 双路测速

- PA6 使用 TIM3_CH1 输入捕获风扇 1 转速脉冲。
- PA7 使用 TIM3_CH2 输入捕获风扇 2 转速脉冲。
- TIM3 计数频率设为 100 kHz，16 位自然回绕；相邻下降沿捕获值使用无符号 16 位差值处理回绕。
- 默认每转脉冲数为 `2U`，保留单个编译期校准常量 `APP_BOARD_IO_FAN_PULSES_PER_REV`。
- RPM 计算为 `60 * 100000 / (delta * pulses_per_rev)`，结果限制在 `uint16_t`。
- 1.5 秒未收到新捕获则对应 RPM 归零。

### 按键

- PE15=KEY1、PE13=KEY2，GPIO 输入、内部上拉、低电平表示按下。
- 使用现有 2 ms `App_PeriodicTick_Get()` 软件节拍采样。
- 原始状态连续稳定 10 个 tick（20 ms）后更新去抖状态。
- 按键位图 bit0=KEY1、bit1=KEY2，1 表示按下。

## 固件模块

新增一个最小模块 `app_board_io.c/.h`，统一管理本次新增的风扇和按键，避免为两个小功能各建一套抽象。

接口：

```c
typedef struct
{
  uint8_t fan_level;
  uint16_t fan1_rpm;
  uint16_t fan2_rpm;
  uint8_t key_bitmap;
} App_BoardIO_Snapshot;

HAL_StatusTypeDef App_BoardIO_Init(TIM_HandleTypeDef *pwm_timer, TIM_HandleTypeDef *tach_timer);
uint8_t App_BoardIO_SetFanLevel(uint8_t level);
void App_BoardIO_Run(uint32_t current_tick);
void App_BoardIO_TachCapture(TIM_HandleTypeDef *timer);
void App_BoardIO_GetSnapshot(App_BoardIO_Snapshot *snapshot);
```

`main.c` 初始化 TIM2/TIM3 后调用 `App_BoardIO_Init()`，主循环调用 `App_BoardIO_Run(current_tick)`。`HAL_TIM_IC_CaptureCallback()` 只转发到 `App_BoardIO_TachCapture()`，不在中断里计算 RPM 或处理协议。

初始化失败沿用现有 `Error_Handler()`。非法风扇档位不修改当前档位，并返回协议结果 `INVALID_LEVEL`。

## 应用通信协议

保留全部现有帧和 GPIO 通道编号，新增：

| ID | 方向 | payload | 说明 |
| --- | --- | --- | --- |
| `0x0A` | Jetson -> STM32 | `seq + level` | 设置风扇档位 1..4 |
| `0x8A` | STM32 -> Jetson | `seq + level + result` | 返回实际档位和结果 |
| `0x0B` | Jetson -> STM32 | `seq` | 查询板级 IO 状态 |
| `0x8B` | STM32 -> Jetson | `seq + level + fan1_rpm(uint16 LE) + fan2_rpm(uint16 LE) + key_bitmap` | 返回风扇和按键快照 |

结果码复用控制类语义：`0x00=OK`、`0x02=INVALID_LEVEL`。帧长度错误继续使用现有错误响应路径。

USB CDC 和 UART5 共用 `App_Uart5Slave` 分发逻辑，因此新增命令自动支持两条链路。

## Jetson 接口

- `messages.py` 增加风扇设置响应和板级 IO 状态解码。
- `serial_host.py` 增加 `set_fan_level()` 和 `query_board_io()`。
- 新增最小命令 `stm32_fan`：
  - `stm32_fan set 1|2|3|4`
  - `stm32_fan status`
- ROS 节点周期查询 `0x0B`，发布：
  - `/stm32/fan_rpm`：`Int32MultiArray [fan1_rpm, fan2_rpm]`
  - `/stm32/fan_level`：`UInt8`
  - `/stm32/key_bitmap`：`UInt8`
  - `/stm32/board_io_text`：人类可读摘要

ROS 节点不新增设置服务；四档设置由 `stm32_fan` CLI 完成，避免为一个整数档位引入自定义 ROS service 类型。

## DM3.1 工程重命名

- `STM32/DM2.1_BAT.ioc` 重命名为 `STM32/DM3.1_BAT.ioc`，同步 CubeMX 项目名。
- Makefile `TARGET` 改为 `DM3.1_BAT`。
- 应用产物改为 `DM3.1_BAT_app.{elf,hex,bin}`，bootloader 产物改为 `DM3.1_BAT_bootloader.{elf,hex,bin}`。
- Makefile 继续复用现有复制规则，但源文件名变化后自动覆盖：

```text
Linux_ROS_WS/src/stm32_jetson_serial_comm/firmware/DM3.1_BAT_app.bin
```

- 删除旧的 `firmware/DM2.1_BAT_app.bin`，更新 CLI 帮助、测试和当前 README 中的所有构建/同步示例。
- 历史规格、历史计划和硬件差异说明中的 DM2.1 基线名称不批量替换。

## 测试与验收

- 新增一个 `test_board_io.py`，检查 TIM2/TIM3、默认 50%、四档映射、测速公式、超时归零和按键去抖结构。
- 扩展协议、UART5 从机、Jetson 消息、主机、CLI 和 ROS 节点测试。
- 更新构建/固件同步测试，断言只生成并引用 `DM3.1_BAT_app.bin`。
- 运行全部 STM32 与 Jetson Python 测试。
- 执行 `make -C STM32 clean` 后重新构建 app 和 bootloader，确认新产物存在、旧产物不再生成、固件同步路径正确。
- 实板验收：上电 50%，四档切换正确，两路 RPM 合理，拔掉测速线 1.5 秒后归零，KEY1/KEY2 去抖状态正确。
