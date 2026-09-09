#include "app_rgb_protocol.h"

#include "app_rgb_led.h"

#include <stddef.h>
#include <string.h>

static void App_RgbProtocol_Error(
  const App_CommFrame *request,
  App_CommFrame *response,
  uint8_t error_code)
{
  response->frame_id = APP_COMM_FRAME_ID_ERROR_RESPONSE;
  response->length = 3U;
  response->data[0] = (request->length > 0U) ? request->data[0] : 0U;
  response->data[1] = request->frame_id;
  response->data[2] = error_code;
}

void App_RgbProtocol_Process(const App_CommFrame *request, App_CommFrame *response)
{
  if ((request == NULL) || (response == NULL))
  {
    return;
  }

  memset(response, 0, sizeof(*response));
  if (request->frame_id == APP_COMM_FRAME_ID_RGB_SET_REQUEST)
  {
    App_CommRgbSet setting;
    uint8_t result = App_CommProtocol_DecodeRgbSetRequest(request, &setting);

    if (result != APP_COMM_CONTROL_RESULT_OK)
    {
      App_RgbProtocol_Error(request, response, APP_COMM_ERROR_CODE_LENGTH);
      return;
    }
    result = App_RgbLed_Set(
      setting.red,
      setting.green,
      setting.blue,
      setting.brightness,
      (App_RgbLedMode)setting.mode);
    response->frame_id = APP_COMM_FRAME_ID_RGB_SET_RESPONSE;
    response->length = 2U;
    response->data[0] = setting.seq;
    response->data[1] = result;
    return;
  }

  if (request->frame_id == APP_COMM_FRAME_ID_RGB_QUERY)
  {
    App_CommRgbQuery query;
    App_RgbLedState state;

    if (App_CommProtocol_DecodeRgbQuery(request, &query) != APP_COMM_CONTROL_RESULT_OK)
    {
      App_RgbProtocol_Error(request, response, APP_COMM_ERROR_CODE_LENGTH);
      return;
    }
    App_RgbLed_GetState(&state);
    response->frame_id = APP_COMM_FRAME_ID_RGB_STATUS;
    response->length = 7U;
    response->data[0] = query.seq;
    response->data[1] = state.red;
    response->data[2] = state.green;
    response->data[3] = state.blue;
    response->data[4] = state.brightness;
    response->data[5] = state.mode;
    response->data[6] = state.output_on;
    return;
  }

  App_RgbProtocol_Error(request, response, APP_COMM_ERROR_CODE_CMD);
}
