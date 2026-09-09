#ifndef BOOTLOADER_FLASH_H
#define BOOTLOADER_FLASH_H

#include "bootloader_config.h"
#include "stm32f4xx_hal.h"

#include <stddef.h>
#include <stdint.h>

typedef struct
{
  uint8_t active;
  uint8_t erased;
  uint32_t image_size;
  uint32_t image_crc32;
  uint32_t next_offset;
} Bootloader_FlashSession;

uint8_t Bootloader_FlashIsAppRange(uint32_t address, uint32_t length);
void Bootloader_FlashResetSession(Bootloader_FlashSession *session);
uint8_t Bootloader_FlashStartSession(
  Bootloader_FlashSession *session,
  uint32_t image_size,
  uint32_t image_crc32);
uint8_t Bootloader_FlashEraseApplication(Bootloader_FlashSession *session);
uint8_t Bootloader_FlashWrite(
  Bootloader_FlashSession *session,
  uint32_t offset,
  const uint8_t *data,
  uint32_t length);
uint8_t Bootloader_FlashVerify(const Bootloader_FlashSession *session);
uint8_t Bootloader_FlashInvalidateMetadata(void);
uint8_t Bootloader_FlashCommitMetadata(uint32_t image_size, uint32_t image_crc32);
uint8_t Bootloader_FlashIsApplicationValid(void);

#endif /* BOOTLOADER_FLASH_H */
