#include "app_ultrasonic_manager.h"

#include "app_ultrasonic_protocol.h"

#include <stddef.h>
#include <stdint.h>

#define APP_ULTRASONIC_TRIGGER_PERIOD_MS 200U
#define APP_ULTRASONIC_TRIGGER_GAP_MS 20U
#define APP_ULTRASONIC_RESPONSE_TIMEOUT_MS 80U
#define APP_ULTRASONIC_WAKE_RESPONSE_EXTRA_MS 12U
#define APP_ULTRASONIC_SLEEP_TIMEOUT_MS 5000U
#define APP_ULTRASONIC_TX_TIMEOUT_MS 5U
#define APP_ULTRASONIC_TICK_MS 2U

/*
 * 三路超声波使用独立 UART：
 *   front -> USART2，left -> UART4，right -> USART3。
 * 为降低互相串扰，三路传感器按 20 ms slot 错峰触发，单路约 200 ms 周期刷新一次。
 */
typedef struct
{
  App_UltrasonicSensorId id;
  USART_TypeDef *instance;
  uint16_t slot_delay_ms;
  UART_HandleTypeDef *huart;
  App_UltrasonicParser parser;
  uint8_t rx_byte;
  uint8_t waiting_response;
  uint8_t valid;
  uint8_t error_code;
  uint16_t distance_mm;
  uint32_t last_trigger_tick;
  uint32_t trigger_due_tick;
} App_UltrasonicSensor;

static App_UltrasonicSensor s_sensors[APP_ULTRASONIC_SENSOR_COUNT] = {
  {APP_ULTRASONIC_SENSOR_FRONT, USART2, 0U, NULL, {0}, 0U, 0U, 0U, APP_ULTRASONIC_ERROR_TIMEOUT, 0U, 0U, 0U},
  {APP_ULTRASONIC_SENSOR_LEFT, UART4, APP_ULTRASONIC_TRIGGER_GAP_MS, NULL, {0}, 0U, 0U, 0U, APP_ULTRASONIC_ERROR_TIMEOUT, 0U, 0U, 0U},
  {APP_ULTRASONIC_SENSOR_RIGHT, USART3, (uint16_t)(APP_ULTRASONIC_TRIGGER_GAP_MS * 2U), NULL, {0}, 0U, 0U, 0U, APP_ULTRASONIC_ERROR_TIMEOUT, 0U, 0U, 0U},
};

/**
  * @brief 将毫秒转换为系统 2 ms 周期计数。
  * @param ms 毫秒数。
  * @retval 对应的 2 ms tick 数，向上取整。
  */
static uint32_t App_UltrasonicManager_MsToTicks(uint32_t ms)
{
  return (ms + (APP_ULTRASONIC_TICK_MS - 1U)) / APP_ULTRASONIC_TICK_MS;
}

/**
  * @brief 根据 UART 句柄查找对应的超声波传感器实例。
  * @param huart UART 句柄指针。
  * @retval 传感器实例指针；未找到返回 NULL。
  */
static App_UltrasonicSensor *App_UltrasonicManager_FindSensor(UART_HandleTypeDef *huart)
{
  size_t index;

  if (huart == NULL)
  {
    return NULL;
  }

  for (index = 0U; index < APP_ULTRASONIC_SENSOR_COUNT; index++)
  {
    if (s_sensors[index].huart == huart)
    {
      return &s_sensors[index];
    }
  }

  return NULL;
}

/**
  * @brief 计算传感器错误状态在 error_bitmap 中的偏移。
  * @param id 传感器编号。
  * @retval 该传感器 2 bit 错误字段的左移位数。
  */
static uint8_t App_UltrasonicManager_ErrorShift(App_UltrasonicSensorId id)
{
  return (uint8_t)((uint8_t)id * 2U);
}

/**
  * @brief 初始化三路受控型超声波传感器串口接收。
  * @param front_uart 前向传感器 UART2 句柄。
  * @param left_uart 左向传感器 UART4 句柄。
  * @param right_uart 右向传感器 UART3 句柄。
  * @retval HAL_OK 表示三路接收中断均启动成功。
  */
HAL_StatusTypeDef App_UltrasonicManager_Init(
  UART_HandleTypeDef *front_uart,
  UART_HandleTypeDef *left_uart,
  UART_HandleTypeDef *right_uart)
{
  size_t index;

  if ((front_uart == NULL) || (left_uart == NULL) || (right_uart == NULL) ||
      (front_uart->Instance != USART2) || (left_uart->Instance != UART4) || (right_uart->Instance != USART3))
  {
    return HAL_ERROR;
  }

  s_sensors[APP_ULTRASONIC_SENSOR_FRONT].huart = front_uart;
  s_sensors[APP_ULTRASONIC_SENSOR_LEFT].huart = left_uart;
  s_sensors[APP_ULTRASONIC_SENSOR_RIGHT].huart = right_uart;

  for (index = 0U; index < APP_ULTRASONIC_SENSOR_COUNT; index++)
  {
    App_UltrasonicSensor *sensor = &s_sensors[index];

    App_UltrasonicProtocol_InitParser(&sensor->parser);
    sensor->rx_byte = 0U;
    sensor->waiting_response = 0U;
    sensor->valid = 0U;
    sensor->error_code = APP_ULTRASONIC_ERROR_TIMEOUT;
    sensor->distance_mm = 0U;
    sensor->last_trigger_tick = 0U;
    sensor->trigger_due_tick = App_UltrasonicManager_MsToTicks(sensor->slot_delay_ms);

    if (HAL_UART_Receive_IT(sensor->huart, &sensor->rx_byte, 1U) != HAL_OK)
    {
      return HAL_ERROR;
    }
  }

  return HAL_OK;
}

/**
  * @brief 周期调度三路超声波传感器触发和响应超时判断。
  * @param current_tick 当前 2 ms 周期计数。
  * @retval None
  */
void App_UltrasonicManager_Run(uint32_t current_tick)
{
  size_t index;
  uint8_t trigger_byte = APP_ULTRASONIC_TRIGGER_BYTE;

  for (index = 0U; index < APP_ULTRASONIC_SENSOR_COUNT; index++)
  {
    App_UltrasonicSensor *sensor = &s_sensors[index];
    uint32_t timeout_ticks = App_UltrasonicManager_MsToTicks(APP_ULTRASONIC_RESPONSE_TIMEOUT_MS);

    if (sensor->huart == NULL)
    {
      continue;
    }

    if (((current_tick - sensor->last_trigger_tick) > App_UltrasonicManager_MsToTicks(APP_ULTRASONIC_SLEEP_TIMEOUT_MS)) &&
        (sensor->waiting_response == 0U))
    {
      /* 传感器长时间未触发后首次唤醒可能稍慢，首帧超时适当放宽。 */
      timeout_ticks += App_UltrasonicManager_MsToTicks(APP_ULTRASONIC_WAKE_RESPONSE_EXTRA_MS);
    }

    if ((sensor->waiting_response != 0U) && ((current_tick - sensor->last_trigger_tick) >= timeout_ticks))
    {
      /* 超时会清除 valid 位，并在 error_bitmap 中记录该路超时。 */
      sensor->waiting_response = 0U;
      sensor->valid = 0U;
      sensor->error_code = APP_ULTRASONIC_ERROR_TIMEOUT;
    }

    if ((sensor->waiting_response == 0U) &&
        (((sensor->last_trigger_tick == 0U) && (current_tick >= sensor->trigger_due_tick)) ||
         ((current_tick - sensor->last_trigger_tick) >= App_UltrasonicManager_MsToTicks(APP_ULTRASONIC_TRIGGER_PERIOD_MS))) &&
        (current_tick >= sensor->trigger_due_tick))
    {
      /* 发送触发字节后立即进入等待响应状态，下一次触发必须等本轮结束或超时。 */
      (void)HAL_UART_Transmit(sensor->huart, &trigger_byte, 1U, APP_ULTRASONIC_TX_TIMEOUT_MS);
      sensor->waiting_response = 1U;
      sensor->last_trigger_tick = current_tick;
      sensor->trigger_due_tick = current_tick + App_UltrasonicManager_MsToTicks(APP_ULTRASONIC_TRIGGER_PERIOD_MS);
    }
  }
}

/**
  * @brief UART 接收完成回调入口，按串口分发到对应超声波解析器。
  * @param huart 触发接收完成的 UART 句柄指针。
  * @retval None
  */
void App_UltrasonicManager_HandleRxCplt(UART_HandleTypeDef *huart)
{
  App_UltrasonicSensor *sensor = App_UltrasonicManager_FindSensor(huart);
  uint16_t distance_mm = 0U;

  if (sensor == NULL)
  {
    return;
  }

  switch (App_UltrasonicProtocol_ParseByte(&sensor->parser, sensor->rx_byte, &distance_mm))
  {
    case APP_ULTRASONIC_PARSE_READY:
      sensor->distance_mm = distance_mm;
      sensor->valid = 1U;
      sensor->error_code = APP_ULTRASONIC_ERROR_NONE;
      sensor->waiting_response = 0U;
      break;

    case APP_ULTRASONIC_PARSE_INTERFERENCE:
      sensor->distance_mm = distance_mm;
      sensor->valid = 0U;
      sensor->error_code = APP_ULTRASONIC_ERROR_INTERFERENCE;
      sensor->waiting_response = 0U;
      break;

    case APP_ULTRASONIC_PARSE_NO_TARGET:
      sensor->distance_mm = distance_mm;
      sensor->valid = 0U;
      sensor->error_code = APP_ULTRASONIC_ERROR_NO_TARGET;
      sensor->waiting_response = 0U;
      break;

    case APP_ULTRASONIC_PARSE_CHECKSUM_ERROR:
      sensor->valid = 0U;
      sensor->error_code = APP_ULTRASONIC_ERROR_TIMEOUT;
      sensor->waiting_response = 0U;
      break;

    default:
      break;
  }

  (void)HAL_UART_Receive_IT(sensor->huart, &sensor->rx_byte, 1U);
}

/**
  * @brief 获取三路超声波距离和状态快照。
  * @param snapshot 快照输出缓冲。
  * @retval None
  */
void App_UltrasonicManager_GetSnapshot(App_UltrasonicSnapshot *snapshot)
{
  size_t index;

  if (snapshot == NULL)
  {
    return;
  }

  snapshot->front_mm = s_sensors[APP_ULTRASONIC_SENSOR_FRONT].distance_mm;
  snapshot->left_mm = s_sensors[APP_ULTRASONIC_SENSOR_LEFT].distance_mm;
  snapshot->right_mm = s_sensors[APP_ULTRASONIC_SENSOR_RIGHT].distance_mm;
  snapshot->valid_bitmap = 0U;
  snapshot->error_bitmap = 0U;

  for (index = 0U; index < APP_ULTRASONIC_SENSOR_COUNT; index++)
  {
    /* valid_bitmap 每路 1 bit；error_bitmap 每路 2 bit，便于主机端同时判断距离可信度和错误原因。 */
    if (s_sensors[index].valid != 0U)
    {
      snapshot->valid_bitmap = (uint8_t)(snapshot->valid_bitmap | (1U << index));
    }

    snapshot->error_bitmap = (uint8_t)(
      snapshot->error_bitmap |
      ((s_sensors[index].error_code & 0x03U) << App_UltrasonicManager_ErrorShift(s_sensors[index].id)));
  }
}
