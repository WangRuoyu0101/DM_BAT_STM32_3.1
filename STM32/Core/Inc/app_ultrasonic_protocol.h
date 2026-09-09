#ifndef APP_ULTRASONIC_PROTOCOL_H
#define APP_ULTRASONIC_PROTOCOL_H

#include <stdint.h>

/* 受控型超声波传感器：STM32 向传感器发送任意字节即可触发一次测距。 */
#define APP_ULTRASONIC_TRIGGER_BYTE 0x55U

/* 传感器响应帧：0xFF + distance_high + distance_low + checksum。 */
#define APP_ULTRASONIC_FRAME_HEADER 0xFFU
#define APP_ULTRASONIC_FRAME_SIZE 4U

/* 传感器定义的特殊距离值。 */
#define APP_ULTRASONIC_INTERFERENCE_VALUE 0xFFFEU
#define APP_ULTRASONIC_NO_TARGET_VALUE 0xFFFDU

typedef enum
{
  APP_ULTRASONIC_PARSE_NONE = 0,
  APP_ULTRASONIC_PARSE_READY,
  APP_ULTRASONIC_PARSE_INTERFERENCE,
  APP_ULTRASONIC_PARSE_NO_TARGET,
  APP_ULTRASONIC_PARSE_CHECKSUM_ERROR
} App_UltrasonicParseResult;

typedef enum
{
  APP_ULTRASONIC_PARSE_WAIT_HEADER = 0,
  APP_ULTRASONIC_PARSE_DATA_HIGH,
  APP_ULTRASONIC_PARSE_DATA_LOW,
  APP_ULTRASONIC_PARSE_CHECKSUM
} App_UltrasonicParseState;

typedef struct
{
  App_UltrasonicParseState state;
  uint8_t data_high;
  uint8_t data_low;
  uint8_t checksum;
  uint16_t distance_mm;
} App_UltrasonicParser;

void App_UltrasonicProtocol_InitParser(App_UltrasonicParser *parser);

/* 输入单字节串口流，解析出有效距离或特殊状态。 */
App_UltrasonicParseResult App_UltrasonicProtocol_ParseByte(
  App_UltrasonicParser *parser,
  uint8_t byte,
  uint16_t *distance_mm);

#endif /* APP_ULTRASONIC_PROTOCOL_H */
