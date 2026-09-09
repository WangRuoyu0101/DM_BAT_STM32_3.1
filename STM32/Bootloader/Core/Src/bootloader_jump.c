#include "bootloader_jump.h"

#include "bootloader_flash.h"
#include "stm32f4xx_hal.h"

#include <stdint.h>

typedef void (*Bootloader_AppEntry)(void);

uint8_t Bootloader_IsApplicationValid(void)
{
  return Bootloader_FlashIsApplicationValid();
}

void Bootloader_JumpToApplication(void)
{
  uint32_t stack_pointer = *(volatile uint32_t *)APP_FLASH_BASE;
  uint32_t reset_handler = *(volatile uint32_t *)(APP_FLASH_BASE + 4U);
  Bootloader_AppEntry app_reset_handler = (Bootloader_AppEntry)reset_handler;

  if (Bootloader_IsApplicationValid() == 0U)
  {
    return;
  }

  __disable_irq();
  HAL_DeInit();
  SysTick->CTRL = 0U;
  SysTick->LOAD = 0U;
  SysTick->VAL = 0U;
  SCB->VTOR = APP_FLASH_BASE;
  __set_MSP(stack_pointer);
  __enable_irq();
  app_reset_handler();
}
