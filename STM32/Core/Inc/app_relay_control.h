#ifndef APP_RELAY_CONTROL_H
#define APP_RELAY_CONTROL_H

#include "app_comm_protocol.h"

#include <stdint.h>

/* 执行 UART5 主机下发的 GPIO 控制命令。 */
uint8_t App_RelayControl_Apply(const App_CommGpioControl *control, uint32_t current_tick);

/* 在主循环中复位到期的爆闪切换脉冲。 */
void App_RelayControl_Service(uint32_t current_tick);

/* 读取所有受控 GPIO 的输出状态位图，bit0-bit5 对应协议通道 0x01-0x06。 */
uint8_t App_RelayControl_GetBitmap(void);

#endif /* APP_RELAY_CONTROL_H */
