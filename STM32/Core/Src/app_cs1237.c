#include "app_cs1237.h"

#include <stddef.h>

#define APP_CS1237_WRITE_REG 0x65U
#define APP_CS1237_READ_REG 0x56U
#define APP_CS1237_READY_TIMEOUT_MS 400U
#define APP_CS1237_SETTLING_SAMPLES 3U

#define APP_CS1237_CONFIG_REF_ON 0x00U
#define APP_CS1237_CONFIG_RATE_10HZ 0x00U
#define APP_CS1237_CONFIG_PGA_1 0x00U
#define APP_CS1237_CONFIG_PGA_128 0x0CU

static App_CS1237_Snapshot s_snapshot = {
  0,
  APP_CS1237_CHANNEL_DIFFERENTIAL,
  0U,
  APP_CS1237_RESULT_TIMEOUT
};
static uint8_t s_settling_samples = APP_CS1237_SETTLING_SAMPLES;

static void App_CS1237_DelayUs(uint32_t microseconds)
{
  uint32_t start = DWT->CYCCNT;
  uint32_t cycles = (SystemCoreClock / 1000000U) * microseconds;

  while ((uint32_t)(DWT->CYCCNT - start) < cycles)
  {
  }
}

static void App_CS1237_SetDioMode(uint32_t mode)
{
  GPIO_InitTypeDef gpio = {0};

  gpio.Pin = CS1237_DIO_Pin;
  gpio.Mode = mode;
  gpio.Pull = GPIO_NOPULL;
  gpio.Speed = GPIO_SPEED_FREQ_HIGH;
  HAL_GPIO_Init(CS1237_DIO_GPIO_Port, &gpio);
}

static void App_CS1237_PulseClock(void)
{
  HAL_GPIO_WritePin(CS1237_CLK_GPIO_Port, CS1237_CLK_Pin, GPIO_PIN_SET);
  App_CS1237_DelayUs(2U);
  HAL_GPIO_WritePin(CS1237_CLK_GPIO_Port, CS1237_CLK_Pin, GPIO_PIN_RESET);
  App_CS1237_DelayUs(2U);
}

static App_CS1237_Result App_CS1237_WaitReady(void)
{
  uint32_t start = HAL_GetTick();

  while (HAL_GPIO_ReadPin(CS1237_DIO_GPIO_Port, CS1237_DIO_Pin) == GPIO_PIN_SET)
  {
    if ((HAL_GetTick() - start) >= APP_CS1237_READY_TIMEOUT_MS)
    {
      return APP_CS1237_RESULT_TIMEOUT;
    }
  }
  return APP_CS1237_RESULT_OK;
}

static uint8_t App_CS1237_BuildConfig(App_CS1237_Channel channel)
{
  uint8_t pga = (channel == APP_CS1237_CHANNEL_TEMPERATURE)
    ? APP_CS1237_CONFIG_PGA_1
    : APP_CS1237_CONFIG_PGA_128;

  return (uint8_t)(
    APP_CS1237_CONFIG_REF_ON |
    APP_CS1237_CONFIG_RATE_10HZ |
    pga |
    (uint8_t)channel);
}

static App_CS1237_Result App_CS1237_WriteReg(uint8_t config)
{
  uint8_t index;
  uint8_t command = APP_CS1237_WRITE_REG;
  App_CS1237_Result result;

  App_CS1237_SetDioMode(GPIO_MODE_INPUT);
  HAL_GPIO_WritePin(CS1237_CLK_GPIO_Port, CS1237_CLK_Pin, GPIO_PIN_RESET);
  result = App_CS1237_WaitReady();
  if (result != APP_CS1237_RESULT_OK)
  {
    return result;
  }

  for (index = 0U; index < 26U; index++)
  {
    App_CS1237_PulseClock();
  }

  App_CS1237_SetDioMode(GPIO_MODE_OUTPUT_PP);
  HAL_GPIO_WritePin(CS1237_DIO_GPIO_Port, CS1237_DIO_Pin, GPIO_PIN_SET);
  for (index = 0U; index < 3U; index++)
  {
    App_CS1237_PulseClock();
  }
  for (index = 0U; index < 7U; index++)
  {
    HAL_GPIO_WritePin(
      CS1237_DIO_GPIO_Port,
      CS1237_DIO_Pin,
      ((command & 0x40U) != 0U) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    App_CS1237_PulseClock();
    command <<= 1U;
  }
  HAL_GPIO_WritePin(CS1237_DIO_GPIO_Port, CS1237_DIO_Pin, GPIO_PIN_RESET);
  App_CS1237_PulseClock();
  for (index = 0U; index < 8U; index++)
  {
    HAL_GPIO_WritePin(
      CS1237_DIO_GPIO_Port,
      CS1237_DIO_Pin,
      ((config & 0x80U) != 0U) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    App_CS1237_PulseClock();
    config <<= 1U;
  }
  HAL_GPIO_WritePin(CS1237_DIO_GPIO_Port, CS1237_DIO_Pin, GPIO_PIN_RESET);
  App_CS1237_PulseClock();
  App_CS1237_SetDioMode(GPIO_MODE_INPUT);
  return APP_CS1237_RESULT_OK;
}

static App_CS1237_Result App_CS1237_ReadReg(uint8_t *config)
{
  uint8_t index;
  uint8_t command = APP_CS1237_READ_REG;
  uint8_t value = 0U;
  App_CS1237_Result result;

  if (config == NULL)
  {
    return APP_CS1237_RESULT_VERIFY_FAILED;
  }
  App_CS1237_SetDioMode(GPIO_MODE_INPUT);
  result = App_CS1237_WaitReady();
  if (result != APP_CS1237_RESULT_OK)
  {
    return result;
  }
  for (index = 0U; index < 26U; index++)
  {
    App_CS1237_PulseClock();
  }

  App_CS1237_SetDioMode(GPIO_MODE_OUTPUT_PP);
  HAL_GPIO_WritePin(CS1237_DIO_GPIO_Port, CS1237_DIO_Pin, GPIO_PIN_SET);
  for (index = 0U; index < 3U; index++)
  {
    App_CS1237_PulseClock();
  }
  for (index = 0U; index < 7U; index++)
  {
    HAL_GPIO_WritePin(
      CS1237_DIO_GPIO_Port,
      CS1237_DIO_Pin,
      ((command & 0x40U) != 0U) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    App_CS1237_PulseClock();
    command <<= 1U;
  }
  HAL_GPIO_WritePin(CS1237_DIO_GPIO_Port, CS1237_DIO_Pin, GPIO_PIN_SET);
  App_CS1237_SetDioMode(GPIO_MODE_INPUT);
  App_CS1237_PulseClock();
  for (index = 0U; index < 8U; index++)
  {
    value <<= 1U;
    HAL_GPIO_WritePin(CS1237_CLK_GPIO_Port, CS1237_CLK_Pin, GPIO_PIN_SET);
    App_CS1237_DelayUs(2U);
    if (HAL_GPIO_ReadPin(CS1237_DIO_GPIO_Port, CS1237_DIO_Pin) == GPIO_PIN_SET)
    {
      value |= 1U;
    }
    HAL_GPIO_WritePin(CS1237_CLK_GPIO_Port, CS1237_CLK_Pin, GPIO_PIN_RESET);
    App_CS1237_DelayUs(2U);
  }
  App_CS1237_PulseClock();
  *config = value;
  return APP_CS1237_RESULT_OK;
}

static int32_t App_CS1237_ReadAdc(void)
{
  uint8_t index;
  int32_t raw = 0;
  uint32_t primask = __get_PRIMASK();

  __disable_irq();
  for (index = 0U; index < 24U; index++)
  {
    raw <<= 1;
    HAL_GPIO_WritePin(CS1237_CLK_GPIO_Port, CS1237_CLK_Pin, GPIO_PIN_SET);
    App_CS1237_DelayUs(2U);
    if (HAL_GPIO_ReadPin(CS1237_DIO_GPIO_Port, CS1237_DIO_Pin) == GPIO_PIN_SET)
    {
      raw |= 1;
    }
    HAL_GPIO_WritePin(CS1237_CLK_GPIO_Port, CS1237_CLK_Pin, GPIO_PIN_RESET);
    App_CS1237_DelayUs(2U);
  }
  for (index = 0U; index < 3U; index++)
  {
    App_CS1237_PulseClock();
  }
  if (primask == 0U)
  {
    __enable_irq();
  }
  if ((raw & (int32_t)0x00800000) != 0)
  {
    raw |= (int32_t)0xFF000000;
  }
  return raw;
}

App_CS1237_Result App_CS1237_SetChannel(App_CS1237_Channel channel)
{
  uint8_t expected;
  uint8_t actual = 0U;
  App_CS1237_Result result;

  if ((channel == APP_CS1237_CHANNEL_RESERVED) ||
      ((uint8_t)channel > (uint8_t)APP_CS1237_CHANNEL_INTERNAL_SHORT))
  {
    return APP_CS1237_RESULT_INVALID_CHANNEL;
  }

  expected = App_CS1237_BuildConfig(channel);
  s_snapshot.channel = channel;
  s_snapshot.valid = 0U;
  s_snapshot.error = APP_CS1237_RESULT_OK;
  s_settling_samples = APP_CS1237_SETTLING_SAMPLES;

  result = App_CS1237_WriteReg(expected);
  if (result == APP_CS1237_RESULT_OK)
  {
    result = App_CS1237_ReadReg(&actual);
  }
  if ((result == APP_CS1237_RESULT_OK) && (actual != expected))
  {
    result = APP_CS1237_RESULT_VERIFY_FAILED;
  }
  s_snapshot.error = (uint8_t)result;
  return result;
}

App_CS1237_Result App_CS1237_Init(void)
{
  GPIO_InitTypeDef gpio = {0};

  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
  DWT->CYCCNT = 0U;
  DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;

  gpio.Pin = CS1237_CLK_Pin;
  gpio.Mode = GPIO_MODE_OUTPUT_PP;
  gpio.Pull = GPIO_NOPULL;
  gpio.Speed = GPIO_SPEED_FREQ_HIGH;
  HAL_GPIO_Init(CS1237_CLK_GPIO_Port, &gpio);
  HAL_GPIO_WritePin(CS1237_CLK_GPIO_Port, CS1237_CLK_Pin, GPIO_PIN_RESET);
  App_CS1237_SetDioMode(GPIO_MODE_INPUT);
  return App_CS1237_SetChannel(APP_CS1237_CHANNEL_DIFFERENTIAL);
}

void App_CS1237_Run(void)
{
  if (s_snapshot.error != APP_CS1237_RESULT_OK)
  {
    return;
  }
  if (HAL_GPIO_ReadPin(CS1237_DIO_GPIO_Port, CS1237_DIO_Pin) != GPIO_PIN_RESET)
  {
    return;
  }

  s_snapshot.raw_adc = App_CS1237_ReadAdc();
  if (s_settling_samples > 0U)
  {
    s_settling_samples--;
    s_snapshot.valid = 0U;
  }
  else
  {
    s_snapshot.valid = 1U;
  }
}

void App_CS1237_GetSnapshot(App_CS1237_Snapshot *snapshot)
{
  if (snapshot != NULL)
  {
    *snapshot = s_snapshot;
  }
}
