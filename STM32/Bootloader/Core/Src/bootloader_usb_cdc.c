#include "bootloader_usb_cdc.h"

#include "usbd_cdc_if.h"
#include "usbd_core.h"

#include <string.h>

static Bootloader_Parser s_usb_parser;
static Bootloader_Frame s_usb_frame;
static volatile uint8_t s_usb_frame_ready = 0U;
static volatile uint8_t s_usb_error_ready = 0U;
static uint8_t s_usb_error_code = 0U;
static uint8_t s_usb_tx_buffer[BOOTLOADER_FRAME_OVERHEAD + BOOTLOADER_MAX_PAYLOAD_SIZE];

uint8_t UserRxBufferFS[APP_RX_DATA_SIZE];
uint8_t UserTxBufferFS[APP_TX_DATA_SIZE];

static uint8_t line_coding[7] = {0x00, 0x08, 0x07, 0x00, 0x00, 0x00, 0x08};

extern USBD_HandleTypeDef hUsbDeviceFS;

static int8_t CDC_Init_FS(void);
static int8_t CDC_DeInit_FS(void);
static int8_t CDC_Control_FS(uint8_t cmd, uint8_t *pbuf, uint16_t length);
static int8_t CDC_Receive_FS(uint8_t *Buf, uint32_t *Len);
static int8_t CDC_TransmitCplt_FS(uint8_t *Buf, uint32_t *Len, uint8_t epnum);

USBD_CDC_ItfTypeDef USBD_Interface_fops_FS =
{
  CDC_Init_FS,
  CDC_DeInit_FS,
  CDC_Control_FS,
  CDC_Receive_FS,
  CDC_TransmitCplt_FS
};

void Bootloader_UsbCdcInit(void)
{
  Bootloader_ProtocolInitParser(&s_usb_parser);
  s_usb_frame_ready = 0U;
  s_usb_error_ready = 0U;
  s_usb_error_code = 0U;
}

void Bootloader_UsbCdcDeInit(void)
{
  (void)USBD_Stop(&hUsbDeviceFS);
  (void)USBD_DeInit(&hUsbDeviceFS);
  HAL_NVIC_DisableIRQ(OTG_FS_IRQn);
}

void Bootloader_UsbCdcHandleData(const uint8_t *data, uint32_t length)
{
  uint32_t index;

  if (data == NULL)
  {
    return;
  }

  for (index = 0U; index < length; index++)
  {
    Bootloader_Frame frame;
    Bootloader_ParseResult result;

    result = Bootloader_ProtocolParseByte(&s_usb_parser, data[index], &frame);
    if (result == BOOTLOADER_PARSE_FRAME_READY)
    {
      s_usb_frame = frame;
      s_usb_frame_ready = 1U;
    }
    else if (result == BOOTLOADER_PARSE_CHECKSUM_ERROR)
    {
      s_usb_error_code = BOOTLOADER_ERROR_CHECKSUM;
      s_usb_error_ready = 1U;
    }
    else if (result == BOOTLOADER_PARSE_LENGTH_ERROR)
    {
      s_usb_error_code = BOOTLOADER_ERROR_LENGTH;
      s_usb_error_ready = 1U;
    }
  }
}

uint8_t Bootloader_UsbCdcPollFrame(Bootloader_Frame *frame)
{
  if ((frame == NULL) || (s_usb_frame_ready == 0U))
  {
    return 0U;
  }

  *frame = s_usb_frame;
  s_usb_frame_ready = 0U;
  return 1U;
}

uint8_t Bootloader_UsbCdcPollError(uint8_t *error_code)
{
  if ((error_code == NULL) || (s_usb_error_ready == 0U))
  {
    return 0U;
  }

  *error_code = s_usb_error_code;
  s_usb_error_ready = 0U;
  return 1U;
}

uint8_t Bootloader_UsbCdcSendFrame(uint8_t frame_id, const uint8_t *payload, uint8_t length)
{
  size_t tx_size;

  tx_size = Bootloader_ProtocolEncode(frame_id, payload, length, s_usb_tx_buffer, sizeof(s_usb_tx_buffer));
  if (tx_size == 0U)
  {
    return USBD_FAIL;
  }

  return CDC_Transmit_FS(s_usb_tx_buffer, (uint16_t)tx_size);
}

static int8_t CDC_Init_FS(void)
{
  USBD_CDC_SetTxBuffer(&hUsbDeviceFS, UserTxBufferFS, 0);
  USBD_CDC_SetRxBuffer(&hUsbDeviceFS, UserRxBufferFS);
  return USBD_OK;
}

static int8_t CDC_DeInit_FS(void)
{
  return USBD_OK;
}

static int8_t CDC_Control_FS(uint8_t cmd, uint8_t *pbuf, uint16_t length)
{
  switch (cmd)
  {
    case CDC_SET_LINE_CODING:
      if (length == sizeof(line_coding))
      {
        memcpy(line_coding, pbuf, sizeof(line_coding));
      }
      break;

    case CDC_GET_LINE_CODING:
      memcpy(pbuf, line_coding, sizeof(line_coding));
      break;

    default:
      break;
  }

  return USBD_OK;
}

static int8_t CDC_Receive_FS(uint8_t *Buf, uint32_t *Len)
{
  Bootloader_UsbCdcHandleData(Buf, *Len);
  USBD_CDC_SetRxBuffer(&hUsbDeviceFS, Buf);
  USBD_CDC_ReceivePacket(&hUsbDeviceFS);
  return USBD_OK;
}

uint8_t CDC_Transmit_FS(uint8_t *Buf, uint16_t Len)
{
  USBD_CDC_HandleTypeDef *hcdc = (USBD_CDC_HandleTypeDef *)hUsbDeviceFS.pClassData;

  if ((hcdc == NULL) || (hcdc->TxState != 0U))
  {
    return USBD_BUSY;
  }

  USBD_CDC_SetTxBuffer(&hUsbDeviceFS, Buf, Len);
  return USBD_CDC_TransmitPacket(&hUsbDeviceFS);
}

static int8_t CDC_TransmitCplt_FS(uint8_t *Buf, uint32_t *Len, uint8_t epnum)
{
  UNUSED(Buf);
  UNUSED(Len);
  UNUSED(epnum);
  return USBD_OK;
}
