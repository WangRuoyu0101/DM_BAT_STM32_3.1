#ifndef BOOTLOADER_PROTOCOL_H
#define BOOTLOADER_PROTOCOL_H

#include "bootloader_config.h"

#include <stddef.h>
#include <stdint.h>

typedef struct
{
  uint8_t frame_id;
  uint8_t length;
  uint8_t data[BOOTLOADER_MAX_PAYLOAD_SIZE];
} Bootloader_Frame;

typedef enum
{
  BOOTLOADER_PARSE_WAIT_HEADER0 = 0,
  BOOTLOADER_PARSE_WAIT_HEADER1,
  BOOTLOADER_PARSE_FRAME_ID,
  BOOTLOADER_PARSE_LENGTH,
  BOOTLOADER_PARSE_DATA,
  BOOTLOADER_PARSE_CHECKSUM
} Bootloader_ParseState;

typedef enum
{
  BOOTLOADER_PARSE_NONE = 0,
  BOOTLOADER_PARSE_FRAME_READY,
  BOOTLOADER_PARSE_CHECKSUM_ERROR,
  BOOTLOADER_PARSE_LENGTH_ERROR
} Bootloader_ParseResult;

typedef struct
{
  Bootloader_ParseState state;
  uint8_t checksum;
  uint8_t data_index;
  Bootloader_Frame frame;
} Bootloader_Parser;

void Bootloader_ProtocolInitParser(Bootloader_Parser *parser);
uint8_t Bootloader_ProtocolChecksum(uint8_t frame_id, const uint8_t *data, uint8_t length);
size_t Bootloader_ProtocolEncode(
  uint8_t frame_id,
  const uint8_t *data,
  uint8_t length,
  uint8_t *output,
  size_t output_size);
Bootloader_ParseResult Bootloader_ProtocolParseByte(
  Bootloader_Parser *parser,
  uint8_t byte,
  Bootloader_Frame *frame);
uint32_t Bootloader_ReadLe32(const uint8_t *data);
void Bootloader_WriteLe32(uint8_t *data, uint32_t value);

#endif /* BOOTLOADER_PROTOCOL_H */
