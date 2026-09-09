#include "app_ultrasonic_protocol.h"

#include <stddef.h>
#include <stdint.h>

/*
 * DYP 受控型超声波模块帧格式：
 *   0xFF + distance_high + distance_low + checksum
 * checksum 为前三字节低 8 bit 和。0xFFFE 表示同频干扰，0xFFFD 表示未测到物体。
 */

/**
  * @brief 初始化受控型超声波传感器串口帧解析器。
  * @param parser 指向解析器实例的指针。
  * @retval None
  */
void App_UltrasonicProtocol_InitParser(App_UltrasonicParser *parser)
{
  if (parser == NULL)
  {
    return;
  }

  parser->state = APP_ULTRASONIC_PARSE_WAIT_HEADER;
  parser->data_high = 0U;
  parser->data_low = 0U;
  parser->checksum = 0U;
  parser->distance_mm = 0U;
}

/**
  * @brief 输入 1 字节并解析 `FF + 高字节 + 低字节 + 校验` 距离帧。
  * @param parser 指向解析器实例的指针。
  * @param byte 新收到的串口字节。
  * @param distance_mm 距离输出，特殊值 0xFFFE/0xFFFD 也会原样输出。
  * @retval 解析结果，用于区分有效距离、同频干扰、无目标和校验错误。
  */
App_UltrasonicParseResult App_UltrasonicProtocol_ParseByte(
  App_UltrasonicParser *parser,
  uint8_t byte,
  uint16_t *distance_mm)
{
  uint8_t expected_checksum;

  if ((parser == NULL) || (distance_mm == NULL))
  {
    return APP_ULTRASONIC_PARSE_NONE;
  }

  switch (parser->state)
  {
    case APP_ULTRASONIC_PARSE_WAIT_HEADER:
      if (byte != APP_ULTRASONIC_FRAME_HEADER)
      {
        return APP_ULTRASONIC_PARSE_NONE;
      }

      parser->checksum = APP_ULTRASONIC_FRAME_HEADER;
      parser->state = APP_ULTRASONIC_PARSE_DATA_HIGH;
      break;

    case APP_ULTRASONIC_PARSE_DATA_HIGH:
      parser->data_high = byte;
      parser->state = APP_ULTRASONIC_PARSE_DATA_LOW;
      break;

    case APP_ULTRASONIC_PARSE_DATA_LOW:
      parser->data_low = byte;
      parser->state = APP_ULTRASONIC_PARSE_CHECKSUM;
      break;

    case APP_ULTRASONIC_PARSE_CHECKSUM:
      parser->distance_mm = (uint16_t)(((uint16_t)parser->data_high << 8U) | parser->data_low);
      expected_checksum = (uint8_t)(APP_ULTRASONIC_FRAME_HEADER + parser->data_high + parser->data_low);

      if (byte != expected_checksum)
      {
        App_UltrasonicProtocol_InitParser(parser);
        return APP_ULTRASONIC_PARSE_CHECKSUM_ERROR;
      }

      *distance_mm = parser->distance_mm;
      if (parser->distance_mm == APP_ULTRASONIC_INTERFERENCE_VALUE)
      {
        App_UltrasonicProtocol_InitParser(parser);
        return APP_ULTRASONIC_PARSE_INTERFERENCE;
      }
      if (parser->distance_mm == APP_ULTRASONIC_NO_TARGET_VALUE)
      {
        App_UltrasonicProtocol_InitParser(parser);
        return APP_ULTRASONIC_PARSE_NO_TARGET;
      }

      App_UltrasonicProtocol_InitParser(parser);
      return APP_ULTRASONIC_PARSE_READY;

    default:
      App_UltrasonicProtocol_InitParser(parser);
      break;
  }

  return APP_ULTRASONIC_PARSE_NONE;
}
