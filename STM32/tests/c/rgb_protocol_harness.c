#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "main.h"
#include "app_comm_protocol.h"
#include "app_rgb_led.h"
#include "app_rgb_protocol.h"

CoreDebug_Type mock_core_debug;
DWT_Type mock_dwt;
GPIO_TypeDef mock_gpio;
uint32_t SystemCoreClock = 80000000U;
static uint32_t cycle;

uint32_t mock_rgb_cycle_now(void) { return cycle++; }
void mock_rgb_write(uint32_t value) { (void)value; }
uint32_t mock_get_primask(void) { return 0U; }
void mock_disable_irq(void) {}
void mock_enable_irq(void) {}

#define CHECK(condition) do { \
  if (!(condition)) { \
    fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition); \
    return 1; \
  } \
} while (0)

static App_CommFrame request(uint8_t frame_id, const uint8_t *payload, uint8_t length)
{
  App_CommFrame frame = {0};
  frame.frame_id = frame_id;
  frame.length = length;
  if (payload != NULL)
  {
    memcpy(frame.data, payload, length);
  }
  return frame;
}

int main(void)
{
  App_CommFrame input;
  App_CommFrame output;
  App_RgbLedState state;
  const uint8_t set_payload[6] = {0x31U, 0x11U, 0x22U, 0x33U, 50U, 3U};
  const uint8_t query_payload[1] = {0x32U};

  App_RgbLed_Init();
  input = request(APP_COMM_FRAME_ID_RGB_SET_REQUEST, set_payload, sizeof(set_payload));
  App_RgbProtocol_Process(&input, &output);
  CHECK(output.frame_id == APP_COMM_FRAME_ID_RGB_SET_RESPONSE);
  CHECK(output.length == 2U);
  CHECK(output.data[0] == 0x31U && output.data[1] == APP_RGB_LED_RESULT_OK);
  App_RgbLed_GetState(&state);
  CHECK(state.red == 0x11U && state.green == 0x22U && state.blue == 0x33U);
  CHECK(state.brightness == 50U && state.mode == 3U && state.output_on == 1U);

  input.data[4] = 101U;
  App_RgbProtocol_Process(&input, &output);
  CHECK(output.frame_id == APP_COMM_FRAME_ID_RGB_SET_RESPONSE);
  CHECK(output.length == 2U);
  CHECK(output.data[0] == 0x31U);
  CHECK(output.data[1] == APP_RGB_LED_RESULT_INVALID_BRIGHTNESS);
  input.data[4] = 50U;
  input.data[5] = 5U;
  App_RgbProtocol_Process(&input, &output);
  CHECK(output.data[1] == APP_RGB_LED_RESULT_INVALID_MODE);

  input = request(APP_COMM_FRAME_ID_RGB_SET_REQUEST, set_payload, 5U);
  App_RgbProtocol_Process(&input, &output);
  CHECK(output.frame_id == APP_COMM_FRAME_ID_ERROR_RESPONSE);
  CHECK(output.length == 3U);
  CHECK(output.data[0] == 0x31U);
  CHECK(output.data[1] == APP_COMM_FRAME_ID_RGB_SET_REQUEST);
  CHECK(output.data[2] == APP_COMM_ERROR_CODE_LENGTH);

  input = request(APP_COMM_FRAME_ID_RGB_QUERY, query_payload, sizeof(query_payload));
  App_RgbProtocol_Process(&input, &output);
  CHECK(output.frame_id == APP_COMM_FRAME_ID_RGB_STATUS);
  CHECK(output.length == 7U);
  CHECK(output.data[0] == 0x32U);
  CHECK(output.data[1] == 0x11U && output.data[2] == 0x22U && output.data[3] == 0x33U);
  CHECK(output.data[4] == 50U && output.data[5] == 3U && output.data[6] == 1U);

  input = request(APP_COMM_FRAME_ID_RGB_QUERY, query_payload, 0U);
  App_RgbProtocol_Process(&input, &output);
  CHECK(output.frame_id == APP_COMM_FRAME_ID_ERROR_RESPONSE);
  CHECK(output.length == 3U);
  CHECK(output.data[0] == 0U);
  CHECK(output.data[1] == APP_COMM_FRAME_ID_RGB_QUERY);
  CHECK(output.data[2] == APP_COMM_ERROR_CODE_LENGTH);

  return 0;
}
