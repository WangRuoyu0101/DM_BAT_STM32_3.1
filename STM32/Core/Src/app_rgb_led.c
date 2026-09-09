#include "app_rgb_led.h"

#include "main.h"

#include <stddef.h>

#define APP_RGB_LED_SLOW_BLINK_HALF_PERIOD_TICKS 250U
#define APP_RGB_LED_MEDIUM_BLINK_HALF_PERIOD_TICKS 125U
#define APP_RGB_LED_FAST_BLINK_HALF_PERIOD_TICKS 63U
#define APP_RGB_LED_COUNT 3U

#ifndef APP_RGB_LED_CYCLE_NOW
#define APP_RGB_LED_CYCLE_NOW() DWT->CYCCNT
#endif

#ifndef APP_RGB_LED_WRITE_PIN
#define APP_RGB_LED_WRITE_PIN(value) (RGB_GPIO_Port->BSRR = (value))
#endif

static App_RgbLedState s_state;
static uint32_t s_last_tick;
static uint32_t s_current_tick;
static uint32_t s_bit_cycles;
static uint32_t s_t0h_cycles;
static uint32_t s_t1h_cycles;
static uint32_t s_reset_cycles;

static void App_RgbLed_WaitUntil(uint32_t deadline)
{
  while ((int32_t)(APP_RGB_LED_CYCLE_NOW() - deadline) < 0)
  {
  }
}

static void App_RgbLed_SendByte(uint8_t value)
{
  uint8_t bit;

  for (bit = 0U; bit < 8U; bit++)
  {
    uint32_t high_cycles = ((value & 0x80U) != 0U) ? s_t1h_cycles : s_t0h_cycles;
    uint32_t deadline;

    APP_RGB_LED_WRITE_PIN(RGB_Pin);
    deadline = APP_RGB_LED_CYCLE_NOW();
    App_RgbLed_WaitUntil(deadline + high_cycles);
    APP_RGB_LED_WRITE_PIN((uint32_t)RGB_Pin << 16U);
    App_RgbLed_WaitUntil(deadline + s_bit_cycles);
    value <<= 1U;
  }
}

static uint8_t App_RgbLed_Linearize(uint8_t value)
{
  return (uint8_t)(((uint32_t)value * value + 127U) / 255U);
}

static void App_RgbLed_ApplyOutput(void)
{
  uint8_t red = 0U;
  uint8_t green = 0U;
  uint8_t blue = 0U;
  uint8_t led;
  uint32_t primask;

  if (s_state.output_on != 0U)
  {
    red = (uint8_t)((App_RgbLed_Linearize(s_state.red) * s_state.brightness + 50U) / 100U);
    green = (uint8_t)((App_RgbLed_Linearize(s_state.green) * s_state.brightness + 50U) / 100U);
    blue = (uint8_t)((App_RgbLed_Linearize(s_state.blue) * s_state.brightness + 50U) / 100U);
  }

  primask = __get_PRIMASK();
  __disable_irq();
  for (led = 0U; led < APP_RGB_LED_COUNT; led++)
  {
    App_RgbLed_SendByte(green);
    App_RgbLed_SendByte(red);
    App_RgbLed_SendByte(blue);
  }
  APP_RGB_LED_WRITE_PIN((uint32_t)RGB_Pin << 16U);
  if (primask == 0U)
  {
    __enable_irq();
  }
  App_RgbLed_WaitUntil(APP_RGB_LED_CYCLE_NOW() + s_reset_cycles);
}

static uint32_t App_RgbLed_HalfPeriodTicks(void)
{
  switch ((App_RgbLedMode)s_state.mode)
  {
    case APP_RGB_LED_MODE_SLOW_BLINK:
      return APP_RGB_LED_SLOW_BLINK_HALF_PERIOD_TICKS;

    case APP_RGB_LED_MODE_MEDIUM_BLINK:
      return APP_RGB_LED_MEDIUM_BLINK_HALF_PERIOD_TICKS;

    case APP_RGB_LED_MODE_FAST_BLINK:
      return APP_RGB_LED_FAST_BLINK_HALF_PERIOD_TICKS;

    default:
      return 0U;
  }
}

void App_RgbLed_Init(void)
{
  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
  DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
  DWT->CYCCNT = 0U;

  s_bit_cycles = (SystemCoreClock + 400000U) / 800000U;
  s_t0h_cycles = (uint32_t)(((uint64_t)SystemCoreClock * 200U + 500000000U) / 1000000000U);
  s_t1h_cycles = (uint32_t)(((uint64_t)SystemCoreClock * 550U + 500000000U) / 1000000000U);
  s_reset_cycles = SystemCoreClock / 8000U;

  s_state.red = APP_RGB_LED_DEFAULT_RED;
  s_state.green = APP_RGB_LED_DEFAULT_GREEN;
  s_state.blue = APP_RGB_LED_DEFAULT_BLUE;
  s_state.brightness = APP_RGB_LED_DEFAULT_BRIGHTNESS;
  s_state.mode = APP_RGB_LED_MODE_SLOW_BLINK;
  s_state.output_on = 1U;
  s_last_tick = 0U;
  s_current_tick = 0U;
  App_RgbLed_ApplyOutput();
}

void App_RgbLed_Run(uint32_t current_tick)
{
  uint32_t half_period = App_RgbLed_HalfPeriodTicks();

  s_current_tick = current_tick;
  if ((half_period != 0U) && ((uint32_t)(current_tick - s_last_tick) >= half_period))
  {
    s_last_tick = current_tick;
    s_state.output_on ^= 1U;
    App_RgbLed_ApplyOutput();
  }
}

uint8_t App_RgbLed_Set(uint8_t red, uint8_t green, uint8_t blue,
                       uint8_t brightness, App_RgbLedMode mode)
{
  if (brightness > 100U)
  {
    return APP_RGB_LED_RESULT_INVALID_BRIGHTNESS;
  }
  if ((mode < APP_RGB_LED_MODE_OFF) || (mode > APP_RGB_LED_MODE_FAST_BLINK))
  {
    return APP_RGB_LED_RESULT_INVALID_MODE;
  }

  s_state.red = red;
  s_state.green = green;
  s_state.blue = blue;
  s_state.brightness = brightness;
  s_state.mode = (uint8_t)mode;
  s_state.output_on = (mode == APP_RGB_LED_MODE_OFF) ? 0U : 1U;
  s_last_tick = s_current_tick;
  App_RgbLed_ApplyOutput();
  return APP_RGB_LED_RESULT_OK;
}

void App_RgbLed_GetState(App_RgbLedState *state)
{
  if (state != NULL)
  {
    *state = s_state;
  }
}
