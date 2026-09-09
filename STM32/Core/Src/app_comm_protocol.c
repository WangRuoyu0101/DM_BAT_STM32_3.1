#include "app_comm_protocol.h"

#include <stddef.h>
#include <stdint.h>
#include <string.h>

/*
 * 协议解析器采用状态机逐字节同步帧头，适合 UART 中断接收。
 * 解析成功后输出完整 App_CommFrame；CRC 或长度错误会复位状态机并返回错误码。
 */

/**
  * @brief 初始化通信协议解析器状态。
  * @param parser 指向解析器实例的指针。
  * @retval None
  */
void App_CommProtocol_InitParser(App_CommParser *parser)
{
  if (parser == NULL)
  {
    return;
  }

  parser->state = APP_COMM_PARSE_WAIT_HEADER0;
  parser->checksum = 0U;
  parser->data_index = 0U;
  parser->frame.frame_id = 0U;
  parser->frame.length = 0U;
  memset(parser->frame.data, 0, sizeof(parser->frame.data));
}

/**
  * @brief 将 1 字节输入到 CRC8 计算器。
  * @param crc 当前 CRC8 值。
  * @param byte 新输入字节。
  * @retval 更新后的 CRC8 值。
  */
static uint8_t App_CommProtocol_Crc8Byte(uint8_t crc, uint8_t byte)
{
  uint8_t bit;

  crc ^= byte;
  for (bit = 0U; bit < 8U; bit++)
  {
    if ((crc & 0x80U) != 0U)
    {
      crc = (uint8_t)((crc << 1U) ^ APP_COMM_CRC8_POLY);
    }
    else
    {
      crc = (uint8_t)(crc << 1U);
    }
  }

  return crc;
}

/**
  * @brief 计算通信帧 CRC8 校验值。
  * @param frame_id 帧ID。
  * @param data 数据区指针，长度为 0 时可为 NULL。
  * @param length 数据区长度。
  * @retval CRC8 校验值，计算范围为帧ID、数据长度和数据区。
  */
uint8_t App_CommProtocol_Checksum(uint8_t frame_id, const uint8_t *data, uint8_t length)
{
  uint8_t checksum = 0U;
  uint8_t index;

  checksum = App_CommProtocol_Crc8Byte(checksum, frame_id);
  checksum = App_CommProtocol_Crc8Byte(checksum, length);

  for (index = 0U; index < length; index++)
  {
    if (data != NULL)
    {
      checksum = App_CommProtocol_Crc8Byte(checksum, data[index]);
    }
  }

  return checksum;
}

/**
  * @brief 将帧ID和数据区打包为完整二进制通信帧。
  * @param frame_id 帧ID。
  * @param data 数据区指针，长度为 0 时可为 NULL。
  * @param length 数据区长度。
  * @param output 输出缓冲区。
  * @param output_size 输出缓冲区大小。
  * @retval 实际帧长度；返回 0 表示参数非法或缓冲区不足。
  */
size_t App_CommProtocol_Encode(
  uint8_t frame_id,
  const uint8_t *data,
  uint8_t length,
  uint8_t *output,
  size_t output_size)
{
  uint8_t index;
  size_t frame_size = (size_t)length + APP_COMM_FRAME_OVERHEAD;

  if ((output == NULL) || (length > APP_COMM_MAX_PAYLOAD_SIZE) || (output_size < frame_size))
  {
    return 0U;
  }

  output[0] = APP_COMM_FRAME_HEADER0;
  output[1] = APP_COMM_FRAME_HEADER1;
  output[2] = frame_id;
  output[3] = length;

  for (index = 0U; index < length; index++)
  {
    output[4U + index] = (data != NULL) ? data[index] : 0U;
  }

  output[4U + length] = App_CommProtocol_Checksum(frame_id, data, length);

  return frame_size;
}

/**
  * @brief 向协议解析器输入 1 字节并尝试解析完整帧。
  * @param parser 指向解析器实例的指针。
  * @param byte 新收到的字节。
  * @param frame 完整帧输出缓冲。
  * @retval 解析结果，用于判断是否收到完整帧或发生校验/长度错误。
  */
App_CommParseResult App_CommProtocol_ParseByte(
  App_CommParser *parser,
  uint8_t byte,
  App_CommFrame *frame)
{
  if ((parser == NULL) || (frame == NULL))
  {
    return APP_COMM_PARSE_NONE;
  }

  switch (parser->state)
  {
    case APP_COMM_PARSE_WAIT_HEADER0:
      if (byte == APP_COMM_FRAME_HEADER0)
      {
        parser->state = APP_COMM_PARSE_WAIT_HEADER1;
      }
      break;

    case APP_COMM_PARSE_WAIT_HEADER1:
      if (byte == APP_COMM_FRAME_HEADER1)
      {
        parser->state = APP_COMM_PARSE_FRAME_ID;
      }
      else if (byte != APP_COMM_FRAME_HEADER0)
      {
        parser->state = APP_COMM_PARSE_WAIT_HEADER0;
      }
      break;

    case APP_COMM_PARSE_FRAME_ID:
      parser->frame.frame_id = byte;
      parser->checksum = App_CommProtocol_Crc8Byte(0U, byte);
      parser->data_index = 0U;
      parser->state = APP_COMM_PARSE_LENGTH;
      break;

    case APP_COMM_PARSE_LENGTH:
      if (byte > APP_COMM_MAX_PAYLOAD_SIZE)
      {
        App_CommProtocol_InitParser(parser);
        return APP_COMM_PARSE_LENGTH_ERROR;
      }

      parser->frame.length = byte;
      parser->checksum = App_CommProtocol_Crc8Byte(parser->checksum, byte);
      parser->state = (byte == 0U) ? APP_COMM_PARSE_CHECKSUM : APP_COMM_PARSE_DATA;
      break;

    case APP_COMM_PARSE_DATA:
      parser->frame.data[parser->data_index] = byte;
      parser->checksum = App_CommProtocol_Crc8Byte(parser->checksum, byte);
      parser->data_index++;
      if (parser->data_index >= parser->frame.length)
      {
        parser->state = APP_COMM_PARSE_CHECKSUM;
      }
      break;

    case APP_COMM_PARSE_CHECKSUM:
      if (byte == parser->checksum)
      {
        *frame = parser->frame;
        App_CommProtocol_InitParser(parser);
        return APP_COMM_PARSE_FRAME_READY;
      }

      App_CommProtocol_InitParser(parser);
      return APP_COMM_PARSE_CHECKSUM_ERROR;

    default:
      App_CommProtocol_InitParser(parser);
      break;
  }

  return APP_COMM_PARSE_NONE;
}

/**
  * @brief 解析状态查询帧的数据区。
  * @param frame 已完成校验的通信帧。
  * @param query 状态查询输出缓冲。
  * @retval 解析结果，APP_COMM_CONTROL_RESULT_OK 表示解析成功。
  */
uint8_t App_CommProtocol_DecodeStatusQuery(
  const App_CommFrame *frame,
  App_CommStatusQuery *query)
{
  if ((frame == NULL) || (query == NULL))
  {
    return APP_COMM_CONTROL_RESULT_LENGTH_ERROR;
  }

  if (frame->frame_id != APP_COMM_FRAME_ID_STATUS_QUERY)
  {
    return APP_COMM_CONTROL_RESULT_LENGTH_ERROR;
  }

  if (frame->length != 1U)
  {
    query->seq = (frame->length > 0U) ? frame->data[0] : 0U;
    return APP_COMM_CONTROL_RESULT_LENGTH_ERROR;
  }

  query->seq = frame->data[0];

  return APP_COMM_CONTROL_RESULT_OK;
}

/**
  * @brief 解析 GPIO 控制请求帧的数据区。
  * @param frame 已完成校验的通信帧。
  * @param control GPIO 控制命令输出缓冲。
  * @retval 控制帧解析结果，APP_COMM_CONTROL_RESULT_OK 表示解析成功。
  */
uint8_t App_CommProtocol_DecodeGpioControlRequest(
  const App_CommFrame *frame,
  App_CommGpioControl *control)
{
  if ((frame == NULL) || (control == NULL))
  {
    return APP_COMM_CONTROL_RESULT_LENGTH_ERROR;
  }

  if (frame->frame_id != APP_COMM_FRAME_ID_GPIO_CONTROL_REQUEST)
  {
    return APP_COMM_CONTROL_RESULT_LENGTH_ERROR;
  }

  if (frame->length != 3U)
  {
    control->seq = (frame->length > 0U) ? frame->data[0] : 0U;
    control->channel_id = (frame->length > 1U) ? frame->data[1] : 0U;
    control->level = 0U;
    return APP_COMM_CONTROL_RESULT_LENGTH_ERROR;
  }

  control->seq = frame->data[0];
  control->channel_id = frame->data[1];
  control->level = frame->data[2];

  return APP_COMM_CONTROL_RESULT_OK;
}

/**
  * @brief 解析 GPIO 状态查询帧的数据区。
  * @param frame 已完成校验的通信帧。
  * @param query GPIO 状态查询输出缓冲。
  * @retval 解析结果，APP_COMM_CONTROL_RESULT_OK 表示解析成功。
  */
uint8_t App_CommProtocol_DecodeGpioStatusQuery(
  const App_CommFrame *frame,
  App_CommGpioStatusQuery *query)
{
  if ((frame == NULL) || (query == NULL))
  {
    return APP_COMM_CONTROL_RESULT_LENGTH_ERROR;
  }

  if (frame->frame_id != APP_COMM_FRAME_ID_GPIO_STATUS_QUERY)
  {
    return APP_COMM_CONTROL_RESULT_LENGTH_ERROR;
  }

  if (frame->length != 1U)
  {
    query->seq = (frame->length > 0U) ? frame->data[0] : 0U;
    return APP_COMM_CONTROL_RESULT_LENGTH_ERROR;
  }

  query->seq = frame->data[0];

  return APP_COMM_CONTROL_RESULT_OK;
}

/**
  * @brief 解析超声波状态查询帧的数据区。
  * @param frame 已完成校验的通信帧。
  * @param query 超声波查询输出缓冲。
  * @retval 解析结果，APP_COMM_CONTROL_RESULT_OK 表示解析成功。
  */
uint8_t App_CommProtocol_DecodeUltrasonicQuery(
  const App_CommFrame *frame,
  App_CommUltrasonicQuery *query)
{
  if ((frame == NULL) || (query == NULL))
  {
    return APP_COMM_CONTROL_RESULT_LENGTH_ERROR;
  }

  if (frame->frame_id != APP_COMM_FRAME_ID_ULTRASONIC_QUERY)
  {
    return APP_COMM_CONTROL_RESULT_LENGTH_ERROR;
  }

  if (frame->length != 1U)
  {
    query->seq = (frame->length > 0U) ? frame->data[0] : 0U;
    return APP_COMM_CONTROL_RESULT_LENGTH_ERROR;
  }

  query->seq = frame->data[0];

  return APP_COMM_CONTROL_RESULT_OK;
}

uint8_t App_CommProtocol_DecodeCS1237Query(
  const App_CommFrame *frame,
  App_CommCS1237Query *query)
{
  if ((frame == NULL) || (query == NULL))
  {
    return APP_COMM_CONTROL_RESULT_LENGTH_ERROR;
  }
  query->seq = (frame->length > 0U) ? frame->data[0] : 0U;
  if ((frame->frame_id != APP_COMM_FRAME_ID_CS1237_QUERY) || (frame->length != 1U))
  {
    return APP_COMM_CONTROL_RESULT_LENGTH_ERROR;
  }
  return APP_COMM_CONTROL_RESULT_OK;
}

uint8_t App_CommProtocol_DecodeCS1237ChannelRequest(
  const App_CommFrame *frame,
  App_CommCS1237ChannelRequest *request)
{
  if ((frame == NULL) || (request == NULL))
  {
    return APP_COMM_CONTROL_RESULT_LENGTH_ERROR;
  }
  request->seq = (frame->length > 0U) ? frame->data[0] : 0U;
  request->channel = (frame->length > 1U) ? frame->data[1] : 0U;
  if ((frame->frame_id != APP_COMM_FRAME_ID_CS1237_CHANNEL_REQUEST) || (frame->length != 2U))
  {
    return APP_COMM_CONTROL_RESULT_LENGTH_ERROR;
  }
  return APP_COMM_CONTROL_RESULT_OK;
}

uint8_t App_CommProtocol_DecodeRtkWriteRequest(
  const App_CommFrame *frame,
  App_CommRtkWriteRequest *request)
{
  uint8_t index;

  if ((frame == NULL) || (request == NULL))
  {
    return APP_COMM_CONTROL_RESULT_LENGTH_ERROR;
  }
  request->seq = (frame->length > 0U) ? frame->data[0] : 0U;
  request->length = 0U;
  if ((frame->frame_id != APP_COMM_FRAME_ID_RTK_WRITE_REQUEST) ||
      (frame->length < 2U) ||
      (frame->length > APP_COMM_MAX_PAYLOAD_SIZE))
  {
    return APP_COMM_CONTROL_RESULT_LENGTH_ERROR;
  }
  request->length = (uint8_t)(frame->length - 1U);
  for (index = 0U; index < request->length; index++)
  {
    request->data[index] = frame->data[index + 1U];
  }
  return APP_COMM_CONTROL_RESULT_OK;
}

uint8_t App_CommProtocol_DecodeRtkReadRequest(
  const App_CommFrame *frame,
  App_CommRtkReadRequest *request)
{
  if ((frame == NULL) || (request == NULL))
  {
    return APP_COMM_CONTROL_RESULT_LENGTH_ERROR;
  }
  request->seq = (frame->length > 0U) ? frame->data[0] : 0U;
  if ((frame->frame_id != APP_COMM_FRAME_ID_RTK_READ_REQUEST) || (frame->length != 1U))
  {
    return APP_COMM_CONTROL_RESULT_LENGTH_ERROR;
  }
  return APP_COMM_CONTROL_RESULT_OK;
}

uint8_t App_CommProtocol_DecodeFanControlRequest(
  const App_CommFrame *frame,
  App_CommFanControl *control)
{
  if ((frame == NULL) || (control == NULL))
  {
    return APP_COMM_CONTROL_RESULT_LENGTH_ERROR;
  }
  control->seq = (frame->length > 0U) ? frame->data[0] : 0U;
  control->level = (frame->length > 1U) ? frame->data[1] : 0U;
  if ((frame->frame_id != APP_COMM_FRAME_ID_FAN_CONTROL_REQUEST) || (frame->length != 2U))
  {
    return APP_COMM_CONTROL_RESULT_LENGTH_ERROR;
  }
  return APP_COMM_CONTROL_RESULT_OK;
}

uint8_t App_CommProtocol_DecodeBoardIOQuery(
  const App_CommFrame *frame,
  App_CommBoardIOQuery *query)
{
  if ((frame == NULL) || (query == NULL))
  {
    return APP_COMM_CONTROL_RESULT_LENGTH_ERROR;
  }
  query->seq = (frame->length > 0U) ? frame->data[0] : 0U;
  if ((frame->frame_id != APP_COMM_FRAME_ID_BOARD_IO_QUERY) || (frame->length != 1U))
  {
    return APP_COMM_CONTROL_RESULT_LENGTH_ERROR;
  }
  return APP_COMM_CONTROL_RESULT_OK;
}

uint8_t App_CommProtocol_DecodeRgbSetRequest(
  const App_CommFrame *frame,
  App_CommRgbSet *request)
{
  if ((frame == NULL) || (request == NULL))
  {
    return APP_COMM_CONTROL_RESULT_LENGTH_ERROR;
  }

  request->seq = (frame->length > 0U) ? frame->data[0] : 0U;
  if ((frame->frame_id != APP_COMM_FRAME_ID_RGB_SET_REQUEST) || (frame->length != 6U))
  {
    return APP_COMM_CONTROL_RESULT_LENGTH_ERROR;
  }

  request->red = frame->data[1];
  request->green = frame->data[2];
  request->blue = frame->data[3];
  request->brightness = frame->data[4];
  request->mode = frame->data[5];
  return APP_COMM_CONTROL_RESULT_OK;
}

uint8_t App_CommProtocol_DecodeRgbQuery(
  const App_CommFrame *frame,
  App_CommRgbQuery *query)
{
  if ((frame == NULL) || (query == NULL))
  {
    return APP_COMM_CONTROL_RESULT_LENGTH_ERROR;
  }

  query->seq = (frame->length > 0U) ? frame->data[0] : 0U;
  if ((frame->frame_id != APP_COMM_FRAME_ID_RGB_QUERY) || (frame->length != 1U))
  {
    return APP_COMM_CONTROL_RESULT_LENGTH_ERROR;
  }

  return APP_COMM_CONTROL_RESULT_OK;
}
