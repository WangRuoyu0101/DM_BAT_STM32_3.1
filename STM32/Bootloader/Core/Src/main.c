#include "app_bootloader_request.h"
#include "bootloader_config.h"
#include "bootloader_flash.h"
#include "bootloader_jump.h"
#include "bootloader_protocol.h"
#include "bootloader_usb_cdc.h"
#include "stm32f4xx_hal.h"
#include "usb_device.h"

#include <stddef.h>
#include <stdint.h>

#define BOOTLOADER_USB_REENUMERATE_DELAY_MS 120U
#define BOOTLOADER_USB_FINAL_ACK_DELAY_MS 20U

typedef enum
{
  BOOTLOADER_STATE_WAITING = 0U,
  BOOTLOADER_STATE_RECEIVING = 1U,
  BOOTLOADER_STATE_VERIFIED = 2U,
  BOOTLOADER_STATE_ERROR = 3U
} Bootloader_State;

static Bootloader_FlashSession s_session;
static uint8_t s_usb_cdc_enabled = 0U;
static uint8_t s_app_valid = 0U;
static uint8_t s_last_error = 0U;
static uint8_t s_status_pending = 1U;
static uint32_t s_led_last_toggle_tick = 0U;
static uint32_t s_status_last_report_tick = 0U;
static Bootloader_State s_state = BOOTLOADER_STATE_WAITING;

static void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void Bootloader_ForceUsbDisconnect(void);
static void Bootloader_EnableUsbCdc(void);
static void Bootloader_StatusLedRun(uint32_t current_tick);
static void Bootloader_SendFrame(uint8_t frame_id, const uint8_t *payload, uint8_t length);
static void Bootloader_SendAck(uint8_t seq, uint8_t command, uint8_t status);
static void Bootloader_SendError(uint8_t seq, uint8_t command, uint8_t error_code);
static void Bootloader_SendInfo(uint8_t seq);
static void Bootloader_SetState(Bootloader_State state, uint8_t error_code);
static void Bootloader_ReportStatusIfDue(uint32_t current_tick);
static void Bootloader_HandleFrame(const Bootloader_Frame *frame);
void Error_Handler(void);

int main(void)
{
  uint8_t stay_in_bootloader;

  HAL_Init();
  SystemClock_Config();
  MX_GPIO_Init();
  Bootloader_FlashResetSession(&s_session);
  s_app_valid = Bootloader_IsApplicationValid();

  stay_in_bootloader = App_BootloaderRequest_ConsumeFlag();
  if ((stay_in_bootloader != 0U) || (s_app_valid == 0U))
  {
    stay_in_bootloader = 1U;
    Bootloader_EnableUsbCdc();
  }
  if ((stay_in_bootloader == 0U) && (s_app_valid != 0U))
  {
    Bootloader_JumpToApplication();
  }
  if (s_usb_cdc_enabled == 0U)
  {
    Bootloader_EnableUsbCdc();
  }

  while (1)
  {
    Bootloader_Frame frame;

    Bootloader_StatusLedRun(HAL_GetTick());

    if ((s_usb_cdc_enabled != 0U) && (Bootloader_UsbCdcPollFrame(&frame) != 0U))
    {
      Bootloader_HandleFrame(&frame);
    }
    else
    {
      uint8_t error_code;

      if ((s_usb_cdc_enabled != 0U) && (Bootloader_UsbCdcPollError(&error_code) != 0U))
      {
        Bootloader_SendError(0U, 0U, error_code);
      }
    }

    Bootloader_ReportStatusIfDue(HAL_GetTick());
  }
}

static void Bootloader_EnableUsbCdc(void)
{
  if (s_usb_cdc_enabled != 0U)
  {
    return;
  }

  Bootloader_ForceUsbDisconnect();
  Bootloader_UsbCdcInit();
  MX_USB_DEVICE_Init();
  s_usb_cdc_enabled = 1U;
}

static void Bootloader_ForceUsbDisconnect(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};

  __HAL_RCC_GPIOA_CLK_ENABLE();

  GPIO_InitStruct.Pin = GPIO_PIN_12;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_12, GPIO_PIN_RESET);
  HAL_Delay(BOOTLOADER_USB_REENUMERATE_DELAY_MS);
  HAL_GPIO_DeInit(GPIOA, GPIO_PIN_12);
}

static void Bootloader_StatusLedRun(uint32_t current_tick)
{
  if ((uint32_t)(current_tick - s_led_last_toggle_tick) >= BOOTLOADER_LED_TOGGLE_PERIOD_MS)
  {
    s_led_last_toggle_tick = current_tick;
    HAL_GPIO_TogglePin(BOOTLOADER_LED_RUN_GPIO_PORT, BOOTLOADER_LED_RUN_PIN);
  }
}

static void Bootloader_SetState(Bootloader_State state, uint8_t error_code)
{
  s_state = state;
  s_last_error = error_code;
  s_status_pending = 1U;
}

static void Bootloader_ReportStatusIfDue(uint32_t current_tick)
{
  uint8_t payload[8];

  if ((s_usb_cdc_enabled == 0U) ||
      ((s_status_pending == 0U) &&
       ((uint32_t)(current_tick - s_status_last_report_tick) < BOOTLOADER_STATUS_REPORT_PERIOD_MS)))
  {
    return;
  }

  payload[0] = (uint8_t)s_state;
  payload[1] = s_app_valid;
  payload[2] = s_last_error;
  payload[3] = 0U;
  Bootloader_WriteLe32(&payload[4], s_session.next_offset);
  if (Bootloader_UsbCdcSendFrame(BOOTLOADER_FRAME_ID_STATUS, payload, (uint8_t)sizeof(payload)) == 0U)
  {
    s_status_last_report_tick = current_tick;
    s_status_pending = 0U;
  }
}

static void Bootloader_HandleFrame(const Bootloader_Frame *frame)
{
  uint8_t seq;
  uint8_t result;

  if ((frame == NULL) || (frame->length == 0U))
  {
    Bootloader_SendError(0U, 0U, BOOTLOADER_ERROR_LENGTH);
    return;
  }

  seq = frame->data[0];

  switch (frame->frame_id)
  {
    case BOOTLOADER_FRAME_ID_HELLO:
      if (frame->length != 1U)
      {
        Bootloader_SendError(seq, frame->frame_id, BOOTLOADER_ERROR_LENGTH);
      }
      else
      {
        Bootloader_SendInfo(seq);
      }
      break;

    case BOOTLOADER_FRAME_ID_START:
      if (frame->length != 9U)
      {
        Bootloader_SendError(seq, frame->frame_id, BOOTLOADER_ERROR_LENGTH);
        break;
      }
      result = Bootloader_FlashStartSession(
        &s_session,
        Bootloader_ReadLe32(&frame->data[1]),
        Bootloader_ReadLe32(&frame->data[5]));
      if (result == BOOTLOADER_STATUS_OK)
      {
        Bootloader_SetState(BOOTLOADER_STATE_WAITING, 0U);
        Bootloader_SendAck(seq, frame->frame_id, result);
      }
      else
      {
        Bootloader_SendError(seq, frame->frame_id, result);
      }
      break;

    case BOOTLOADER_FRAME_ID_ERASE:
      if (frame->length != 1U)
      {
        Bootloader_SendError(seq, frame->frame_id, BOOTLOADER_ERROR_LENGTH);
        break;
      }
      result = Bootloader_FlashEraseApplication(&s_session);
      s_app_valid = Bootloader_IsApplicationValid();
      if (result == BOOTLOADER_STATUS_OK)
      {
        Bootloader_SetState(BOOTLOADER_STATE_RECEIVING, 0U);
        Bootloader_SendAck(seq, frame->frame_id, result);
      }
      else
      {
        Bootloader_SendError(seq, frame->frame_id, result);
      }
      break;

    case BOOTLOADER_FRAME_ID_WRITE:
      if (frame->length < 6U)
      {
        Bootloader_SendError(seq, frame->frame_id, BOOTLOADER_ERROR_LENGTH);
        break;
      }
      result = Bootloader_FlashWrite(
        &s_session,
        Bootloader_ReadLe32(&frame->data[1]),
        &frame->data[5],
        (uint32_t)frame->length - 5U);
      if (result == BOOTLOADER_STATUS_OK)
      {
        Bootloader_SendAck(seq, frame->frame_id, result);
      }
      else
      {
        Bootloader_SendError(seq, frame->frame_id, result);
      }
      break;

    case BOOTLOADER_FRAME_ID_VERIFY:
      if (frame->length != 1U)
      {
        Bootloader_SendError(seq, frame->frame_id, BOOTLOADER_ERROR_LENGTH);
        break;
      }
      result = Bootloader_FlashVerify(&s_session);
      s_app_valid = Bootloader_IsApplicationValid();
      if (result == BOOTLOADER_STATUS_OK)
      {
        Bootloader_SetState(BOOTLOADER_STATE_VERIFIED, 0U);
        Bootloader_SendAck(seq, frame->frame_id, result);
      }
      else
      {
        Bootloader_SendError(seq, frame->frame_id, result);
      }
      break;

    case BOOTLOADER_FRAME_ID_JUMP:
      if (Bootloader_IsApplicationValid() == 0U)
      {
        Bootloader_SendError(seq, frame->frame_id, BOOTLOADER_ERROR_APP_INVALID);
      }
      else
      {
        Bootloader_SendAck(seq, frame->frame_id, BOOTLOADER_STATUS_OK);
        HAL_Delay(BOOTLOADER_USB_FINAL_ACK_DELAY_MS);
        Bootloader_UsbCdcDeInit();
        HAL_Delay(BOOTLOADER_USB_REENUMERATE_DELAY_MS);
        Bootloader_JumpToApplication();
      }
      break;

    case BOOTLOADER_FRAME_ID_RESET:
      Bootloader_SendAck(seq, frame->frame_id, BOOTLOADER_STATUS_OK);
      HAL_Delay(BOOTLOADER_USB_FINAL_ACK_DELAY_MS);
      NVIC_SystemReset();
      break;

    default:
      Bootloader_SendError(seq, frame->frame_id, BOOTLOADER_ERROR_UNKNOWN_COMMAND);
      break;
  }
}

static void Bootloader_SendFrame(uint8_t frame_id, const uint8_t *payload, uint8_t length)
{
  (void)Bootloader_UsbCdcSendFrame(frame_id, payload, length);
}

static void Bootloader_SendAck(uint8_t seq, uint8_t command, uint8_t status)
{
  uint8_t payload[3];

  payload[0] = seq;
  payload[1] = command;
  payload[2] = status;
  Bootloader_SendFrame(BOOTLOADER_FRAME_ID_ACK, payload, (uint8_t)sizeof(payload));
}

static void Bootloader_SendError(uint8_t seq, uint8_t command, uint8_t error_code)
{
  uint8_t payload[3];

  Bootloader_SetState(BOOTLOADER_STATE_ERROR, error_code);
  payload[0] = seq;
  payload[1] = command;
  payload[2] = error_code;
  Bootloader_SendFrame(BOOTLOADER_FRAME_ID_ERROR, payload, (uint8_t)sizeof(payload));
}

static void Bootloader_SendInfo(uint8_t seq)
{
  uint8_t payload[17];

  payload[0] = seq;
  Bootloader_WriteLe32(&payload[1], APP_FLASH_BASE);
  Bootloader_WriteLe32(&payload[5], APP_FLASH_SIZE);
  Bootloader_WriteLe32(&payload[9], BOOTLOADER_WRITE_DATA_MAX);
  Bootloader_WriteLe32(&payload[13], BOOTLOADER_VERSION);
  Bootloader_SendFrame(BOOTLOADER_FRAME_ID_INFO, payload, (uint8_t)sizeof(payload));
}

static void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);

  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLM = 8;
  RCC_OscInitStruct.PLL.PLLN = 336;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;
  RCC_OscInitStruct.PLL.PLLQ = 7;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK |
                                RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV4;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV2;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_5) != HAL_OK)
  {
    Error_Handler();
  }
}

static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};

  __HAL_RCC_GPIOB_CLK_ENABLE();

  HAL_GPIO_WritePin(BOOTLOADER_LED_RUN_GPIO_PORT, BOOTLOADER_LED_RUN_PIN, GPIO_PIN_RESET);

  GPIO_InitStruct.Pin = BOOTLOADER_LED_RUN_PIN;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(BOOTLOADER_LED_RUN_GPIO_PORT, &GPIO_InitStruct);
}

void HAL_MspInit(void)
{
  __HAL_RCC_SYSCFG_CLK_ENABLE();
  __HAL_RCC_PWR_CLK_ENABLE();
}

void SysTick_Handler(void)
{
  HAL_IncTick();
}

extern PCD_HandleTypeDef hpcd_USB_OTG_FS;

void OTG_FS_IRQHandler(void)
{
  HAL_PCD_IRQHandler(&hpcd_USB_OTG_FS);
}

void Error_Handler(void)
{
  __disable_irq();
  while (1)
  {
  }
}
