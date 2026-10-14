#ifndef APP_ULTRASONIC_MANAGER_H
#define APP_ULTRASONIC_MANAGER_H

#include "main.h"

#include <stdint.h>

#define APP_ULTRASONIC_SENSOR_COUNT 3U

typedef enum
{
  APP_ULTRASONIC_SENSOR_FRONT = 0,
  APP_ULTRASONIC_SENSOR_LEFT,
  APP_ULTRASONIC_SENSOR_RIGHT
} App_UltrasonicSensorId;

/* 三路超声波状态位：bit0 前、bit1 左、bit2 右。 */
#define APP_ULTRASONIC_VALID_FRONT 0x01U
#define APP_ULTRASONIC_VALID_LEFT 0x02U
#define APP_ULTRASONIC_VALID_RIGHT 0x04U

/* error_bitmap 每路占 2 bit：00 无错误，01 超时/校验错误，10 同频干扰，11 未测到物体。 */
#define APP_ULTRASONIC_ERROR_NONE 0x00U
#define APP_ULTRASONIC_ERROR_TIMEOUT 0x01U
#define APP_ULTRASONIC_ERROR_INTERFERENCE 0x02U
#define APP_ULTRASONIC_ERROR_NO_TARGET 0x03U

typedef struct
{
  uint16_t front_mm;
  uint16_t left_mm;
  uint16_t right_mm;
  uint8_t valid_bitmap;
  uint8_t error_bitmap;
} App_UltrasonicSnapshot;

/* 初始化前/左/右三路受控型超声波 UART，并启动单字节中断接收。 */
HAL_StatusTypeDef App_UltrasonicManager_Init(
  UART_HandleTypeDef *front_uart,
  UART_HandleTypeDef *left_uart,
  UART_HandleTypeDef *right_uart);

/* 在主循环中周期触发传感器、处理响应超时，并维护距离快照。 */
void App_UltrasonicManager_Run(uint32_t current_tick);

/* HAL UART 接收完成回调入口，按 UART 实例分发给对应传感器解析器。 */
void App_UltrasonicManager_HandleRxCplt(UART_HandleTypeDef *huart);

/* 获取最近一次三路距离快照，供 USB CDC 从机响应 Jetson 查询。 */
void App_UltrasonicManager_GetSnapshot(App_UltrasonicSnapshot *snapshot);

#endif /* APP_ULTRASONIC_MANAGER_H */
