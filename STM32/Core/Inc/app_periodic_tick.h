#ifndef APP_PERIODIC_TICK_H
#define APP_PERIODIC_TICK_H

#include <stdint.h>

/* 获取应用层 2 ms 软件节拍，供主循环调度非阻塞用户任务。 */
uint32_t App_PeriodicTick_Get(void);

#endif /* APP_PERIODIC_TICK_H */
