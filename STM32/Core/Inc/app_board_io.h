#ifndef APP_BOARD_IO_H
#define APP_BOARD_IO_H

#include "stm32f4xx_hal.h"

#define APP_BOARD_IO_DEFAULT_FAN_LEVEL 4U
#define APP_BOARD_IO_FAN_PULSES_PER_REV 2U
#define APP_BOARD_IO_KEY_DEBOUNCE_TICKS 10U
#define APP_BOARD_IO_TACH_TIMEOUT_TICKS 750U

typedef struct
{
  uint16_t fan1_rpm;
  uint16_t fan2_rpm;
  uint8_t fan_level;
  uint8_t key_bitmap;
} App_BoardIO_Snapshot;

HAL_StatusTypeDef App_BoardIO_Init(TIM_HandleTypeDef *pwm_timer,
                                   TIM_HandleTypeDef *tach_timer);
void App_BoardIO_Run(uint32_t current_tick);
uint8_t App_BoardIO_SetFanLevel(uint8_t level);
uint8_t App_BoardIO_GetFanLevel(void);
void App_BoardIO_GetSnapshot(App_BoardIO_Snapshot *snapshot);
void App_BoardIO_CaptureCallback(TIM_HandleTypeDef *timer);

#endif
