#ifndef APP_UART5_SLAVE_H
#define APP_UART5_SLAVE_H

#include "app_comm_protocol.h"
#include "app_board_io.h"
#include "app_bootloader_request.h"
#include "app_cs1237.h"
#include "app_relay_control.h"
#include "app_rgb_led.h"
#include "app_ultrasonic_manager.h"
#include "main.h"

#include <stdint.h>

/* 初始化 UART5 应用协议从机节点，并启动二进制帧的单字节中断接收。 */
HAL_StatusTypeDef App_Uart5Slave_Init(UART_HandleTypeDef *huart);

/* 在主循环中处理已解析完成的 Jetson 主机帧，并通过 UART5 返回响应帧。 */
void App_Uart5Slave_Run(uint32_t current_tick);

/* 在其他主循环任务前优先处理 GPIO 控制帧，降低输出引脚变化延迟。 */
void App_Uart5Slave_RunFastGpio(uint32_t current_tick);

/* 返回当前是否正在等待软件复位进入 bootloader，用于主循环暂停普通运行灯任务。 */
uint8_t App_Uart5Slave_IsBootloaderResetPending(void);

/* UART5 接收完成回调入口，仅负责将字节喂给协议解析器并重新打开接收中断。 */
void App_Uart5Slave_HandleRxCplt(UART_HandleTypeDef *huart);

/* USB CDC 接收入口，复用 UART5 应用协议解析和响应。 */
void App_Uart5Slave_HandleUsbData(const uint8_t *data, uint32_t length);

/* USB CDC IN 传输完成回调入口，用于释放发送队列中的在途帧。 */
void App_Uart5Slave_HandleUsbTxComplete(void);

#endif /* APP_UART5_SLAVE_H */
