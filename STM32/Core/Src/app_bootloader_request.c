#include "app_bootloader_request.h"

#include "stm32f4xx_hal.h"

#include <stdint.h>

/*
 * 应用与 bootloader 之间通过 RTC backup register 传递一次性请求标志。
 * 该寄存器在软件复位后保持，因此应用收到上位机请求后可以先置位，
 * 再调用 NVIC_SystemReset()，bootloader 启动后读取并清除该标志。
 */
static void App_BootloaderRequest_EnableBackupAccess(void)
{
  __HAL_RCC_PWR_CLK_ENABLE();
  PWR->CR |= PWR_CR_DBP;
  RCC->BDCR |= RCC_BDCR_RTCEN;
}

/**
  * @brief 写入进入 bootloader 的一次性请求标志。
  * @param None
  * @retval None
  */
void App_BootloaderRequest_SetFlag(void)
{
  App_BootloaderRequest_EnableBackupAccess();
  RTC->BKP0R = APP_BOOTLOADER_REQUEST_MAGIC;
}

/**
  * @brief 读取并清除 bootloader 请求标志。
  * @param None
  * @retval 1 表示本次复位由应用请求进入 bootloader，0 表示普通启动。
  */
uint8_t App_BootloaderRequest_ConsumeFlag(void)
{
  uint8_t flag_is_set;

  App_BootloaderRequest_EnableBackupAccess();
  flag_is_set = (RTC->BKP0R == APP_BOOTLOADER_REQUEST_MAGIC) ? 1U : 0U;
  RTC->BKP0R = 0U;

  return flag_is_set;
}
