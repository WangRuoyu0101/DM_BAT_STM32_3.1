#ifndef APP_CS1237_H
#define APP_CS1237_H

#include "main.h"

#include <stdint.h>

typedef enum
{
  APP_CS1237_CHANNEL_DIFFERENTIAL = 0,
  APP_CS1237_CHANNEL_RESERVED = 1,
  APP_CS1237_CHANNEL_TEMPERATURE = 2,
  APP_CS1237_CHANNEL_INTERNAL_SHORT = 3
} App_CS1237_Channel;

typedef enum
{
  APP_CS1237_RESULT_OK = 0,
  APP_CS1237_RESULT_INVALID_CHANNEL = 1,
  APP_CS1237_RESULT_TIMEOUT = 2,
  APP_CS1237_RESULT_VERIFY_FAILED = 3
} App_CS1237_Result;

typedef struct
{
  int32_t raw_adc;
  App_CS1237_Channel channel;
  uint8_t valid;
  uint8_t error;
} App_CS1237_Snapshot;

App_CS1237_Result App_CS1237_Init(void);
void App_CS1237_Run(void);
App_CS1237_Result App_CS1237_SetChannel(App_CS1237_Channel channel);
void App_CS1237_GetSnapshot(App_CS1237_Snapshot *snapshot);

#endif /* APP_CS1237_H */
