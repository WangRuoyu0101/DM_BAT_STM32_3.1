# DM3.1 Bootloader 防变砖升级设计

## 目标

- Bootloader 首次通过 SWD 写入后，第一版 App 必须能够通过 USB 上位机写入，不再依赖 SWD。
- App 擦除、写入或校验期间发生失败、复位或断电后，设备必须停留在 Bootloader，直到上位机重新完成一次正确升级。
- Bootloader 空闲时主动向上位机上报状态。

## Flash 布局

STM32F407VE 的 512 KiB Flash 按以下方式使用：

- Bootloader：`0x08000000–0x08007FFF`，Sector 0–1，共 32 KiB。
- App：`0x08008000–0x0805FFFF`，Sector 2–6，共 352 KiB。
- App 元数据：`0x08060000–0x0807FFFF`，Sector 7，共 128 KiB。

App 链接脚本和 Bootloader 返回的 `INFO.app_size` 都改为 352 KiB。上位机继续使用 `INFO` 返回值检查镜像大小，不另设固定容量。

## App 元数据与有效性

Sector 7 起始位置保存 20 字节小端记录：

- 偏移 0：`magic = 0x41334D44`（字节序列 `DM3A`），有效标志，最后写入。
- 偏移 4：`format_version = 1`。
- 偏移 8：`image_size`，App 镜像字节数。
- 偏移 12：`image_crc32`，App 镜像 CRC32。
- 偏移 16：`record_crc32`，偏移 4–15 三个字段的 CRC32。

镜像和元数据都复用现有反射式 CRC32 算法。Bootloader 功能版本更新为 `0x00020000`。

Bootloader 只在以下条件全部成立时认为 App 有效：

1. `magic` 和格式版本正确；
2. 元数据 CRC32 正确；
3. 镜像长度非零且未超出 App 区；
4. 栈顶位于 STM32 SRAM；
5. 复位入口 Thumb 位为 1，去掉 Thumb 位后的地址位于 App 镜像范围；
6. App 全镜像 CRC32 与元数据一致。

没有元数据的既有 App 不自动接纳。若先通过 SWD 写入 App、再写入 Bootloader，设备会保持在 Bootloader，必须使用上位机重新写入一次 App。仅凭向量表不能可靠证明整个 App 完整，因此不提供“信任旧 App”开关。

## 升级状态机

状态包括：

- `WAITING`：等待升级命令。
- `RECEIVING`：App 已擦除，正在接收镜像。
- `VERIFIED`：镜像和元数据已验证，等待 `JUMP`。
- `ERROR`：升级命令失败；是否仍有有效 App 由 `app_valid` 单独表示。

命令处理规则：

1. `START` 只校验并保存镜像长度与 CRC，不改变旧 App 或元数据。
2. `ERASE` 先把有效元数据的 `magic` 写成 0 并回读确认；元数据原本无效时无需重复写入。确认无效后擦除 App 使用的 Sector 2–6。
3. 元数据未成功失效时不得开始擦除 App。
4. `WRITE` 继续要求偏移连续、范围合法，并在成功后更新已接收字节数。
5. `VERIFY` 只在完整接收后执行。App CRC 和向量表正确后，擦除 Sector 7，先写入并回读其他字段，最后写入 `magic`，再完整校验元数据。
6. `VERIFY` 只有在元数据提交成功后才返回成功，当前会话仍停留在 `VERIFIED`，等待上位机显式发送 `JUMP`。
7. `JUMP` 必须重新执行完整 App 有效性检查，不能只检查向量表。
8. `VERIFY` 成功后、`JUMP` 前若复位或断电，下次启动允许进入已验证 App。
9. 元数据确认失效后的任何错误都进入 `ERROR`，且 App 保持无效。若元数据失效本身失败，则不得擦除 App，旧 App 仍可保持有效。新的 `START` 可重新开始升级，但只有新的 `VERIFY` 成功后 App 才恢复有效。

## 上电行为

- App 无效：立即启用 USB CDC，保持 Bootloader，不设自动退出超时。
- App 有效且 App 请求进入 Bootloader：启用 USB CDC，保持 Bootloader。
- App 有效且无升级请求：保留现有 2 秒握手窗口；没有握手则启动 App。
- `RESET` 不绕过有效性检查。重启后仍按上述规则决定是否进入 App。

## Bootloader 状态上报

新增主动帧 `BOOTLOADER_STATUS (0x92)`，载荷为：

- `state`：`WAITING=0 / RECEIVING=1 / VERIFIED=2 / ERROR=3`。
- `app_valid`：缓存的 App 有效状态。
- `last_error`：最近一次 Bootloader 错误码，复位后为 0。
- `reserved`：固定为 0。
- `received_bytes`：当前会话已成功写入的字节数，32 位小端。

USB CDC 空闲时每 1 秒发送一次状态帧；状态变化后立即发送一次。正在执行 `ERASE`、单次 `WRITE`、`VERIFY` 或元数据 Flash 操作时不发送，操作结束并发送命令响应后再上报。这样 `RECEIVING` 可在命令间空闲期上报，但不会与 Flash 临界操作并发。

`app_valid` 在启动检查、元数据失效和元数据提交时更新，不在每次心跳中重复计算整镜像 CRC。

## 上位机适配

Python Bootloader 协议层增加状态帧解析。等待 `INFO` 或 `ACK` 时遇到 `0x92`，先分发状态回调并继续等待原命令响应，避免主动帧打乱升级顺序。

Qt 连接设备时使用现有 `HELLO` 做最小模式探测：收到 Bootloader `INFO` 或主动状态帧时进入 `BOOTLOADER` 状态；否则按现有 App 模式连接。Bootloader 模式下周期读取状态帧，并在固件升级页显示状态、App 有效性、最近错误和接收字节数。

首次写入 App 时不勾选“从运行态请求进入 bootloader”，直接执行 `HELLO → START → ERASE → WRITE → VERIFY → JUMP`。升级失败后保留 Bootloader 模式和重试入口，不要求重连 App。

## 失败与断电保证

- `ERASE` 前断电：旧元数据和旧 App 未被破坏，仍可启动旧 App。
- 元数据失效后至新元数据提交前断电：App 无效，重启后永久停留 Bootloader。
- 元数据擦除或写入期间断电：`magic` 尚未最后提交，重启后永久停留 Bootloader。
- CRC、向量表、Flash 写入或元数据校验失败：返回错误、进入 `ERROR`，不得执行 `JUMP`。
- 有效元数据发生损坏，或 App 内容与 CRC 不一致：启动检查失败，进入 Bootloader。

## 验证

自动测试至少覆盖：

- 新 Flash 布局、App 链接长度和 `INFO.app_size` 一致。
- 元数据缺失、字段损坏、CRC 不匹配或向量表非法时 App 无效。
- `START` 不使旧 App 失效；`ERASE` 必须先使元数据失效。
- 写入不完整或 CRC 错误时不能提交元数据。
- `VERIFY` 成功时最后提交 `magic`，`JUMP` 使用完整有效性检查。
- Python 客户端等待响应时能跳过并分发主动状态帧。
- Qt 能识别 Bootloader、显示状态并在失败后允许直接重试。

硬件验收至少覆盖：

1. 只用 SWD 写入 Bootloader，随后通过 Qt 写入第一版 App。
2. 从运行中 App 请求进入 Bootloader 并成功升级。
3. 分别在元数据失效、各 Sector 擦除、多个写入偏移、校验及元数据提交阶段断电，重启后均停留 Bootloader。
4. 每种失败后重新发起完整升级，成功后可以 `JUMP`。
5. `VERIFY` 成功但未发送 `JUMP` 时断电，重启后可以启动 App。
6. Bootloader 空闲 1 秒状态心跳、状态变化上报和 Qt 展示正确，且升级命令响应不被状态帧干扰。
