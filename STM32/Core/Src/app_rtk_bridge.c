#include "app_rtk_bridge.h"

#define APP_RTK_BRIDGE_RX_MASK (APP_RTK_BRIDGE_RX_CAPACITY - 1U)
#define APP_RTK_BRIDGE_TX_TIMEOUT_MS 10U

static UART_HandleTypeDef *s_uart = NULL;
static uint8_t s_rx_byte = 0U;
static uint8_t s_rx_buffer[APP_RTK_BRIDGE_RX_CAPACITY];
static volatile uint16_t s_rx_head = 0U;
static volatile uint16_t s_rx_tail = 0U;
static volatile uint8_t s_rx_overflow = 0U;
static volatile uint32_t s_overflow_bytes = 0U;
static volatile uint32_t s_uart_errors = 0U;
static volatile uint16_t s_rx_high_water = 0U;

static void App_RtkBridge_IncrementSaturated(volatile uint32_t *counter)
{
  if (*counter != UINT32_MAX)
  {
    (*counter)++;
  }
}

HAL_StatusTypeDef App_RtkBridge_Init(UART_HandleTypeDef *huart)
{
  if ((huart == NULL) || (huart->Instance != USART6))
  {
    return HAL_ERROR;
  }

  s_uart = huart;
  s_rx_byte = 0U;
  s_rx_head = 0U;
  s_rx_tail = 0U;
  s_rx_overflow = 0U;
  s_overflow_bytes = 0U;
  s_uart_errors = 0U;
  s_rx_high_water = 0U;
  return HAL_UART_Receive_IT(s_uart, &s_rx_byte, 1U);
}

HAL_StatusTypeDef App_RtkBridge_Write(const uint8_t *data, uint16_t length)
{
  if ((s_uart == NULL) || (data == NULL) || (length == 0U))
  {
    return HAL_ERROR;
  }
  return HAL_UART_Transmit(s_uart, (uint8_t *)data, length, APP_RTK_BRIDGE_TX_TIMEOUT_MS);
}

size_t App_RtkBridge_Read(uint8_t *data, size_t capacity, uint8_t *flags)
{
  size_t count = 0U;
  uint16_t head;
  uint32_t primask;

  if ((data == NULL) && (capacity > 0U))
  {
    return 0U;
  }

  primask = __get_PRIMASK();
  __disable_irq();
  if (flags != NULL)
  {
    *flags = (s_rx_overflow != 0U) ? APP_RTK_BRIDGE_FLAG_OVERFLOW : 0U;
  }
  s_rx_overflow = 0U;
  head = s_rx_head;
  __set_PRIMASK(primask);

  while ((s_rx_tail != head) && (count < capacity))
  {
    data[count] = s_rx_buffer[s_rx_tail & APP_RTK_BRIDGE_RX_MASK];
    s_rx_tail++;
    count++;
  }
  return count;
}

void App_RtkBridge_GetDiagnostics(App_RtkBridgeDiagnostics *diagnostics)
{
  uint32_t primask;

  if (diagnostics == NULL)
  {
    return;
  }
  primask = __get_PRIMASK();
  __disable_irq();
  diagnostics->overflow_bytes = s_overflow_bytes;
  diagnostics->uart_errors = s_uart_errors;
  diagnostics->rx_high_water = s_rx_high_water;
  __set_PRIMASK(primask);
}

void App_RtkBridge_HandleRxCplt(UART_HandleTypeDef *huart)
{
  uint16_t occupancy;

  if ((s_uart == NULL) || (huart == NULL) || (huart->Instance != USART6))
  {
    return;
  }

  if ((uint16_t)(s_rx_head - s_rx_tail) < APP_RTK_BRIDGE_RX_CAPACITY)
  {
    s_rx_buffer[s_rx_head & APP_RTK_BRIDGE_RX_MASK] = s_rx_byte;
    s_rx_head++;
    occupancy = (uint16_t)(s_rx_head - s_rx_tail);
    if (occupancy > s_rx_high_water)
    {
      s_rx_high_water = occupancy;
    }
  }
  else
  {
    s_rx_overflow = 1U;
    App_RtkBridge_IncrementSaturated(&s_overflow_bytes);
  }
  (void)HAL_UART_Receive_IT(s_uart, &s_rx_byte, 1U);
}

void App_RtkBridge_HandleError(UART_HandleTypeDef *huart)
{
  if ((s_uart != NULL) && (huart != NULL) && (huart->Instance == USART6))
  {
    App_RtkBridge_IncrementSaturated(&s_uart_errors);
    (void)HAL_UART_Receive_IT(s_uart, &s_rx_byte, 1U);
  }
}
