#include "bootloader_protocol.h"

#include <stddef.h>
#include <stdint.h>
#include <string.h>

void Bootloader_ProtocolInitParser(Bootloader_Parser *parser)
{
  if (parser == NULL)
  {
    return;
  }

  parser->state = BOOTLOADER_PARSE_WAIT_HEADER0;
  parser->checksum = 0U;
  parser->data_index = 0U;
  parser->frame.frame_id = 0U;
  parser->frame.length = 0U;
  memset(parser->frame.data, 0, sizeof(parser->frame.data));
}

static uint8_t Bootloader_Crc8Byte(uint8_t crc, uint8_t byte)
{
  uint8_t bit;

  crc ^= byte;
  for (bit = 0U; bit < 8U; bit++)
  {
    if ((crc & 0x80U) != 0U)
    {
      crc = (uint8_t)((crc << 1U) ^ BOOTLOADER_CRC8_POLY);
    }
    else
    {
      crc = (uint8_t)(crc << 1U);
    }
  }

  return crc;
}

uint8_t Bootloader_ProtocolChecksum(uint8_t frame_id, const uint8_t *data, uint8_t length)
{
  uint8_t checksum = 0U;
  uint8_t index;

  checksum = Bootloader_Crc8Byte(checksum, frame_id);
  checksum = Bootloader_Crc8Byte(checksum, length);

  for (index = 0U; index < length; index++)
  {
    if (data != NULL)
    {
      checksum = Bootloader_Crc8Byte(checksum, data[index]);
    }
  }

  return checksum;
}

size_t Bootloader_ProtocolEncode(
  uint8_t frame_id,
  const uint8_t *data,
  uint8_t length,
  uint8_t *output,
  size_t output_size)
{
  uint8_t index;
  size_t frame_size = (size_t)length + BOOTLOADER_FRAME_OVERHEAD;

  if ((output == NULL) || (length > BOOTLOADER_MAX_PAYLOAD_SIZE) || (output_size < frame_size))
  {
    return 0U;
  }

  output[0] = BOOTLOADER_FRAME_HEADER0;
  output[1] = BOOTLOADER_FRAME_HEADER1;
  output[2] = frame_id;
  output[3] = length;

  for (index = 0U; index < length; index++)
  {
    output[4U + index] = (data != NULL) ? data[index] : 0U;
  }

  output[4U + length] = Bootloader_ProtocolChecksum(frame_id, data, length);

  return frame_size;
}

Bootloader_ParseResult Bootloader_ProtocolParseByte(
  Bootloader_Parser *parser,
  uint8_t byte,
  Bootloader_Frame *frame)
{
  if ((parser == NULL) || (frame == NULL))
  {
    return BOOTLOADER_PARSE_NONE;
  }

  switch (parser->state)
  {
    case BOOTLOADER_PARSE_WAIT_HEADER0:
      if (byte == BOOTLOADER_FRAME_HEADER0)
      {
        parser->state = BOOTLOADER_PARSE_WAIT_HEADER1;
      }
      break;

    case BOOTLOADER_PARSE_WAIT_HEADER1:
      if (byte == BOOTLOADER_FRAME_HEADER1)
      {
        parser->state = BOOTLOADER_PARSE_FRAME_ID;
      }
      else if (byte != BOOTLOADER_FRAME_HEADER0)
      {
        parser->state = BOOTLOADER_PARSE_WAIT_HEADER0;
      }
      break;

    case BOOTLOADER_PARSE_FRAME_ID:
      parser->frame.frame_id = byte;
      parser->checksum = Bootloader_Crc8Byte(0U, byte);
      parser->data_index = 0U;
      parser->state = BOOTLOADER_PARSE_LENGTH;
      break;

    case BOOTLOADER_PARSE_LENGTH:
      if (byte > BOOTLOADER_MAX_PAYLOAD_SIZE)
      {
        Bootloader_ProtocolInitParser(parser);
        return BOOTLOADER_PARSE_LENGTH_ERROR;
      }

      parser->frame.length = byte;
      parser->checksum = Bootloader_Crc8Byte(parser->checksum, byte);
      parser->state = (byte == 0U) ? BOOTLOADER_PARSE_CHECKSUM : BOOTLOADER_PARSE_DATA;
      break;

    case BOOTLOADER_PARSE_DATA:
      parser->frame.data[parser->data_index] = byte;
      parser->checksum = Bootloader_Crc8Byte(parser->checksum, byte);
      parser->data_index++;
      if (parser->data_index >= parser->frame.length)
      {
        parser->state = BOOTLOADER_PARSE_CHECKSUM;
      }
      break;

    case BOOTLOADER_PARSE_CHECKSUM:
      if (byte == parser->checksum)
      {
        *frame = parser->frame;
        Bootloader_ProtocolInitParser(parser);
        return BOOTLOADER_PARSE_FRAME_READY;
      }

      Bootloader_ProtocolInitParser(parser);
      return BOOTLOADER_PARSE_CHECKSUM_ERROR;

    default:
      Bootloader_ProtocolInitParser(parser);
      break;
  }

  return BOOTLOADER_PARSE_NONE;
}

uint32_t Bootloader_ReadLe32(const uint8_t *data)
{
  if (data == NULL)
  {
    return 0U;
  }

  return ((uint32_t)data[0]) |
         ((uint32_t)data[1] << 8U) |
         ((uint32_t)data[2] << 16U) |
         ((uint32_t)data[3] << 24U);
}

void Bootloader_WriteLe32(uint8_t *data, uint32_t value)
{
  if (data == NULL)
  {
    return;
  }

  data[0] = (uint8_t)(value & 0xFFU);
  data[1] = (uint8_t)((value >> 8U) & 0xFFU);
  data[2] = (uint8_t)((value >> 16U) & 0xFFU);
  data[3] = (uint8_t)((value >> 24U) & 0xFFU);
}
