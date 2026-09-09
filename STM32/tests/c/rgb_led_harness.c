#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "main.h"
#include "app_rgb_led.h"

CoreDebug_Type mock_core_debug;
DWT_Type mock_dwt;
GPIO_TypeDef mock_gpio;
uint32_t SystemCoreClock;

typedef struct
{
  uint32_t value;
  uint32_t cycle;
} PinWrite;

static PinWrite writes[256];
static size_t write_count;
static uint32_t cycle;
static uint32_t primask;

uint32_t mock_rgb_cycle_now(void)
{
  return cycle++;
}

void mock_rgb_write(uint32_t value)
{
  if (write_count < sizeof(writes) / sizeof(writes[0]))
  {
    writes[write_count].value = value;
    writes[write_count].cycle = cycle;
    write_count++;
  }
}

uint32_t mock_get_primask(void)
{
  return primask;
}

void mock_disable_irq(void)
{
  primask = 1U;
}

void mock_enable_irq(void)
{
  primask = 0U;
}

#include "../../Core/Src/app_rgb_led.c"

#define CHECK(condition) do { \
  if (!(condition)) { \
    fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition); \
    return 1; \
  } \
} while (0)

static void clear_writes(void)
{
  write_count = 0U;
  cycle = 0U;
  memset(writes, 0, sizeof(writes));
}

static uint8_t captured_byte(size_t byte_index)
{
  uint8_t value = 0U;
  size_t bit;

  for (bit = 0U; bit < 8U; bit++)
  {
    size_t index = (byte_index * 8U + bit) * 2U;
    uint32_t high_cycles = writes[index + 1U].cycle - writes[index].cycle;
    value = (uint8_t)((value << 1U) | ((high_cycles > 40U) ? 1U : 0U));
  }
  return value;
}

static uint32_t captured_high_cycles(size_t bit_index)
{
  size_t index = bit_index * 2U;
  return writes[index + 1U].cycle - writes[index].cycle;
}

static int check_state(uint8_t red, uint8_t green, uint8_t blue,
                       uint8_t brightness, uint8_t mode, uint8_t output_on)
{
  App_RgbLedState state;
  App_RgbLed_GetState(&state);
  return state.red == red && state.green == green && state.blue == blue
    && state.brightness == brightness && state.mode == mode
    && state.output_on == output_on;
}

int main(void)
{
  App_RgbLedState before;
  App_RgbLedState after;

  SystemCoreClock = 0U;
  clear_writes();
  App_RgbLed_Init();
  CHECK(write_count == 145U);

  SystemCoreClock = 80000000U;
  clear_writes();
  App_RgbLed_Init();
  CHECK(check_state(0U, 255U, 0U, 25U, APP_RGB_LED_MODE_SLOW_BLINK, 1U));
  CHECK(captured_byte(0U) == 64U);
  CHECK(captured_byte(1U) == 0U);
  CHECK(captured_byte(2U) == 0U);
  CHECK(captured_byte(3U) == 64U);
  CHECK(captured_byte(4U) == 0U);
  CHECK(captured_byte(5U) == 0U);
  CHECK(captured_byte(6U) == 64U);
  CHECK(captured_byte(7U) == 0U);
  CHECK(captured_byte(8U) == 0U);
  CHECK(captured_high_cycles(0U) <= 24U);
  CHECK(captured_high_cycles(1U) >= 44U);
  CHECK(cycle - writes[write_count - 1U].cycle >= 8000U);

  clear_writes();
  CHECK(App_RgbLed_Set(128U, 64U, 32U, 50U, APP_RGB_LED_MODE_STEADY)
        == APP_RGB_LED_RESULT_OK);
  CHECK(captured_byte(0U) == 8U);
  CHECK(captured_byte(1U) == 32U);
  CHECK(captured_byte(2U) == 2U);
  CHECK(captured_byte(3U) == 8U);
  CHECK(captured_byte(4U) == 32U);
  CHECK(captured_byte(5U) == 2U);
  CHECK(captured_byte(6U) == 8U);
  CHECK(captured_byte(7U) == 32U);
  CHECK(captured_byte(8U) == 2U);

  App_RgbLed_Init();
  clear_writes();
  CHECK(App_RgbLed_Set(1U, 2U, 3U, 100U, APP_RGB_LED_MODE_OFF)
        == APP_RGB_LED_RESULT_OK);
  CHECK(check_state(1U, 2U, 3U, 100U, APP_RGB_LED_MODE_OFF, 0U));
  App_RgbLed_Run(UINT32_MAX);
  CHECK(check_state(1U, 2U, 3U, 100U, APP_RGB_LED_MODE_OFF, 0U));

  App_RgbLed_Init();
  CHECK(App_RgbLed_Set(1U, 2U, 3U, 100U, APP_RGB_LED_MODE_STEADY)
        == APP_RGB_LED_RESULT_OK);
  App_RgbLed_Run(UINT32_MAX);
  CHECK(check_state(1U, 2U, 3U, 100U, APP_RGB_LED_MODE_STEADY, 1U));

  App_RgbLed_Init();
  CHECK(App_RgbLed_Set(1U, 2U, 3U, 100U, APP_RGB_LED_MODE_SLOW_BLINK)
        == APP_RGB_LED_RESULT_OK);
  App_RgbLed_Run(249U);
  CHECK(check_state(1U, 2U, 3U, 100U, APP_RGB_LED_MODE_SLOW_BLINK, 1U));
  App_RgbLed_Run(250U);
  CHECK(check_state(1U, 2U, 3U, 100U, APP_RGB_LED_MODE_SLOW_BLINK, 0U));

  App_RgbLed_Init();
  CHECK(App_RgbLed_Set(1U, 2U, 3U, 100U, APP_RGB_LED_MODE_MEDIUM_BLINK)
        == APP_RGB_LED_RESULT_OK);
  App_RgbLed_Run(124U);
  CHECK(check_state(1U, 2U, 3U, 100U, APP_RGB_LED_MODE_MEDIUM_BLINK, 1U));
  App_RgbLed_Run(125U);
  CHECK(check_state(1U, 2U, 3U, 100U, APP_RGB_LED_MODE_MEDIUM_BLINK, 0U));

  App_RgbLed_Init();
  CHECK(App_RgbLed_Set(1U, 2U, 3U, 100U, APP_RGB_LED_MODE_FAST_BLINK)
        == APP_RGB_LED_RESULT_OK);
  App_RgbLed_Run(62U);
  CHECK(check_state(1U, 2U, 3U, 100U, APP_RGB_LED_MODE_FAST_BLINK, 1U));
  App_RgbLed_Run(63U);
  CHECK(check_state(1U, 2U, 3U, 100U, APP_RGB_LED_MODE_FAST_BLINK, 0U));

  App_RgbLed_Init();
  CHECK(App_RgbLed_Set(10U, 20U, 30U, 40U, APP_RGB_LED_MODE_MEDIUM_BLINK)
        == APP_RGB_LED_RESULT_OK);
  App_RgbLed_GetState(&before);
  clear_writes();
  CHECK(App_RgbLed_Set(1U, 2U, 3U, 101U, APP_RGB_LED_MODE_STEADY)
        == APP_RGB_LED_RESULT_INVALID_BRIGHTNESS);
  App_RgbLed_GetState(&after);
  CHECK(memcmp(&before, &after, sizeof(before)) == 0);
  CHECK(write_count == 0U);
  CHECK(App_RgbLed_Set(1U, 2U, 3U, 40U, (App_RgbLedMode)5U)
        == APP_RGB_LED_RESULT_INVALID_MODE);
  App_RgbLed_GetState(&after);
  CHECK(memcmp(&before, &after, sizeof(before)) == 0);
  CHECK(write_count == 0U);

  App_RgbLed_Init();
  App_RgbLed_Run(UINT32_MAX - 100U);
  CHECK(App_RgbLed_Set(1U, 2U, 3U, 100U, APP_RGB_LED_MODE_SLOW_BLINK)
        == APP_RGB_LED_RESULT_OK);
  App_RgbLed_Run(148U);
  CHECK(check_state(1U, 2U, 3U, 100U, APP_RGB_LED_MODE_SLOW_BLINK, 1U));
  App_RgbLed_Run(149U);
  CHECK(check_state(1U, 2U, 3U, 100U, APP_RGB_LED_MODE_SLOW_BLINK, 0U));

  return 0;
}
