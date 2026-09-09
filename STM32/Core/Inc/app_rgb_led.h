#ifndef APP_RGB_LED_H
#define APP_RGB_LED_H

#include <stdint.h>

#define APP_RGB_LED_DEFAULT_RED 0U
#define APP_RGB_LED_DEFAULT_GREEN 255U
#define APP_RGB_LED_DEFAULT_BLUE 0U
#define APP_RGB_LED_DEFAULT_BRIGHTNESS 25U

#define APP_RGB_LED_RESULT_OK 0U
#define APP_RGB_LED_RESULT_INVALID_BRIGHTNESS 1U
#define APP_RGB_LED_RESULT_INVALID_MODE 2U

typedef enum {
  APP_RGB_LED_MODE_OFF = 0U,
  APP_RGB_LED_MODE_STEADY = 1U,
  APP_RGB_LED_MODE_SLOW_BLINK = 2U,
  APP_RGB_LED_MODE_MEDIUM_BLINK = 3U,
  APP_RGB_LED_MODE_FAST_BLINK = 4U
} App_RgbLedMode;

typedef struct {
  uint8_t red, green, blue, brightness, mode, output_on;
} App_RgbLedState;

void App_RgbLed_Init(void);
void App_RgbLed_Run(uint32_t current_tick);
uint8_t App_RgbLed_Set(uint8_t red, uint8_t green, uint8_t blue,
                       uint8_t brightness, App_RgbLedMode mode);
void App_RgbLed_GetState(App_RgbLedState *state);

#endif /* APP_RGB_LED_H */
