#ifndef APP_COMM_PROTOCOL_H
#define APP_COMM_PROTOCOL_H

#include <stddef.h>
#include <stdint.h>

/*
 * UART5 应用层二进制通信协议。
 * 帧格式：AA 55 + frame_id + length + payload + CRC8。
 * CRC8 计算范围为 frame_id、length 和 payload，帧头不参与校验。
 */
#define APP_COMM_FRAME_HEADER0 0xAAU
#define APP_COMM_FRAME_HEADER1 0x55U
#define APP_COMM_CRC8_POLY 0x07U
#define APP_COMM_FRAME_OVERHEAD 5U
#define APP_COMM_MAX_PAYLOAD_SIZE 250U

/* 主从通信帧 ID。 */
#define APP_COMM_FRAME_ID_STATUS_QUERY 0x01U
#define APP_COMM_FRAME_ID_GPIO_CONTROL_REQUEST 0x02U
#define APP_COMM_FRAME_ID_GPIO_STATUS_QUERY 0x03U
#define APP_COMM_FRAME_ID_ULTRASONIC_QUERY 0x04U
#define APP_COMM_FRAME_ID_BOOTLOADER_REQUEST 0x05U
#define APP_COMM_FRAME_ID_CS1237_QUERY 0x06U
#define APP_COMM_FRAME_ID_CS1237_CHANNEL_REQUEST 0x07U
#define APP_COMM_FRAME_ID_FAN_CONTROL_REQUEST 0x0AU
#define APP_COMM_FRAME_ID_BOARD_IO_QUERY 0x0BU
#define APP_COMM_FRAME_ID_RGB_SET_REQUEST 0x0CU
#define APP_COMM_FRAME_ID_RGB_QUERY 0x0DU
#define APP_COMM_FRAME_ID_STATUS_RESPONSE 0x81U
#define APP_COMM_FRAME_ID_GPIO_CONTROL_RESPONSE 0x82U
#define APP_COMM_FRAME_ID_GPIO_STATUS_RESPONSE 0x83U
#define APP_COMM_FRAME_ID_ULTRASONIC_RESPONSE 0x84U
#define APP_COMM_FRAME_ID_BOOTLOADER_RESPONSE 0x85U
#define APP_COMM_FRAME_ID_CS1237_RESPONSE 0x86U
#define APP_COMM_FRAME_ID_CS1237_CHANNEL_RESPONSE 0x87U
#define APP_COMM_FRAME_ID_FAN_CONTROL_RESPONSE 0x8AU
#define APP_COMM_FRAME_ID_BOARD_IO_RESPONSE 0x8BU
#define APP_COMM_FRAME_ID_RGB_SET_RESPONSE 0x8CU
#define APP_COMM_FRAME_ID_RGB_STATUS 0x8DU
#define APP_COMM_FRAME_ID_ERROR_RESPONSE 0xE1U

/* 通用错误响应码。 */
#define APP_COMM_ERROR_CODE_CMD 0x01U
#define APP_COMM_ERROR_CODE_CHECKSUM 0x02U
#define APP_COMM_ERROR_CODE_LENGTH 0x03U
#define APP_COMM_ERROR_CODE_AUTH 0x04U

/* GPIO 控制通道 ID。 */
#define APP_COMM_GPIO_CHANNEL_FLASH_CTR 0x01U
#define APP_COMM_GPIO_CHANNEL_LED 0x02U
#define APP_COMM_GPIO_CHANNEL_BEE 0x03U
#define APP_COMM_GPIO_CHANNEL_MOTOR 0x04U
#define APP_COMM_GPIO_CHANNEL_FLASH 0x05U
#define APP_COMM_GPIO_CHANNEL_SOUND 0x06U

/* GPIO 控制电平。 */
#define APP_COMM_GPIO_LEVEL_LOW 0x00U
#define APP_COMM_GPIO_LEVEL_HIGH 0x01U

/* GPIO 控制响应结果。 */
#define APP_COMM_CONTROL_RESULT_OK 0x00U
#define APP_COMM_CONTROL_RESULT_INVALID_CHANNEL 0x01U
#define APP_COMM_CONTROL_RESULT_INVALID_LEVEL 0x02U
#define APP_COMM_CONTROL_RESULT_LENGTH_ERROR 0x03U

typedef struct
{
  uint8_t frame_id;
  uint8_t length;
  uint8_t data[APP_COMM_MAX_PAYLOAD_SIZE];
} App_CommFrame;

typedef struct
{
  /* 主机请求序号，STM32 响应时原样回显。 */
  uint8_t seq;
} App_CommStatusQuery;

typedef struct
{
  /* seq + channel_id + level，对应 GPIO 控制请求 0x02。 */
  uint8_t seq;
  uint8_t channel_id;
  uint8_t level;
} App_CommGpioControl;

typedef struct
{
  /* 主机请求序号，STM32 响应 GPIO 状态时原样回显。 */
  uint8_t seq;
} App_CommGpioStatusQuery;

typedef struct
{
  /* 主机请求序号，STM32 响应超声波快照时原样回显。 */
  uint8_t seq;
} App_CommUltrasonicQuery;

typedef struct
{
  uint8_t seq;
} App_CommCS1237Query;

typedef struct
{
  uint8_t seq;
  uint8_t channel;
} App_CommCS1237ChannelRequest;

typedef struct
{
  uint8_t seq;
  uint8_t level;
} App_CommFanControl;

typedef struct
{
  uint8_t seq;
} App_CommBoardIOQuery;

typedef struct
{
  uint8_t seq;
  uint8_t red;
  uint8_t green;
  uint8_t blue;
  uint8_t brightness;
  uint8_t mode;
} App_CommRgbSet;

typedef struct
{
  uint8_t seq;
} App_CommRgbQuery;

typedef enum
{
  APP_COMM_PARSE_WAIT_HEADER0 = 0,
  APP_COMM_PARSE_WAIT_HEADER1,
  APP_COMM_PARSE_FRAME_ID,
  APP_COMM_PARSE_LENGTH,
  APP_COMM_PARSE_DATA,
  APP_COMM_PARSE_CHECKSUM
} App_CommParseState;

typedef enum
{
  APP_COMM_PARSE_NONE = 0,
  APP_COMM_PARSE_FRAME_READY,
  APP_COMM_PARSE_CHECKSUM_ERROR,
  APP_COMM_PARSE_LENGTH_ERROR
} App_CommParseResult;

typedef struct
{
  App_CommParseState state;
  uint8_t checksum;
  uint8_t data_index;
  App_CommFrame frame;
} App_CommParser;

void App_CommProtocol_InitParser(App_CommParser *parser);

/* 计算协议帧 CRC8；data 为 NULL 且 length 为 0 时表示空 payload。 */
uint8_t App_CommProtocol_Checksum(uint8_t frame_id, const uint8_t *data, uint8_t length);

/* 将 frame_id 和 payload 编码为完整 UART5 二进制帧。 */
size_t App_CommProtocol_Encode(
  uint8_t frame_id,
  const uint8_t *data,
  uint8_t length,
  uint8_t *output,
  size_t output_size);

/* 单字节流式解析 UART5 二进制帧，可在 UART RX 中断中逐字节调用。 */
App_CommParseResult App_CommProtocol_ParseByte(
  App_CommParser *parser,
  uint8_t byte,
  App_CommFrame *frame);

/* 以下 Decode 接口只解析 payload，不重新计算 CRC；调用前应确保帧已通过解析器校验。 */
uint8_t App_CommProtocol_DecodeStatusQuery(
  const App_CommFrame *frame,
  App_CommStatusQuery *query);
uint8_t App_CommProtocol_DecodeGpioControlRequest(
  const App_CommFrame *frame,
  App_CommGpioControl *control);
uint8_t App_CommProtocol_DecodeGpioStatusQuery(
  const App_CommFrame *frame,
  App_CommGpioStatusQuery *query);
uint8_t App_CommProtocol_DecodeUltrasonicQuery(
  const App_CommFrame *frame,
  App_CommUltrasonicQuery *query);
uint8_t App_CommProtocol_DecodeCS1237Query(
  const App_CommFrame *frame,
  App_CommCS1237Query *query);
uint8_t App_CommProtocol_DecodeCS1237ChannelRequest(
  const App_CommFrame *frame,
  App_CommCS1237ChannelRequest *request);
uint8_t App_CommProtocol_DecodeFanControlRequest(
  const App_CommFrame *frame,
  App_CommFanControl *control);
uint8_t App_CommProtocol_DecodeBoardIOQuery(
  const App_CommFrame *frame,
  App_CommBoardIOQuery *query);
uint8_t App_CommProtocol_DecodeRgbSetRequest(
  const App_CommFrame *frame,
  App_CommRgbSet *request);
uint8_t App_CommProtocol_DecodeRgbQuery(
  const App_CommFrame *frame,
  App_CommRgbQuery *query);

#endif /* APP_COMM_PROTOCOL_H */
