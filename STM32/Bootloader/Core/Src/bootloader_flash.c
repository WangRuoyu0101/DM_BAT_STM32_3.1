#include "bootloader_flash.h"

#include <stddef.h>
#include <stdint.h>

typedef struct
{
  uint32_t magic;
  uint32_t format_version;
  uint32_t image_size;
  uint32_t image_crc32;
  uint32_t record_crc32;
} Bootloader_AppMetadata;

static uint8_t Bootloader_FlashProgramBytes(uint32_t address, const uint8_t *data, uint32_t length);

static uint32_t Bootloader_FlashCrc32(const uint8_t *data, uint32_t length)
{
  uint32_t crc = 0xFFFFFFFFU;
  uint32_t index;
  uint8_t bit;

  for (index = 0U; index < length; index++)
  {
    crc ^= data[index];
    for (bit = 0U; bit < 8U; bit++)
    {
      crc = ((crc & 1U) != 0U) ? ((crc >> 1U) ^ 0xEDB88320U) : (crc >> 1U);
    }
  }

  return ~crc;
}

static uint8_t Bootloader_FlashVectorsAreValid(uint32_t image_size)
{
  uint32_t stack_pointer = *(volatile uint32_t *)APP_FLASH_BASE;
  uint32_t reset_handler = *(volatile uint32_t *)(APP_FLASH_BASE + 4U);
  uint32_t reset_address = reset_handler & ~1U;
  uint32_t image_end = APP_FLASH_BASE + image_size;

  if ((image_size < 8U) || (image_size > APP_FLASH_SIZE) ||
      (stack_pointer < APP_SRAM_BASE) || (stack_pointer > APP_SRAM_END) ||
      ((reset_handler & 1U) == 0U) ||
      (reset_address < APP_FLASH_BASE) || (reset_address >= image_end))
  {
    return 0U;
  }

  return 1U;
}

uint8_t Bootloader_FlashIsAppRange(uint32_t address, uint32_t length)
{
  uint32_t end_address;

  if (length == 0U)
  {
    return 0U;
  }

  end_address = address + length;
  if ((end_address < address) || (address < APP_FLASH_BASE) || (end_address > APP_FLASH_END))
  {
    return 0U;
  }

  return 1U;
}

void Bootloader_FlashResetSession(Bootloader_FlashSession *session)
{
  if (session == NULL)
  {
    return;
  }

  session->active = 0U;
  session->erased = 0U;
  session->image_size = 0U;
  session->image_crc32 = 0U;
  session->next_offset = 0U;
}

uint8_t Bootloader_FlashStartSession(
  Bootloader_FlashSession *session,
  uint32_t image_size,
  uint32_t image_crc32)
{
  if ((session == NULL) || (image_size == 0U) || (image_size > APP_FLASH_SIZE))
  {
    return BOOTLOADER_ERROR_SESSION;
  }

  session->active = 1U;
  session->erased = 0U;
  session->image_size = image_size;
  session->image_crc32 = image_crc32;
  session->next_offset = 0U;

  return BOOTLOADER_STATUS_OK;
}

uint8_t Bootloader_FlashInvalidateMetadata(void)
{
  const Bootloader_AppMetadata *metadata = (const Bootloader_AppMetadata *)APP_METADATA_BASE;
  static const uint32_t invalid_magic = 0U;

  if (metadata->magic != APP_METADATA_MAGIC)
  {
    return BOOTLOADER_STATUS_OK;
  }

  if (Bootloader_FlashProgramBytes(
        APP_METADATA_BASE,
        (const uint8_t *)&invalid_magic,
        (uint32_t)sizeof(invalid_magic)) != BOOTLOADER_STATUS_OK)
  {
    return BOOTLOADER_ERROR_FLASH;
  }

  return (metadata->magic == APP_METADATA_MAGIC) ? BOOTLOADER_ERROR_FLASH : BOOTLOADER_STATUS_OK;
}

uint8_t Bootloader_FlashEraseApplication(Bootloader_FlashSession *session)
{
  FLASH_EraseInitTypeDef erase = {0};
  uint32_t sector_error = 0U;

  if ((session == NULL) || (session->active == 0U) || (session->image_size == 0U))
  {
    return BOOTLOADER_ERROR_SESSION;
  }

  if (Bootloader_FlashInvalidateMetadata() != BOOTLOADER_STATUS_OK)
  {
    return BOOTLOADER_ERROR_FLASH;
  }

  erase.TypeErase = FLASH_TYPEERASE_SECTORS;
  erase.Banks = FLASH_BANK_1;
  erase.Sector = FLASH_SECTOR_2;
  erase.NbSectors = 5U;
  erase.VoltageRange = FLASH_VOLTAGE_RANGE_3;

  if (HAL_FLASH_Unlock() != HAL_OK)
  {
    return BOOTLOADER_ERROR_FLASH;
  }

  if (HAL_FLASHEx_Erase(&erase, &sector_error) != HAL_OK)
  {
    (void)HAL_FLASH_Lock();
    return BOOTLOADER_ERROR_FLASH;
  }

  (void)HAL_FLASH_Lock();
  session->erased = 1U;
  return BOOTLOADER_STATUS_OK;
}

static uint8_t Bootloader_FlashProgramBytes(uint32_t address, const uint8_t *data, uint32_t length)
{
  uint32_t index;

  if (HAL_FLASH_Unlock() != HAL_OK)
  {
    return BOOTLOADER_ERROR_FLASH;
  }

  for (index = 0U; index < length; index++)
  {
    if (HAL_FLASH_Program(FLASH_TYPEPROGRAM_BYTE, address + index, data[index]) != HAL_OK)
    {
      (void)HAL_FLASH_Lock();
      return BOOTLOADER_ERROR_FLASH;
    }
  }

  (void)HAL_FLASH_Lock();
  return BOOTLOADER_STATUS_OK;
}

uint8_t Bootloader_FlashWrite(
  Bootloader_FlashSession *session,
  uint32_t offset,
  const uint8_t *data,
  uint32_t length)
{
  uint32_t address = APP_FLASH_BASE + offset;

  if ((session == NULL) || (data == NULL) || (session->active == 0U) || (session->erased == 0U))
  {
    return BOOTLOADER_ERROR_SESSION;
  }

  if ((offset != session->next_offset) ||
      (length == 0U) ||
      ((offset + length) < offset) ||
      ((offset + length) > session->image_size) ||
      (Bootloader_FlashIsAppRange(address, length) == 0U))
  {
    return BOOTLOADER_ERROR_RANGE;
  }

  if (Bootloader_FlashProgramBytes(address, data, length) != BOOTLOADER_STATUS_OK)
  {
    return BOOTLOADER_ERROR_FLASH;
  }

  session->next_offset += length;
  return BOOTLOADER_STATUS_OK;
}

uint8_t Bootloader_FlashIsApplicationValid(void)
{
  const Bootloader_AppMetadata *stored = (const Bootloader_AppMetadata *)APP_METADATA_BASE;
  Bootloader_AppMetadata metadata = *stored;
  const uint8_t *app_image = (const uint8_t *)APP_FLASH_BASE;

  if ((metadata.magic != APP_METADATA_MAGIC) ||
      (metadata.format_version != APP_METADATA_FORMAT_VERSION) ||
      (metadata.image_size == 0U) || (metadata.image_size > APP_FLASH_SIZE) ||
      (metadata.record_crc32 != Bootloader_FlashCrc32(
        (const uint8_t *)&metadata.format_version,
        3U * (uint32_t)sizeof(uint32_t))) ||
      (Bootloader_FlashVectorsAreValid(metadata.image_size) == 0U) ||
      (Bootloader_FlashCrc32(app_image, metadata.image_size) != metadata.image_crc32))
  {
    return 0U;
  }

  return 1U;
}

uint8_t Bootloader_FlashCommitMetadata(uint32_t image_size, uint32_t image_crc32)
{
  FLASH_EraseInitTypeDef erase = {0};
  Bootloader_AppMetadata metadata = {0};
  const Bootloader_AppMetadata *stored = (const Bootloader_AppMetadata *)APP_METADATA_BASE;
  uint32_t sector_error = 0U;

  metadata.magic = APP_METADATA_MAGIC;
  metadata.format_version = APP_METADATA_FORMAT_VERSION;
  metadata.image_size = image_size;
  metadata.image_crc32 = image_crc32;
  metadata.record_crc32 = Bootloader_FlashCrc32(
    (const uint8_t *)&metadata.format_version,
    3U * (uint32_t)sizeof(uint32_t));

  erase.TypeErase = FLASH_TYPEERASE_SECTORS;
  erase.Banks = FLASH_BANK_1;
  erase.Sector = FLASH_SECTOR_7;
  erase.NbSectors = 1U;
  erase.VoltageRange = FLASH_VOLTAGE_RANGE_3;

  if (HAL_FLASH_Unlock() != HAL_OK)
  {
    return BOOTLOADER_ERROR_FLASH;
  }
  if (HAL_FLASHEx_Erase(&erase, &sector_error) != HAL_OK)
  {
    (void)HAL_FLASH_Lock();
    return BOOTLOADER_ERROR_FLASH;
  }
  (void)HAL_FLASH_Lock();

  if (Bootloader_FlashProgramBytes(
        APP_METADATA_BASE + (uint32_t)offsetof(Bootloader_AppMetadata, format_version),
        (const uint8_t *)&metadata.format_version,
        (uint32_t)sizeof(metadata) - (uint32_t)sizeof(metadata.magic)) != BOOTLOADER_STATUS_OK)
  {
    return BOOTLOADER_ERROR_FLASH;
  }

  if ((stored->format_version != metadata.format_version) ||
      (stored->image_size != metadata.image_size) ||
      (stored->image_crc32 != metadata.image_crc32) ||
      (stored->record_crc32 != metadata.record_crc32))
  {
    return BOOTLOADER_ERROR_VERIFY;
  }

  if (Bootloader_FlashProgramBytes(
        APP_METADATA_BASE,
        (const uint8_t *)&metadata.magic,
        (uint32_t)sizeof(metadata.magic)) != BOOTLOADER_STATUS_OK)
  {
    return BOOTLOADER_ERROR_FLASH;
  }

  return (Bootloader_FlashIsApplicationValid() != 0U) ? BOOTLOADER_STATUS_OK : BOOTLOADER_ERROR_VERIFY;
}

uint8_t Bootloader_FlashVerify(const Bootloader_FlashSession *session)
{
  const uint8_t *app_image = (const uint8_t *)APP_FLASH_BASE;
  uint8_t result;

  if ((session == NULL) || (session->active == 0U) || (session->erased == 0U) ||
      (session->next_offset != session->image_size))
  {
    return BOOTLOADER_ERROR_SESSION;
  }

  if ((Bootloader_FlashCrc32(app_image, session->image_size) != session->image_crc32) ||
      (Bootloader_FlashVectorsAreValid(session->image_size) == 0U))
  {
    return BOOTLOADER_ERROR_VERIFY;
  }

  result = Bootloader_FlashCommitMetadata(session->image_size, session->image_crc32);
  if (result != BOOTLOADER_STATUS_OK)
  {
    return result;
  }

  return BOOTLOADER_STATUS_OK;
}
