#include "app_periodic_tick.h"

#include "main.h"

#include <stdint.h>

/*
 * TIM6 每 2 ms 进入一次中断，形成应用层统一软件节拍。
 * 中断里只递增计数，LED、UART5、超声波等用户任务都在主循环中根据该 tick 调度。
 */
static volatile uint32_t s_periodic_tick = 0U;

/**
  * @brief 获取 TIM6 周期节拍计数值。
  * @param None
  * @retval 当前节拍计数值，每 2 ms 增加 1。
  */
uint32_t App_PeriodicTick_Get(void)
{
  return s_periodic_tick;
}

/**
  * @brief HAL 定时器周期到达回调函数。
  * @param htim 触发回调的定时器句柄指针。
  * @retval None
  */
void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim)
{
  if (htim->Instance == TIM6)
  {
    /* 中断里只维护节拍计数，具体任务放到主循环执行。 */
    s_periodic_tick++;
  }
}
