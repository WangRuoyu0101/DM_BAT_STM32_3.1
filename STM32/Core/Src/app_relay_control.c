#include "app_relay_control.h"

#include "main.h"

#include <stddef.h>
#include <stdint.h>

#define APP_RELAY_CONTROL_FLASH_PULSE_TICKS 100U
#define APP_RELAY_CONTROL_STARTUP_ALERT_TICKS 500U

typedef struct
{
  uint8_t channel_id;
  GPIO_TypeDef *port;
  uint16_t pin;
} App_RelayControlChannel;

/*
 * USB CDC 协议中的 GPIO channel_id 与实际输出引脚映射。
 * 数组顺序同时决定状态位图 bit 位置：bit0 对应第 1 项，bit5 对应第 6 项。
 */
static const App_RelayControlChannel s_channels[] = {
  /* SIGNAL-FLASH-CTR */
  {APP_COMM_GPIO_CHANNEL_FLASH_CTR, GPIOC, GPIO_PIN_1},
  /* SIGNAL-LED */
  {APP_COMM_GPIO_CHANNEL_LED, GPIOE, GPIO_PIN_7},
  /* SIGNAL-BEE */
  {APP_COMM_GPIO_CHANNEL_BEE, GPIOE, GPIO_PIN_2},
  /* SIGNAL-MOTOR */
  {APP_COMM_GPIO_CHANNEL_MOTOR, GPIOD, GPIO_PIN_8},
  /* SIGNAL-FLASH */
  {APP_COMM_GPIO_CHANNEL_FLASH, GPIOC, GPIO_PIN_3},
  /* SIGNAL-SOUND */
  {APP_COMM_GPIO_CHANNEL_SOUND, GPIOD, GPIO_PIN_12},
};

static uint8_t s_flash_pulse_active = 0U;
static uint32_t s_flash_pulse_start_tick = 0U;
static uint8_t s_startup_alert_active = 0U;
static uint32_t s_startup_alert_start_tick = 0U;

void App_RelayControl_Init(uint32_t current_tick)
{
  /* 音频功放默认使能，确保主机未下发 GPIO 命令时也可以播放声音。 */
  HAL_GPIO_WritePin(GPIOD, GPIO_PIN_12, GPIO_PIN_SET);
  /* 上电声光提示保持 1 秒。 */
  HAL_GPIO_WritePin(GPIOE, GPIO_PIN_2, GPIO_PIN_SET);
  s_startup_alert_start_tick = current_tick;
  s_startup_alert_active = 1U;
}

/**
  * @brief 根据通道 ID 查找继电器控制 GPIO。
  * @param channel_id 控制通道 ID。
  * @retval 通道配置指针；返回 NULL 表示通道无效。
  */
static const App_RelayControlChannel *App_RelayControl_FindChannel(uint8_t channel_id)
{
  size_t index;

  for (index = 0U; index < (sizeof(s_channels) / sizeof(s_channels[0])); index++)
  {
    if (s_channels[index].channel_id == channel_id)
    {
      return &s_channels[index];
    }
  }

  return NULL;
}

/**
  * @brief 执行主机下发的 GPIO 高低电平控制命令。
  * @param control GPIO 控制命令，包含通道 ID 和目标电平。
  * @retval 控制结果码，APP_COMM_CONTROL_RESULT_OK 表示执行成功。
  */
uint8_t App_RelayControl_Apply(const App_CommGpioControl *control, uint32_t current_tick)
{
  const App_RelayControlChannel *channel;
  GPIO_PinState pin_state;

  if (control == NULL)
  {
    return APP_COMM_CONTROL_RESULT_LENGTH_ERROR;
  }

  channel = App_RelayControl_FindChannel(control->channel_id);
  if (channel == NULL)
  {
    return APP_COMM_CONTROL_RESULT_INVALID_CHANNEL;
  }

  if (control->level == APP_COMM_GPIO_LEVEL_LOW)
  {
    pin_state = GPIO_PIN_RESET;
  }
  else if (control->level == APP_COMM_GPIO_LEVEL_HIGH)
  {
    pin_state = GPIO_PIN_SET;
  }
  else
  {
    return APP_COMM_CONTROL_RESULT_INVALID_LEVEL;
  }

  if (control->channel_id == APP_COMM_GPIO_CHANNEL_FLASH_CTR)
  {
    if (control->level == APP_COMM_GPIO_LEVEL_LOW)
    {
      s_flash_pulse_active = 0U;
    }
    else
    {
      s_flash_pulse_start_tick = current_tick;
      s_flash_pulse_active = 1U;
    }
  }
  else if (control->channel_id == APP_COMM_GPIO_CHANNEL_BEE)
  {
    s_startup_alert_active = 0U;
  }

  HAL_GPIO_WritePin(channel->port, channel->pin, pin_state);

  return APP_COMM_CONTROL_RESULT_OK;
}

void App_RelayControl_Service(uint32_t current_tick)
{
  if ((s_flash_pulse_active != 0U) &&
      ((uint32_t)(current_tick - s_flash_pulse_start_tick) >= APP_RELAY_CONTROL_FLASH_PULSE_TICKS))
  {
    HAL_GPIO_WritePin(GPIOC, GPIO_PIN_1, GPIO_PIN_RESET);
    s_flash_pulse_active = 0U;
  }
  if ((s_startup_alert_active != 0U) &&
      ((uint32_t)(current_tick - s_startup_alert_start_tick) >= APP_RELAY_CONTROL_STARTUP_ALERT_TICKS))
  {
    HAL_GPIO_WritePin(GPIOE, GPIO_PIN_2, GPIO_PIN_RESET);
    s_startup_alert_active = 0U;
  }
}

/**
  * @brief 获取所有继电器控制 GPIO 的当前输出状态位图。
  * @param None
  * @retval GPIO 状态位图，bit0 对应通道 0x01，bit5 对应通道 0x06。
  */
uint8_t App_RelayControl_GetBitmap(void)
{
  uint8_t bitmap = 0U;
  size_t index;

  for (index = 0U; index < (sizeof(s_channels) / sizeof(s_channels[0])); index++)
  {
    if (HAL_GPIO_ReadPin(s_channels[index].port, s_channels[index].pin) == GPIO_PIN_SET)
    {
      bitmap = (uint8_t)(bitmap | (1U << index));
    }
  }

  return bitmap;
}
