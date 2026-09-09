#ifndef APP_RTK_BRIDGE_H
#define APP_RTK_BRIDGE_H

#include "main.h"

#include <stddef.h>
#include <stdint.h>

#define APP_RTK_BRIDGE_RX_CAPACITY 1024U
#define APP_RTK_BRIDGE_FLAG_OVERFLOW 0x01U

typedef struct
{
  uint32_t overflow_bytes;
  uint32_t uart_errors;
  uint16_t rx_high_water;
} App_RtkBridgeDiagnostics;

HAL_StatusTypeDef App_RtkBridge_Init(UART_HandleTypeDef *huart);
HAL_StatusTypeDef App_RtkBridge_Write(const uint8_t *data, uint16_t length);
size_t App_RtkBridge_Read(uint8_t *data, size_t capacity, uint8_t *flags);
void App_RtkBridge_GetDiagnostics(App_RtkBridgeDiagnostics *diagnostics);
void App_RtkBridge_HandleRxCplt(UART_HandleTypeDef *huart);
void App_RtkBridge_HandleError(UART_HandleTypeDef *huart);

#endif /* APP_RTK_BRIDGE_H */
