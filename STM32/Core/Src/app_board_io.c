#include "app_board_io.h"

#include "main.h"

#define APP_BOARD_IO_TACH_HZ 100000UL

static const uint16_t s_fan_pulses[] = {1680U, 3360U, 5040U, 6720U};
static TIM_HandleTypeDef *s_pwm_timer;
static TIM_HandleTypeDef *s_tach_timers[2];
static volatile uint16_t s_capture[2];
static volatile uint8_t s_capture_pending[2];
static uint16_t s_previous_capture[2];
static uint32_t s_last_tach_tick[2];
static uint8_t s_have_previous[2];
static uint8_t s_key_candidate[3];
static uint8_t s_key_stable[3];
static uint8_t s_key_count[3];
static uint32_t s_last_run_tick;
static App_BoardIO_Snapshot s_snapshot;

static uint16_t App_BoardIO_RpmFromDelta(uint16_t delta)
{
  uint32_t rpm;

  if (delta == 0U)
  {
    return 0U;
  }
  rpm = (60UL * APP_BOARD_IO_TACH_HZ) /
        ((uint32_t)delta * APP_BOARD_IO_FAN_PULSES_PER_REV);
  return (rpm > UINT16_MAX) ? UINT16_MAX : (uint16_t)rpm;
}

HAL_StatusTypeDef App_BoardIO_Init(TIM_HandleTypeDef *pwm_timer,
                                   TIM_HandleTypeDef *fan1_tach_timer,
                                   TIM_HandleTypeDef *fan2_tach_timer)
{
  if ((pwm_timer == NULL) || (fan1_tach_timer == NULL) || (fan2_tach_timer == NULL))
  {
    return HAL_ERROR;
  }

  s_pwm_timer = pwm_timer;
  s_tach_timers[0] = fan1_tach_timer;
  s_tach_timers[1] = fan2_tach_timer;
  s_snapshot.fan_level = APP_BOARD_IO_DEFAULT_FAN_LEVEL;
  __HAL_TIM_SET_COMPARE(s_pwm_timer, TIM_CHANNEL_1,
                        s_fan_pulses[APP_BOARD_IO_DEFAULT_FAN_LEVEL - 1U]);

  if (HAL_TIM_PWM_Start(s_pwm_timer, TIM_CHANNEL_1) != HAL_OK)
  {
    return HAL_ERROR;
  }
  if (HAL_TIM_IC_Start_IT(s_tach_timers[0], TIM_CHANNEL_2) != HAL_OK)
  {
    return HAL_ERROR;
  }
  if (HAL_TIM_IC_Start_IT(s_tach_timers[1], TIM_CHANNEL_1) != HAL_OK)
  {
    return HAL_ERROR;
  }
  return HAL_OK;
}

uint8_t App_BoardIO_SetFanLevel(uint8_t level)
{
  if ((level < 1U) || (level > 4U) || (s_pwm_timer == NULL))
  {
    return 2U;
  }
  __HAL_TIM_SET_COMPARE(s_pwm_timer, TIM_CHANNEL_1, s_fan_pulses[level - 1U]);
  s_snapshot.fan_level = level;
  return 0U;
}

uint8_t App_BoardIO_GetFanLevel(void)
{
  return s_snapshot.fan_level;
}

static void App_BoardIO_UpdateKey(uint8_t index, uint8_t pressed)
{
  if (pressed != s_key_candidate[index])
  {
    s_key_candidate[index] = pressed;
    s_key_count[index] = 1U;
  }
  else if (s_key_count[index] < APP_BOARD_IO_KEY_DEBOUNCE_TICKS)
  {
    s_key_count[index]++;
    if (s_key_count[index] == APP_BOARD_IO_KEY_DEBOUNCE_TICKS)
    {
      s_key_stable[index] = pressed;
    }
  }
}

void App_BoardIO_Run(uint32_t current_tick)
{
  uint8_t index;

  if (current_tick == s_last_run_tick)
  {
    return;
  }
  s_last_run_tick = current_tick;

  App_BoardIO_UpdateKey(0U, HAL_GPIO_ReadPin(KEY1_GPIO_Port, KEY1_Pin) == GPIO_PIN_RESET);
  App_BoardIO_UpdateKey(1U, HAL_GPIO_ReadPin(KEY2_GPIO_Port, KEY2_Pin) == GPIO_PIN_RESET);
  App_BoardIO_UpdateKey(2U, HAL_GPIO_ReadPin(KEY3_GPIO_Port, KEY3_Pin) == GPIO_PIN_RESET);
  s_snapshot.key_bitmap = (uint8_t)(s_key_stable[0] |
                                    (s_key_stable[1] << 1U) |
                                    (s_key_stable[2] << 2U));

  for (index = 0U; index < 2U; index++)
  {
    if (s_capture_pending[index] != 0U)
    {
      uint16_t capture = s_capture[index];
      s_capture_pending[index] = 0U;
      if (s_have_previous[index] != 0U)
      {
        uint16_t rpm = App_BoardIO_RpmFromDelta((uint16_t)(capture - s_previous_capture[index]));
        if (index == 0U)
        {
          s_snapshot.fan1_rpm = rpm;
        }
        else
        {
          s_snapshot.fan2_rpm = rpm;
        }
      }
      s_previous_capture[index] = capture;
      s_have_previous[index] = 1U;
      s_last_tach_tick[index] = current_tick;
    }
    else if ((current_tick - s_last_tach_tick[index]) > APP_BOARD_IO_TACH_TIMEOUT_TICKS)
    {
      if (index == 0U)
      {
        s_snapshot.fan1_rpm = 0U;
      }
      else
      {
        s_snapshot.fan2_rpm = 0U;
      }
      s_have_previous[index] = 0U;
    }
  }
}

void App_BoardIO_GetSnapshot(App_BoardIO_Snapshot *snapshot)
{
  if (snapshot != NULL)
  {
    *snapshot = s_snapshot;
  }
}

void App_BoardIO_CaptureCallback(TIM_HandleTypeDef *timer)
{
  if (timer == NULL)
  {
    return;
  }
  if ((timer == s_tach_timers[0]) && (timer->Channel == HAL_TIM_ACTIVE_CHANNEL_2))
  {
    s_capture[0] = (uint16_t)HAL_TIM_ReadCapturedValue(timer, TIM_CHANNEL_2);
    s_capture_pending[0] = 1U;
  }
  else if ((timer == s_tach_timers[1]) && (timer->Channel == HAL_TIM_ACTIVE_CHANNEL_1))
  {
    s_capture[1] = (uint16_t)HAL_TIM_ReadCapturedValue(timer, TIM_CHANNEL_1);
    s_capture_pending[1] = 1U;
  }
}

void HAL_TIM_IC_CaptureCallback(TIM_HandleTypeDef *timer)
{
  App_BoardIO_CaptureCallback(timer);
}
