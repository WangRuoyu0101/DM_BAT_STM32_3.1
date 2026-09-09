# TIM6 周期任务节拍设计

## 目标

使用 STM32F407 的 TIM6 基本定时器产生 10 ms 周期中断。中断服务只递增一个全局软件节拍计数器，LED-RUN 和后续周期任务在主循环中根据该计数器独立调度。

## 定时器配置

- 定时器：TIM6
- TIM6 输入时钟：84 MHz
- Prescaler：8399
- Counter Period：99
- 计数频率：10 kHz
- 更新中断周期：10 ms
- 启用 `TIM6_DAC_IRQn`

计算关系：

```text
84 MHz / (8399 + 1) = 10 kHz
10 kHz / (99 + 1) = 100 Hz = 10 ms
```

## 软件结构

定义一个 `volatile uint32_t` 全局节拍计数器。TIM6 更新中断通过 HAL 中断处理流程进入 `HAL_TIM_PeriodElapsedCallback()`，确认中断来源为 TIM6 后，将计数器加一。

中断回调不得执行 LED 翻转、通信收发或其他业务任务，避免中断执行时间随任务数量增加。

主循环中的每个周期任务保存自己的上次执行节拍：

```c
if ((uint32_t)(current_tick - last_tick) >= period_ticks)
{
    last_tick = current_tick;
    task();
}
```

使用无符号减法判断间隔，允许 `uint32_t` 计数器自然溢出。

## LED-RUN 行为

- LED-RUN 引脚：PC10
- LED 为低电平点亮
- LED 任务周期：50 tick，即每 500 ms 翻转一次
- 完整亮灭周期：1 s
- LED 翻转在主循环执行，不在定时器中断内执行

## 初始化顺序

1. 初始化 GPIO。
2. 初始化 TIM6。
3. 启动 TIM6 更新中断。
4. 初始化其他外设。
5. 主循环读取节拍并运行到期任务。

如果 TIM6 初始化或中断启动失败，进入现有 `Error_Handler()`。

## CubeMX 可维护性

TIM6、NVIC 和 HAL TIM 模块通过 `DM2.1_BAT.ioc` 配置生成。用户调度代码放在 CubeMX 的 `USER CODE` 区域，确保后续重新生成代码时不会丢失。

## 验证

- 检查 `.ioc` 中 TIM6 参数和 `TIM6_DAC_IRQn`。
- 检查生成的中断处理函数调用 `HAL_TIM_IRQHandler(&htim6)`。
- 检查回调仅递增节拍计数器。
- 检查 LED 任务使用 50 tick 周期并在主循环翻转 PC10。
- 执行干净构建，要求编译和链接成功且无新增警告。
