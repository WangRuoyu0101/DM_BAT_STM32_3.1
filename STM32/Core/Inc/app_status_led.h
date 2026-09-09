#ifndef APP_STATUS_LED_H
#define APP_STATUS_LED_H

#include <stdint.h>

/* 初始化主应用正常运行指示灯任务。 */
void App_StatusLed_Init(void);

/* 在主循环中按 2 ms 软件节拍周期性翻转 LED_RUN。 */
void App_StatusLed_Run(uint32_t current_tick);

#endif /* APP_STATUS_LED_H */
