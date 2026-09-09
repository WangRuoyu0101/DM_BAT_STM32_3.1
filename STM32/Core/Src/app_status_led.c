#include "app_status_led.h"

#include "main.h"

#include <stdint.h>

/*
 * LED_RUN 是应用正常运行指示灯。
 * TIM6 周期为 2 ms，500 个 tick 对应 1000 ms 翻转一次。
 * 进入 bootloader 请求复位等待窗口后，运行灯由 UART5 模块接管为 250 ms 快闪。
 */
#define APP_STATUS_LED_PERIOD_TICKS 500U

static uint32_t s_last_tick = 0U;

/**
  * @brief 初始化运行状态 LED 任务。
  * @param None
  * @retval None
  */
void App_StatusLed_Init(void)
{
  s_last_tick = 0U;
}

/**
  * @brief 根据当前节拍周期性翻转运行状态 LED。
  * @param current_tick 当前 2 ms 周期计数值。
  * @retval None
  */
void App_StatusLed_Run(uint32_t current_tick)
{
  if ((uint32_t)(current_tick - s_last_tick) >= APP_STATUS_LED_PERIOD_TICKS)
  {
    /* 使用无符号差值判断，tick 回绕时仍能保持周期。 */
    s_last_tick = current_tick;
    HAL_GPIO_TogglePin(LED_RUN_GPIO_Port, LED_RUN_Pin);
  }
}
