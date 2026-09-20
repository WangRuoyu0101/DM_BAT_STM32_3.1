#include "app_uart5_slave.h"
#include "app_rgb_protocol.h"
#include "usbd_cdc_if.h"
#include "usbd_core.h"

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#define APP_UART5_SLAVE_TX_TIMEOUT_MS 20U
#define APP_UART5_SLAVE_STATUS_OK 0x00U
#define APP_UART5_SLAVE_BOOTLOADER_RESULT_OK 0x00U
#define APP_UART5_SLAVE_BOOTLOADER_RESET_DELAY_TICKS 250U
#define APP_UART5_SLAVE_BOOTLOADER_LED_TOGGLE_TICKS 125U
#define APP_UART5_SLAVE_BOOTLOADER_REQUEST_LENGTH 5U
#define APP_UART5_SLAVE_USB_TX_QUEUE_DEPTH 2U
#define APP_UART5_SLAVE_USB_TX_FRAME_SIZE (APP_COMM_FRAME_OVERHEAD + APP_COMM_MAX_PAYLOAD_SIZE)

typedef enum
{
  APP_UART5_SLAVE_PORT_UART5 = 0U,
  APP_UART5_SLAVE_PORT_USB = 1U
} App_Uart5SlavePort;

typedef struct
{
  uint16_t length;
  uint8_t data[APP_UART5_SLAVE_USB_TX_FRAME_SIZE];
} App_Uart5SlaveUsbTxFrame;

/*
 * UART5 应用协议从机。
 * 中断上下文只接收字节、喂给协议解析器并记录一帧结果；
 * 主循环再读取缓存帧并执行业务响应，避免在中断中做 HAL_UART_Transmit 等阻塞操作。
 */
static UART_HandleTypeDef *s_uart5 = NULL;
static uint8_t s_rx_byte = 0U;
static App_CommParser s_parser;
static App_CommFrame s_rx_frame;
static volatile uint8_t s_frame_ready = 0U;
static volatile uint8_t s_error_ready = 0U;
static volatile uint8_t s_error_code = 0U;
static App_CommParser s_usb_parser;
static App_CommFrame s_usb_rx_frame;
static volatile uint8_t s_usb_frame_ready = 0U;
static volatile uint8_t s_usb_error_ready = 0U;
static volatile uint8_t s_usb_error_code = 0U;
static App_Uart5SlaveUsbTxFrame s_usb_tx_queue[APP_UART5_SLAVE_USB_TX_QUEUE_DEPTH];
static volatile uint8_t s_usb_tx_head = 0U;
static volatile uint8_t s_usb_tx_count = 0U;
static volatile uint8_t s_usb_tx_in_flight = 0U;
static uint32_t s_usb_busy_retries = 0U;
static uint32_t s_usb_queue_overflows = 0U;
static uint32_t s_usb_tx_failures = 0U;
static App_Uart5SlavePort s_response_port = APP_UART5_SLAVE_PORT_UART5;
static uint8_t s_bootloader_reset_pending = 0U;
static uint32_t s_bootloader_reset_start_tick = 0U;
static uint32_t s_bootloader_led_last_tick = 0U;

extern USBD_HandleTypeDef hUsbDeviceFS;

/* 运行态进入 bootloader 的请求密码，payload 为 seq + "wb88"。 */
static const uint8_t s_bootloader_password[4] = {'w', 'b', '8', '8'};

static void App_Uart5Slave_IncrementSaturated(uint32_t *counter)
{
  if (*counter != UINT32_MAX)
  {
    (*counter)++;
  }
}

static void App_Uart5Slave_StoreU32(uint8_t *output, uint32_t value)
{
  output[0] = (uint8_t)(value & 0xFFU);
  output[1] = (uint8_t)((value >> 8U) & 0xFFU);
  output[2] = (uint8_t)((value >> 16U) & 0xFFU);
  output[3] = (uint8_t)((value >> 24U) & 0xFFU);
}

static void App_Uart5Slave_QueueUsbFrame(const uint8_t *data, uint16_t length)
{
  uint8_t tail;
  uint32_t primask = __get_PRIMASK();

  __disable_irq();
  if (s_usb_tx_count >= APP_UART5_SLAVE_USB_TX_QUEUE_DEPTH)
  {
    App_Uart5Slave_IncrementSaturated(&s_usb_queue_overflows);
    __set_PRIMASK(primask);
    return;
  }
  tail = (uint8_t)((s_usb_tx_head + s_usb_tx_count) % APP_UART5_SLAVE_USB_TX_QUEUE_DEPTH);
  s_usb_tx_queue[tail].length = length;
  memcpy(s_usb_tx_queue[tail].data, data, length);
  s_usb_tx_count++;
  __set_PRIMASK(primask);
}

static void App_Uart5Slave_PumpUsbTx(void)
{
  App_Uart5SlaveUsbTxFrame *frame;
  uint8_t result;
  uint32_t primask = __get_PRIMASK();

  __disable_irq();
  if ((s_usb_tx_count == 0U) || (s_usb_tx_in_flight != 0U))
  {
    __set_PRIMASK(primask);
    return;
  }

  frame = &s_usb_tx_queue[s_usb_tx_head];
  s_usb_tx_in_flight = 1U;
  result = CDC_Transmit_FS(frame->data, frame->length);
  if (result == USBD_BUSY)
  {
    s_usb_tx_in_flight = 0U;
    App_Uart5Slave_IncrementSaturated(&s_usb_busy_retries);
  }
  else if (result != USBD_OK)
  {
    s_usb_tx_in_flight = 0U;
    s_usb_tx_head = (uint8_t)((s_usb_tx_head + 1U) % APP_UART5_SLAVE_USB_TX_QUEUE_DEPTH);
    s_usb_tx_count--;
    App_Uart5Slave_IncrementSaturated(&s_usb_tx_failures);
  }
  __set_PRIMASK(primask);
}

/**
  * @brief 通过 UART5 发送一帧协议数据。
  * @param frame_id 响应帧ID。
  * @param payload 响应数据区指针，长度为 0 时可为 NULL。
  * @param length 响应数据区长度。
  * @retval None
  */
static void App_Uart5Slave_SendFrame(uint8_t frame_id, const uint8_t *payload, uint8_t length)
{
  uint8_t tx_buffer[APP_COMM_FRAME_OVERHEAD + APP_COMM_MAX_PAYLOAD_SIZE];
  size_t tx_size;

  tx_size = App_CommProtocol_Encode(frame_id, payload, length, tx_buffer, sizeof(tx_buffer));
  if (tx_size > 0U)
  {
    if (s_response_port == APP_UART5_SLAVE_PORT_USB)
    {
      App_Uart5Slave_QueueUsbFrame(tx_buffer, (uint16_t)tx_size);
    }
    else
    {
      (void)HAL_UART_Transmit(s_uart5, tx_buffer, (uint16_t)tx_size, APP_UART5_SLAVE_TX_TIMEOUT_MS);
    }
  }
}

/**
  * @brief 发送从机状态响应帧。
  * @param seq 主机请求序号。
  * @param current_tick 当前 2 ms 周期计数值。
  * @retval None
  */
static void App_Uart5Slave_SendStatus(uint8_t seq, uint32_t current_tick)
{
  uint8_t payload[19];

  payload[0] = seq;
  payload[1] = (uint8_t)(current_tick & 0xFFU);
  payload[2] = (uint8_t)((current_tick >> 8U) & 0xFFU);
  payload[3] = (uint8_t)((current_tick >> 16U) & 0xFFU);
  payload[4] = (uint8_t)((current_tick >> 24U) & 0xFFU);
  payload[5] = APP_UART5_SLAVE_STATUS_OK;
  payload[6] = App_RelayControl_GetBitmap();
  App_Uart5Slave_StoreU32(&payload[7], s_usb_busy_retries);
  App_Uart5Slave_StoreU32(&payload[11], s_usb_queue_overflows);
  App_Uart5Slave_StoreU32(&payload[15], s_usb_tx_failures);

  App_Uart5Slave_SendFrame(APP_COMM_FRAME_ID_STATUS_RESPONSE, payload, (uint8_t)sizeof(payload));
}

/**
  * @brief 发送从机错误响应帧。
  * @param seq 主机请求序号，无法识别时为 0。
  * @param source_frame_id 触发错误的原始帧ID，无法识别时为 0。
  * @param error_code 错误码。
  * @retval None
  */
static void App_Uart5Slave_SendError(uint8_t seq, uint8_t source_frame_id, uint8_t error_code)
{
  uint8_t payload[3];

  payload[0] = seq;
  payload[1] = source_frame_id;
  payload[2] = error_code;
  App_Uart5Slave_SendFrame(APP_COMM_FRAME_ID_ERROR_RESPONSE, payload, (uint8_t)sizeof(payload));
}

/**
  * @brief 发送 GPIO 控制响应帧。
  * @param seq 主机请求序号。
  * @param channel_id 控制通道 ID。
  * @param result 控制结果码。
  * @retval None
  */
static void App_Uart5Slave_SendControlResponse(uint8_t seq, uint8_t channel_id, uint8_t result)
{
  uint8_t payload[3];

  payload[0] = seq;
  payload[1] = channel_id;
  payload[2] = result;
  App_Uart5Slave_SendFrame(APP_COMM_FRAME_ID_GPIO_CONTROL_RESPONSE, payload, (uint8_t)sizeof(payload));
}

/**
  * @brief 发送 GPIO 状态响应帧。
  * @param seq 主机请求序号。
  * @retval None
  */
static void App_Uart5Slave_SendGpioStatus(uint8_t seq)
{
  uint8_t payload[2];

  payload[0] = seq;
  payload[1] = App_RelayControl_GetBitmap();
  App_Uart5Slave_SendFrame(APP_COMM_FRAME_ID_GPIO_STATUS_RESPONSE, payload, (uint8_t)sizeof(payload));
}

/**
  * @brief 发送三路超声波距离汇总响应帧。
  * @param seq 主机请求序号。
  * @retval None
  */
static void App_Uart5Slave_SendUltrasonicStatus(uint8_t seq)
{
  App_UltrasonicSnapshot ultrasonic_snapshot;
  uint8_t payload[9];

  App_UltrasonicManager_GetSnapshot(&ultrasonic_snapshot);

  payload[0] = seq;
  payload[1] = (uint8_t)(ultrasonic_snapshot.front_mm & 0xFFU);
  payload[2] = (uint8_t)((ultrasonic_snapshot.front_mm >> 8U) & 0xFFU);
  payload[3] = (uint8_t)(ultrasonic_snapshot.left_mm & 0xFFU);
  payload[4] = (uint8_t)((ultrasonic_snapshot.left_mm >> 8U) & 0xFFU);
  payload[5] = (uint8_t)(ultrasonic_snapshot.right_mm & 0xFFU);
  payload[6] = (uint8_t)((ultrasonic_snapshot.right_mm >> 8U) & 0xFFU);
  payload[7] = ultrasonic_snapshot.valid_bitmap;
  payload[8] = ultrasonic_snapshot.error_bitmap;

  App_Uart5Slave_SendFrame(APP_COMM_FRAME_ID_ULTRASONIC_RESPONSE, payload, (uint8_t)sizeof(payload));
}

static void App_Uart5Slave_SendCS1237Status(uint8_t seq)
{
  App_CS1237_Snapshot snapshot;
  uint8_t payload[8];
  uint32_t raw_adc;

  App_CS1237_GetSnapshot(&snapshot);
  raw_adc = (uint32_t)snapshot.raw_adc;
  payload[0] = seq;
  payload[1] = (uint8_t)(raw_adc & 0xFFU);
  payload[2] = (uint8_t)((raw_adc >> 8U) & 0xFFU);
  payload[3] = (uint8_t)((raw_adc >> 16U) & 0xFFU);
  payload[4] = (uint8_t)((raw_adc >> 24U) & 0xFFU);
  payload[5] = (uint8_t)snapshot.channel;
  payload[6] = snapshot.valid;
  payload[7] = snapshot.error;
  App_Uart5Slave_SendFrame(APP_COMM_FRAME_ID_CS1237_RESPONSE, payload, (uint8_t)sizeof(payload));
}

static void App_Uart5Slave_SendCS1237ChannelResponse(uint8_t seq, uint8_t channel, uint8_t result)
{
  uint8_t payload[3] = {seq, channel, result};

  App_Uart5Slave_SendFrame(
    APP_COMM_FRAME_ID_CS1237_CHANNEL_RESPONSE,
    payload,
    (uint8_t)sizeof(payload));
}

static void App_Uart5Slave_SendFanControlResponse(uint8_t seq, uint8_t result)
{
  uint8_t payload[3] = {seq, App_BoardIO_GetFanLevel(), result};

  App_Uart5Slave_SendFrame(
    APP_COMM_FRAME_ID_FAN_CONTROL_RESPONSE,
    payload,
    (uint8_t)sizeof(payload));
}

static void App_Uart5Slave_SendBoardIOStatus(uint8_t seq)
{
  App_BoardIO_Snapshot snapshot;
  uint8_t payload[7];

  App_BoardIO_GetSnapshot(&snapshot);
  payload[0] = seq;
  payload[1] = snapshot.fan_level;
  payload[2] = (uint8_t)(snapshot.fan1_rpm & 0xFFU);
  payload[3] = (uint8_t)((snapshot.fan1_rpm >> 8U) & 0xFFU);
  payload[4] = (uint8_t)(snapshot.fan2_rpm & 0xFFU);
  payload[5] = (uint8_t)((snapshot.fan2_rpm >> 8U) & 0xFFU);
  payload[6] = snapshot.key_bitmap;
  App_Uart5Slave_SendFrame(
    APP_COMM_FRAME_ID_BOARD_IO_RESPONSE,
    payload,
    (uint8_t)sizeof(payload));
}

/**
  * @brief 发送进入 bootloader 请求响应帧。
  * @param seq 主机请求序号。
  * @param result 请求处理结果。
  * @retval None
  */
static void App_Uart5Slave_SendBootloaderResponse(uint8_t seq, uint8_t result)
{
  uint8_t payload[2];

  payload[0] = seq;
  payload[1] = result;
  App_Uart5Slave_SendFrame(APP_COMM_FRAME_ID_BOOTLOADER_RESPONSE, payload, (uint8_t)sizeof(payload));
}

/**
  * @brief 启动应用到 bootloader 的延时复位流程。
  * @param seq 主机请求序号。
  * @param current_tick 当前 2 ms 周期计数值。
  * @retval None
  */
static void App_Uart5Slave_StartBootloaderReset(uint8_t seq, uint32_t current_tick)
{
  App_Uart5Slave_SendBootloaderResponse(seq, APP_UART5_SLAVE_BOOTLOADER_RESULT_OK);
  App_BootloaderRequest_SetFlag();
  s_bootloader_reset_pending = 1U;
  s_bootloader_reset_start_tick = current_tick;
  s_bootloader_led_last_tick = current_tick;
}

/**
  * @brief 校验 bootloader 请求帧中的固定密码。
  * @param frame 已通过 CRC8 的 bootloader 请求帧。
  * @retval 1 表示密码正确，0 表示密码错误。
  */
static uint8_t App_Uart5Slave_IsBootloaderPasswordValid(const App_CommFrame *frame)
{
  uint8_t index;

  for (index = 0U; index < (uint8_t)sizeof(s_bootloader_password); index++)
  {
    if (frame->data[index + 1U] != s_bootloader_password[index])
    {
      return 0U;
    }
  }

  return 1U;
}

static void App_Uart5Slave_DeInitUsbBeforeReset(void)
{
  (void)USBD_Stop(&hUsbDeviceFS);
  (void)USBD_DeInit(&hUsbDeviceFS);
  HAL_NVIC_DisableIRQ(OTG_FS_IRQn);
  HAL_Delay(50U);
}

/**
  * @brief 处理 bootloader 请求后的等待窗口，期间 LED_RUN 快闪并最终软件复位。
  * @param current_tick 当前 2 ms 周期计数值。
  * @retval None
  */
static void App_Uart5Slave_RunBootloaderReset(uint32_t current_tick)
{
  if (s_bootloader_reset_pending == 0U)
  {
    return;
  }

  if ((uint32_t)(current_tick - s_bootloader_led_last_tick) >= APP_UART5_SLAVE_BOOTLOADER_LED_TOGGLE_TICKS)
  {
    s_bootloader_led_last_tick = current_tick;
    HAL_GPIO_TogglePin(LED_RUN_GPIO_Port, LED_RUN_Pin);
  }

  if ((uint32_t)(current_tick - s_bootloader_reset_start_tick) >= APP_UART5_SLAVE_BOOTLOADER_RESET_DELAY_TICKS)
  {
    App_Uart5Slave_DeInitUsbBeforeReset();
    NVIC_SystemReset();
  }
}

static void App_Uart5Slave_ProcessFrame(const App_CommFrame *frame, uint32_t current_tick)
{
  if (frame->frame_id == APP_COMM_FRAME_ID_STATUS_QUERY)
  {
    App_CommStatusQuery status_query;
    uint8_t result;

    result = App_CommProtocol_DecodeStatusQuery(frame, &status_query);
    if (result == APP_COMM_CONTROL_RESULT_OK)
    {
      App_Uart5Slave_SendStatus(status_query.seq, current_tick);
    }
    else
    {
      App_Uart5Slave_SendError(status_query.seq, frame->frame_id, APP_COMM_ERROR_CODE_LENGTH);
    }
  }
  else if (frame->frame_id == APP_COMM_FRAME_ID_GPIO_CONTROL_REQUEST)
  {
    App_CommGpioControl control;
    uint8_t result;

    result = App_CommProtocol_DecodeGpioControlRequest(frame, &control);
    if (result == APP_COMM_CONTROL_RESULT_OK)
    {
      result = App_RelayControl_Apply(&control, current_tick);
    }

    App_Uart5Slave_SendControlResponse(control.seq, control.channel_id, result);
  }
  else if (frame->frame_id == APP_COMM_FRAME_ID_GPIO_STATUS_QUERY)
  {
    App_CommGpioStatusQuery gpio_status_query;
    uint8_t result;

    result = App_CommProtocol_DecodeGpioStatusQuery(frame, &gpio_status_query);
    if (result == APP_COMM_CONTROL_RESULT_OK)
    {
      App_Uart5Slave_SendGpioStatus(gpio_status_query.seq);
    }
    else
    {
      App_Uart5Slave_SendError(gpio_status_query.seq, frame->frame_id, APP_COMM_ERROR_CODE_LENGTH);
    }
  }
  else if (frame->frame_id == APP_COMM_FRAME_ID_ULTRASONIC_QUERY)
  {
    App_CommUltrasonicQuery ultrasonic_query;
    uint8_t result;

    result = App_CommProtocol_DecodeUltrasonicQuery(frame, &ultrasonic_query);
    if (result == APP_COMM_CONTROL_RESULT_OK)
    {
      App_Uart5Slave_SendUltrasonicStatus(ultrasonic_query.seq);
    }
    else
    {
      App_Uart5Slave_SendError(ultrasonic_query.seq, frame->frame_id, APP_COMM_ERROR_CODE_LENGTH);
    }
  }
  else if (frame->frame_id == APP_COMM_FRAME_ID_BOOTLOADER_REQUEST)
  {
    uint8_t seq = (frame->length > 0U) ? frame->data[0] : 0U;

    if (frame->length != APP_UART5_SLAVE_BOOTLOADER_REQUEST_LENGTH)
    {
      App_Uart5Slave_SendError(seq, frame->frame_id, APP_COMM_ERROR_CODE_LENGTH);
    }
    else if (App_Uart5Slave_IsBootloaderPasswordValid(frame) == 0U)
    {
      App_Uart5Slave_SendError(seq, frame->frame_id, APP_COMM_ERROR_CODE_AUTH);
    }
    else
    {
      App_Uart5Slave_StartBootloaderReset(seq, current_tick);
    }
  }
  else if (frame->frame_id == APP_COMM_FRAME_ID_CS1237_QUERY)
  {
    App_CommCS1237Query query;
    uint8_t result = App_CommProtocol_DecodeCS1237Query(frame, &query);

    if (result == APP_COMM_CONTROL_RESULT_OK)
    {
      App_Uart5Slave_SendCS1237Status(query.seq);
    }
    else
    {
      App_Uart5Slave_SendError(query.seq, frame->frame_id, APP_COMM_ERROR_CODE_LENGTH);
    }
  }
  else if (frame->frame_id == APP_COMM_FRAME_ID_CS1237_CHANNEL_REQUEST)
  {
    App_CommCS1237ChannelRequest request;
    uint8_t result = App_CommProtocol_DecodeCS1237ChannelRequest(frame, &request);

    if (result == APP_COMM_CONTROL_RESULT_OK)
    {
      result = (uint8_t)App_CS1237_SetChannel((App_CS1237_Channel)request.channel);
      App_Uart5Slave_SendCS1237ChannelResponse(request.seq, request.channel, result);
    }
    else
    {
      App_Uart5Slave_SendError(request.seq, frame->frame_id, APP_COMM_ERROR_CODE_LENGTH);
    }
  }
  else if (frame->frame_id == APP_COMM_FRAME_ID_FAN_CONTROL_REQUEST)
  {
    App_CommFanControl control;
    uint8_t result = App_CommProtocol_DecodeFanControlRequest(frame, &control);

    if (result == APP_COMM_CONTROL_RESULT_OK)
    {
      result = App_BoardIO_SetFanLevel(control.level);
      App_Uart5Slave_SendFanControlResponse(control.seq, result);
    }
    else
    {
      App_Uart5Slave_SendError(control.seq, frame->frame_id, APP_COMM_ERROR_CODE_LENGTH);
    }
  }
  else if (frame->frame_id == APP_COMM_FRAME_ID_BOARD_IO_QUERY)
  {
    App_CommBoardIOQuery query;
    uint8_t result = App_CommProtocol_DecodeBoardIOQuery(frame, &query);

    if (result == APP_COMM_CONTROL_RESULT_OK)
    {
      App_Uart5Slave_SendBoardIOStatus(query.seq);
    }
    else
    {
      App_Uart5Slave_SendError(query.seq, frame->frame_id, APP_COMM_ERROR_CODE_LENGTH);
    }
  }
  else if ((frame->frame_id == APP_COMM_FRAME_ID_RGB_SET_REQUEST) ||
           (frame->frame_id == APP_COMM_FRAME_ID_RGB_QUERY))
  {
    App_CommFrame response;

    App_RgbProtocol_Process(frame, &response);
    App_Uart5Slave_SendFrame(response.frame_id, response.data, response.length);
  }
  else
  {
    uint8_t seq = (frame->length > 0U) ? frame->data[0] : 0U;
    App_Uart5Slave_SendError(seq, frame->frame_id, APP_COMM_ERROR_CODE_CMD);
  }
}

/**
  * @brief 初始化 UART5 从机通信模块。
  * @param huart UART5 句柄指针。
  * @retval HAL_OK 表示初始化并启动接收成功，其他值表示失败。
  */
HAL_StatusTypeDef App_Uart5Slave_Init(UART_HandleTypeDef *huart)
{
  if ((huart == NULL) || (huart->Instance != UART5))
  {
    return HAL_ERROR;
  }

  s_uart5 = huart;
  s_rx_byte = 0U;
  s_frame_ready = 0U;
  s_error_ready = 0U;
  s_error_code = 0U;
  s_usb_frame_ready = 0U;
  s_usb_error_ready = 0U;
  s_usb_error_code = 0U;
  s_usb_tx_head = 0U;
  s_usb_tx_count = 0U;
  s_usb_tx_in_flight = 0U;
  s_usb_busy_retries = 0U;
  s_usb_queue_overflows = 0U;
  s_usb_tx_failures = 0U;
  s_response_port = APP_UART5_SLAVE_PORT_UART5;
  s_bootloader_reset_pending = 0U;
  s_bootloader_reset_start_tick = 0U;
  s_bootloader_led_last_tick = 0U;
  App_CommProtocol_InitParser(&s_parser);
  App_CommProtocol_InitParser(&s_usb_parser);

  /* 采用单字节接收，便于协议层在连续字节流中寻找帧头。 */
  return HAL_UART_Receive_IT(s_uart5, &s_rx_byte, 1U);
}

/**
  * @brief 在主循环靠前位置优先处理已解析完成的 GPIO 控制帧。
  * @param current_tick 当前 2 ms 周期计数值，预留用于后续时序诊断。
  * @retval None
  */
void App_Uart5Slave_RunFastGpio(uint32_t current_tick)
{
  App_CommFrame frame;
  App_CommGpioControl control = {0};
  uint8_t frame_ready = 0U;
  uint8_t result;
  uint32_t primask;

  if ((s_uart5 == NULL) || (s_bootloader_reset_pending != 0U))
  {
    return;
  }

  primask = __get_PRIMASK();
  __disable_irq();
  frame = s_rx_frame;
  frame_ready = s_frame_ready;
  if ((frame_ready != 0U) && (frame.frame_id == APP_COMM_FRAME_ID_GPIO_CONTROL_REQUEST))
  {
    s_frame_ready = 0U;
  }
  else
  {
    frame_ready = 0U;
  }
  __set_PRIMASK(primask);

  if (frame_ready == 0U)
  {
    return;
  }

  /* GPIO 控制帧在超声波任务前执行；响应仍在 GPIO 写入后发送。 */
  result = App_CommProtocol_DecodeGpioControlRequest(&frame, &control);
  if (result == APP_COMM_CONTROL_RESULT_OK)
  {
    result = App_RelayControl_Apply(&control, current_tick);
  }

  s_response_port = APP_UART5_SLAVE_PORT_UART5;
  App_Uart5Slave_SendControlResponse(control.seq, control.channel_id, result);
}

/**
  * @brief 在主循环中处理已解析完成的主机帧。
  * @param current_tick 当前 2 ms 周期计数值，用于状态响应载荷。
  * @retval None
  */
void App_Uart5Slave_Run(uint32_t current_tick)
{
  App_CommFrame frame;
  uint8_t error_ready = 0U;
  uint8_t error_code = 0U;
  uint8_t frame_ready = 0U;
  uint32_t primask;

  if (s_uart5 == NULL)
  {
    return;
  }

  App_Uart5Slave_PumpUsbTx();
  App_Uart5Slave_RunBootloaderReset(current_tick);
  if (s_bootloader_reset_pending != 0U)
  {
    return;
  }

  /* 与 UART 接收中断共享解析结果，复制后再在主循环中发送响应。 */
  primask = __get_PRIMASK();
  __disable_irq();
  frame = s_rx_frame;
  frame_ready = s_frame_ready;
  error_ready = s_error_ready;
  error_code = s_error_code;
  s_frame_ready = 0U;
  s_error_ready = 0U;
  s_error_code = 0U;
  __set_PRIMASK(primask);

  if (error_ready != 0U)
  {
    s_response_port = APP_UART5_SLAVE_PORT_UART5;
    App_Uart5Slave_SendError(0U, 0U, error_code);
    return;
  }

  if (frame_ready != 0U)
  {
    s_response_port = APP_UART5_SLAVE_PORT_UART5;
    App_Uart5Slave_ProcessFrame(&frame, current_tick);
  }

  primask = __get_PRIMASK();
  __disable_irq();
  frame = s_usb_rx_frame;
  frame_ready = s_usb_frame_ready;
  error_ready = s_usb_error_ready;
  error_code = s_usb_error_code;
  s_usb_frame_ready = 0U;
  s_usb_error_ready = 0U;
  s_usb_error_code = 0U;
  __set_PRIMASK(primask);

  if (error_ready != 0U)
  {
    s_response_port = APP_UART5_SLAVE_PORT_USB;
    App_Uart5Slave_SendError(0U, 0U, error_code);
    s_response_port = APP_UART5_SLAVE_PORT_UART5;
    return;
  }

  if (frame_ready != 0U)
  {
    s_response_port = APP_UART5_SLAVE_PORT_USB;
    App_Uart5Slave_ProcessFrame(&frame, current_tick);
  }

  s_response_port = APP_UART5_SLAVE_PORT_UART5;
  App_Uart5Slave_PumpUsbTx();
}

uint8_t App_Uart5Slave_IsBootloaderResetPending(void)
{
  return s_bootloader_reset_pending;
}

void App_Uart5Slave_HandleUsbData(const uint8_t *data, uint32_t length)
{
  uint32_t index;

  if ((data == NULL) || (s_bootloader_reset_pending != 0U))
  {
    return;
  }

  for (index = 0U; index < length; index++)
  {
    if ((s_usb_frame_ready == 0U) && (s_usb_error_ready == 0U))
    {
      App_CommParseResult result;

      result = App_CommProtocol_ParseByte(&s_usb_parser, data[index], &s_usb_rx_frame);
      if (result == APP_COMM_PARSE_FRAME_READY)
      {
        s_usb_frame_ready = 1U;
      }
      else if (result == APP_COMM_PARSE_CHECKSUM_ERROR)
      {
        s_usb_error_code = APP_COMM_ERROR_CODE_CHECKSUM;
        s_usb_error_ready = 1U;
      }
      else if (result == APP_COMM_PARSE_LENGTH_ERROR)
      {
        s_usb_error_code = APP_COMM_ERROR_CODE_LENGTH;
        s_usb_error_ready = 1U;
      }
    }
  }
}

void App_Uart5Slave_HandleUsbTxComplete(void)
{
  if ((s_usb_tx_in_flight != 0U) && (s_usb_tx_count > 0U))
  {
    s_usb_tx_head = (uint8_t)((s_usb_tx_head + 1U) % APP_UART5_SLAVE_USB_TX_QUEUE_DEPTH);
    s_usb_tx_count--;
    s_usb_tx_in_flight = 0U;
  }
}

/**
  * @brief UART 接收完成回调的业务处理入口。
  * @param huart 触发接收完成的 UART 句柄指针。
  * @retval None
  */
void App_Uart5Slave_HandleRxCplt(UART_HandleTypeDef *huart)
{
  if ((s_uart5 == NULL) || (huart == NULL) || (huart->Instance != UART5))
  {
    return;
  }

  if ((s_frame_ready == 0U) && (s_error_ready == 0U))
  {
    App_CommParseResult result;

    result = App_CommProtocol_ParseByte(&s_parser, s_rx_byte, &s_rx_frame);
    if (result == APP_COMM_PARSE_FRAME_READY)
    {
      s_frame_ready = 1U;
    }
    else if (result == APP_COMM_PARSE_CHECKSUM_ERROR)
    {
      s_error_code = APP_COMM_ERROR_CODE_CHECKSUM;
      s_error_ready = 1U;
    }
    else if (result == APP_COMM_PARSE_LENGTH_ERROR)
    {
      s_error_code = APP_COMM_ERROR_CODE_LENGTH;
      s_error_ready = 1U;
    }
  }

  /* 每处理完一个字节都重新打开 UART5 接收中断，持续解析主机帧。 */
  (void)HAL_UART_Receive_IT(s_uart5, &s_rx_byte, 1U);
}

/**
  * @brief HAL UART 接收完成公共回调函数。
  * @param huart 触发接收完成的 UART 句柄指针。
  * @retval None
  */
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
  /* HAL 公共回调分发到各用户模块，模块内部按串口实例自行过滤。 */
  App_Uart5Slave_HandleRxCplt(huart);
  App_UltrasonicManager_HandleRxCplt(huart);
}
