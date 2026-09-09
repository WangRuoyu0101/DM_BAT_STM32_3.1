# 中文注释与工程文档完善实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变运行逻辑的前提下完成项目自研代码的中文注释，并建立可从仓库根目录直接操作的三级中文 README 和审核报告。

**Architecture:** 按 STM32 应用、STM32 Bootloader/基础设施、Jetson 运行代码、Jetson 工具与测试、三级 README 五个边界分批修改。每批修改后运行对应测试并创建本地提交，最后执行全量验证和需求逐项审计；所有提交在用户审核前只保留本地。

**Tech Stack:** STM32F407、C、ARM GCC、Make、OpenOCD、Python 3、ROS2 Foxy、ament_python、Bash、Markdown、unittest。

## Global Constraints

- 基线备份为 GitHub `main` 提交 `72b7fc3`；本计划执行期间不得再次推送 GitHub。
- 只修改项目自有注释和文档，不改变固件、协议、脚本或 Jetson 程序行为。
- 注释和 README 使用中文；代码标识符、协议名、芯片名、工具名和许可证可保留英文。
- 不修改 `STM32/Drivers/`、`STM32/Middlewares/`、工具链、构建产物和供应商样板代码。
- 所有 Mac 命令默认从 `DM2.1_BAT` 根目录执行；STM32 目标统一使用 `make -C STM32 ...`。
- Jetson 目录切换命令必须明确标注为“在 Jetson 上执行”。
- 工作报告通过用户审核前，只允许本地提交，不允许推送。

---

### Task 1: 建立验证基线和注释审计清单

**Files:**
- Reference: `docs/superpowers/specs/2026-07-11-chinese-comments-readme-design.md`
- Reference: `STM32/tests/test_comm_protocol_frame.py`
- Reference: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_protocol.py`

**Interfaces:**
- Consumes: GitHub 备份提交 `72b7fc3` 和当前本地设计提交。
- Produces: 后续各任务使用的测试基线和允许修改范围。

- [ ] **Step 1: 确认工作区与远端基线**

Run:

```bash
git status --short --branch
git rev-list --left-right --count main...origin/main
```

Expected: 工作区干净；本地仅领先已提交的设计/计划，不落后远端。

- [ ] **Step 2: 运行 STM32 结构测试基线**

Run:

```bash
python3 -m unittest discover STM32/tests -v
```

Expected: 48 项测试全部通过。

- [ ] **Step 3: 运行 Jetson 包测试基线**

Run:

```bash
cd Linux_ROS_WS/src/stm32_jetson_serial_comm && python3 -m unittest discover -s tests -v
```

Expected: 83 项测试全部通过。此处是验证命令，不进入 README 的 Mac 快捷命令示例。

### Task 2: 补全 STM32 主应用中文注释

**Files:**
- Modify: `STM32/Core/Inc/app_bootloader_request.h`
- Modify: `STM32/Core/Inc/app_comm_protocol.h`
- Modify: `STM32/Core/Inc/app_cs1237.h`
- Modify: `STM32/Core/Inc/app_flash_layout.h`
- Modify: `STM32/Core/Inc/app_periodic_tick.h`
- Modify: `STM32/Core/Inc/app_relay_control.h`
- Modify: `STM32/Core/Inc/app_rtk_bridge.h`
- Modify: `STM32/Core/Inc/app_status_led.h`
- Modify: `STM32/Core/Inc/app_uart5_slave.h`
- Modify: `STM32/Core/Inc/app_ultrasonic_manager.h`
- Modify: `STM32/Core/Inc/app_ultrasonic_protocol.h`
- Modify: `STM32/Core/Src/app_bootloader_request.c`
- Modify: `STM32/Core/Src/app_comm_protocol.c`
- Modify: `STM32/Core/Src/app_cs1237.c`
- Modify: `STM32/Core/Src/app_periodic_tick.c`
- Modify: `STM32/Core/Src/app_relay_control.c`
- Modify: `STM32/Core/Src/app_rtk_bridge.c`
- Modify: `STM32/Core/Src/app_status_led.c`
- Modify: `STM32/Core/Src/app_uart5_slave.c`
- Modify: `STM32/Core/Src/app_ultrasonic_manager.c`
- Modify: `STM32/Core/Src/app_ultrasonic_protocol.c`
- Modify: `STM32/Core/Src/main.c`
- Modify: `STM32/Core/Src/stm32f4xx_it.c`
- Modify: `STM32/Core/Src/stm32f4xx_hal_msp.c`

**Interfaces:**
- Consumes: 现有 `App_*` 公共 API、HAL 回调和 UART5/USB CDC 协议。
- Produces: 模块职责、API、状态机、中断/主循环协作、硬件约束均有中文说明的 STM32 主应用源码。

- [ ] **Step 1: 为头文件补充模块和公共接口说明**

Apply these responsibility descriptions without changing declarations:

```text
app_comm_protocol：AA 55 帧格式、CRC8、逐字节解析和业务 payload 编解码。
app_cs1237：PD11/PD14 GPIO 时序、通道配置、快照有效性和错误码。
app_rtk_bridge：USART6 环形缓冲、分片写入、溢出策略和累计诊断。
app_uart5_slave：UART5/USB CDC 共用协议、ISR 到主循环移交和响应队列。
app_ultrasonic_manager：三路传感器错峰调度、超时和状态位图。
app_bootloader_request：RTC 备份寄存器中的一次性跳转标志。
```

- [ ] **Step 2: 为源文件补充关键实现原因**

Add Chinese comments specifically around:

```text
CRC 状态机重同步；CS1237 24 位符号扩展与配置回读；RTK 满缓冲时保留旧数据；
UART 回调只搬运数据、主循环负责阻塞发送；超声波错峰触发；tick 无符号回绕；
应用请求 Bootloader 后的应答、LED 快闪和延时复位。
```

- [ ] **Step 3: 只在 CubeMX 自定义区域补充说明**

Keep generated function bodies unchanged. In `main.c`, `stm32f4xx_it.c` and `stm32f4xx_hal_msp.c`, comment only project initialization order, UART6/ADC GPIO additions, interrupt dispatch and main-loop scheduling.

- [ ] **Step 4: 检查差异并运行 STM32 测试**

Run:

```bash
git diff --check
git diff -- STM32/Core
python3 -m unittest discover STM32/tests -v
```

Expected: 差异仅为注释；48 项测试通过。

- [ ] **Step 5: 创建本地提交**

```bash
git add STM32/Core
git commit -m "docs: complete Chinese comments for STM32 application"
```

### Task 3: 补全 STM32 Bootloader、USB、自定义构建和测试注释

**Files:**
- Modify: `STM32/Bootloader/Core/Inc/bootloader_config.h`
- Modify: `STM32/Bootloader/Core/Inc/bootloader_flash.h`
- Modify: `STM32/Bootloader/Core/Inc/bootloader_jump.h`
- Modify: `STM32/Bootloader/Core/Inc/bootloader_protocol.h`
- Modify: `STM32/Bootloader/Core/Inc/bootloader_usb_cdc.h`
- Modify: `STM32/Bootloader/Core/Src/bootloader_flash.c`
- Modify: `STM32/Bootloader/Core/Src/bootloader_jump.c`
- Modify: `STM32/Bootloader/Core/Src/bootloader_protocol.c`
- Modify: `STM32/Bootloader/Core/Src/bootloader_usb_cdc.c`
- Modify: `STM32/Bootloader/Core/Src/main.c`
- Modify: `STM32/USB_DEVICE/App/usbd_cdc_if.c`
- Modify: `STM32/Makefile`
- Modify: `STM32/STM32F407XX_APP_FLASH.ld`
- Modify: `STM32/STM32F407XX_BOOT_FLASH.ld`
- Modify: `STM32/tests/test_comm_protocol_frame.py`
- Modify: `STM32/tests/test_cs1237_driver.py`
- Modify: `STM32/tests/test_cs1237_protocol.py`
- Modify: `STM32/tests/test_relay_control.py`
- Modify: `STM32/tests/test_rtk_bridge.py`
- Modify: `STM32/tests/test_rtk_protocol.py`
- Modify: `STM32/tests/test_tim6_periodic_tick.py`
- Modify: `STM32/tests/test_uart5_bootloader.py`
- Modify: `STM32/tests/test_uart5_protocol_readme.py`
- Modify: `STM32/tests/test_uart5_slave_status.py`
- Modify: `STM32/tests/test_ultrasonic_manager.py`
- Modify: `STM32/tests/test_ultrasonic_protocol.py`
- Modify: `STM32/tests/test_usb_cdc_echo.py`

**Interfaces:**
- Consumes: Flash 分区 `0x08000000/0x08008000`、USB CDC/UART5 Bootloader 协议和 Make 目标。
- Produces: Bootloader 安全边界、升级状态机、USB 复枚举、自定义构建目标和测试意图的中文说明。

- [ ] **Step 1: 注释 Bootloader 安全与协议边界**

Document in Chinese:

```text
应用区边界检查；擦除扇区选择；写入序号/偏移校验；CRC32 校验；
栈顶和复位向量合法性；HELLO→START→ERASE→WRITE→VERIFY→JUMP；
USB CDC 与 UART5 共用解析器；一次性应用跳转标志。
```

- [ ] **Step 2: 注释 USB CDC 自定义逻辑**

In `usbd_cdc_if.c`, comment only the application-protocol feed, Bootloader feed, transmit-complete callback and forced USB re-enumeration behavior. Preserve ST-generated comments and code unchanged.

- [ ] **Step 3: 中文化自定义构建说明和测试意图**

Translate project-owned Makefile/linker comments and add one Chinese module docstring to each listed test file describing the verified behavior. Do not translate Python identifiers or assertion strings required by tests.

- [ ] **Step 4: 检查并运行 STM32 测试**

```bash
git diff --check
python3 -m unittest discover STM32/tests -v
```

Expected: 48 项测试通过。

- [ ] **Step 5: 创建本地提交**

```bash
git add STM32/Bootloader STM32/USB_DEVICE/App/usbd_cdc_if.c STM32/Makefile STM32/STM32F407XX_APP_FLASH.ld STM32/STM32F407XX_BOOT_FLASH.ld STM32/tests
git commit -m "docs: complete Chinese comments for STM32 bootloader and tests"
```

### Task 4: 补全 Jetson 运行代码中文注释

**Files:**
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/__init__.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/bootloader.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/bootloader_cli.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/cs1237.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/gpio_cli.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/messages.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/protocol.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/rtk_bridge.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/rtk_cli.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/serial_driver.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/serial_host.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/serial_link_cli.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/serial_node_core.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/stm32_serial_node.py`

**Interfaces:**
- Consumes: STM32 应用协议、Bootloader 协议、pyserial、ROS2 topic/service 和 CS1237 标定文件。
- Produces: 每个模块、公共类/函数和非直观数据流均有中文说明的 Jetson 运行代码。

- [ ] **Step 1: 补充模块和公共 API 文档字符串**

Use concise Chinese docstrings describing protocol packing/parsing, serial ownership, request/response matching, calibration persistence, RTK fragmentation, CLI responsibilities, polling and ROS2 publication.

- [ ] **Step 2: 补充关键算法说明**

Comment these reasons in Chinese:

```text
CRC8/CRC32 范围；解析器垃圾字节重同步；Bootloader 独立擦除超时；
CS1237 临时文件加 os.replace 原子保存；RTK 249/30 字节分片限制；
串口锁避免响应交叉；轮询超时后的 link_ok 状态；序号 8 位回绕。
```

- [ ] **Step 3: 检查并运行 Jetson 单元测试**

Run:

```bash
git diff --check
cd Linux_ROS_WS/src/stm32_jetson_serial_comm && python3 -m unittest discover -s tests -v
```

Expected: 83 项测试通过。

- [ ] **Step 4: 创建本地提交**

```bash
git add Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm
git commit -m "docs: complete Chinese comments for Jetson runtime"
```

### Task 5: 补全 Jetson 脚本、启动、包配置和测试注释

**Files:**
- Modify: `Linux_ROS_WS/scripts/sync_to_jetson.sh`
- Modify: `Linux_ROS_WS/scripts/pull_from_jetson.sh`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/serial_link.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/launch/stm32_serial.launch.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/setup.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/package.xml`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_bootloader.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_cs1237.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_firmware_sync.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_gpio_cli.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_messages.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_protocol.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_rtk_bridge.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_rtk_cli.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_serial_driver.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_serial_host.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_serial_link.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_serial_node_core.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_setup_entry_points.py`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/test_stm32_serial_node_source.py`

**Interfaces:**
- Consumes: `REMOTE_HOST`、`REMOTE_WS`、ROS2 launch 参数、ament_python 安装入口。
- Produces: 同步删除语义、包入口、启动参数和测试意图均有中文说明的 Jetson 工具代码。

- [ ] **Step 1: 注释脚本和启动配置风险边界**

Explain that rsync `--delete` mirrors the source tree, excluded build/cache files are preserved from transfer, environment variables override the default Jetson, and launch defaults match `stm32_serial_node.py`.

- [ ] **Step 2: 注释测试模块**

Add a Chinese module docstring to each listed test file. Describe the behavior under test rather than restating individual assertions.

- [ ] **Step 3: 验证脚本和测试**

```bash
bash -n Linux_ROS_WS/scripts/sync_to_jetson.sh
bash -n Linux_ROS_WS/scripts/pull_from_jetson.sh
cd Linux_ROS_WS/src/stm32_jetson_serial_comm && python3 -m unittest discover -s tests -v
```

Expected: 两个脚本语法检查通过，83 项测试通过。

- [ ] **Step 4: 创建本地提交**

```bash
git add Linux_ROS_WS/scripts Linux_ROS_WS/src/stm32_jetson_serial_comm
git commit -m "docs: complete Chinese comments for Jetson tools and tests"
```

### Task 6: 新增仓库根 README

**Files:**
- Create: `README.md`
- Reference: `STM32/README.md`
- Reference: `Linux_ROS_WS/src/stm32_jetson_serial_comm/README.md`

**Interfaces:**
- Consumes: 两个子工程的真实 Make 目标、脚本路径、测试命令和部署流程。
- Produces: 整个 `DM2.1_BAT` 仓库的统一中文入口。

- [ ] **Step 1: 创建固定章节骨架**

Use exactly these top-level sections:

```markdown
# DM2.1_BAT 电源板与 Jetson 通信工程
## 工程概览
## 环境搭建
## 工程编译
## 代码烧录与部署
## 功能测试
## 二次开发手册
## 子工程文档与硬件资料
```

- [ ] **Step 2: 写入可直接执行的 Mac 快捷命令**

Include these root-relative commands with Chinese prerequisites and expected outputs:

```bash
make -C STM32 app
make -C STM32 bootloader
make -C STM32 clean
make -C STM32 flash
make -C STM32 erase
Linux_ROS_WS/scripts/sync_to_jetson.sh
Linux_ROS_WS/scripts/pull_from_jetson.sh
python3 -m unittest discover STM32/tests -v
python3 -m unittest discover -s Linux_ROS_WS/src/stm32_jetson_serial_comm/tests -t Linux_ROS_WS/src/stm32_jetson_serial_comm -v
```

- [ ] **Step 3: 写入开发手册与导航**

Describe the STM32 application/Bootloader split, USB CDC/UART5 protocol path, Jetson package role, feature-extension sequence, required tests, and links to both child READMEs and `STM32/docs/` hardware manuals.

- [ ] **Step 4: 检查并提交**

```bash
git diff --check README.md
git add README.md
git commit -m "docs: add repository development guide"
```

### Task 7: 重组并完善 STM32 README

**Files:**
- Modify: `STM32/README.md`

**Interfaces:**
- Consumes: `STM32/Makefile` 目标、链接脚本、应用/Bootloader 源码与现有协议说明。
- Produces: 严格按环境、编译、烧录、测试、接口顺序组织的 STM32 中文开发手册。

- [ ] **Step 1: 重组一级章节**

Use this exact order:

```markdown
# DM2.1_BAT STM32 工程说明
## 工程概览
## 环境搭建
## 工程编译
## 代码烧录
## 功能测试
## 二次开发接口
## 常见问题与参考资料
```

Move existing CS1237、UM982、Flash、UART5、USB CDC/Bootloader details under `二次开发接口` without deleting protocol values or hardware mappings.

- [ ] **Step 2: 修正所有 Mac 命令上下文**

Replace directory-changing OpenOCD examples with root-safe forms using `openocd -s STM32 ...` and `STM32/build/...` paths. Keep every `make` example in `make -C STM32 <target>` form.

- [ ] **Step 3: 完善测试与扩展步骤**

Document software unit tests, application/Bootloader builds, CMSIS-DAP flashing verification, USB CDC enumeration, UART5 fallback, sensor/RTK/ADC checks, and the file/test/README sequence for adding a new module or protocol frame.

- [ ] **Step 4: 运行 README 相关测试并提交**

```bash
python3 -m unittest STM32/tests/test_uart5_bootloader.py STM32/tests/test_uart5_protocol_readme.py -v
git diff --check STM32/README.md
git add STM32/README.md
git commit -m "docs: reorganize STM32 development guide"
```

Expected: README 结构测试通过。

### Task 8: 重组 Jetson README 与固件目录说明

**Files:**
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/README.md`
- Modify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/firmware/README.md`

**Interfaces:**
- Consumes: ROS2 包入口、同步脚本、Bootloader 客户端、topic/service 和测试命令。
- Produces: 严格按环境、编译、部署、测试、接口顺序组织的 Jetson 中文开发手册。

- [ ] **Step 1: 重组一级章节**

Use this exact order:

```markdown
# Jetson 与 STM32 通信工程说明
## 工程概览
## 环境搭建
## 工程编译
## 代码烧录与部署
## 功能测试
## 二次开发接口
## 常见问题与协议参考
```

- [ ] **Step 2: 区分 Mac 与 Jetson 命令**

Mac sync/pull/build commands remain root-relative. Commands using `cd ~/ros_ws`, `colcon`, `ros2 run`, `ros2 launch`, `ros2 topic` and `ros2 service` must be grouped under an explicit “Jetson 端执行” label.

- [ ] **Step 3: 完善二次开发接口**

Document module ownership, console entry registration, adding a protocol message, adding a ROS2 topic/service/parameter, CS1237 calibration, RTK bridge, GPIO channel, Bootloader upgrade and unit-test extension.

- [ ] **Step 4: 更新固件目录说明并提交**

Ensure `firmware/README.md` describes generation via `make -C STM32 app`, sync via `Linux_ROS_WS/scripts/sync_to_jetson.sh`, ignored generated binary policy, and Jetson-side Bootloader use.

```bash
git diff --check Linux_ROS_WS/src/stm32_jetson_serial_comm/README.md Linux_ROS_WS/src/stm32_jetson_serial_comm/firmware/README.md
git add Linux_ROS_WS/src/stm32_jetson_serial_comm/README.md Linux_ROS_WS/src/stm32_jetson_serial_comm/firmware/README.md
git commit -m "docs: reorganize Jetson development guide"
```

### Task 9: 全量验证、完成审计和工作报告

**Files:**
- Create: `docs/2026-07-11-chinese-comments-readme-work-report.md`
- Verify: `README.md`
- Verify: `STM32/README.md`
- Verify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/README.md`
- Verify: `Linux_ROS_WS/src/stm32_jetson_serial_comm/firmware/README.md`
- Verify: all files modified in Tasks 2–5.

**Interfaces:**
- Consumes: 所有本地注释和 README 提交、测试与构建输出。
- Produces: 可供用户审核的中文工作报告；不推送 GitHub。

- [ ] **Step 1: 执行静态审计**

```bash
git diff --check origin/main...HEAD
rg -n 'cd STM32' README.md STM32/README.md Linux_ROS_WS/src/stm32_jetson_serial_comm/README.md Linux_ROS_WS/src/stm32_jetson_serial_comm/firmware/README.md
rg -n '^## ' README.md STM32/README.md Linux_ROS_WS/src/stm32_jetson_serial_comm/README.md
```

Expected: 无空白错误；Mac 快捷命令不依赖进入 `STM32/`；一级章节符合设计顺序。

- [ ] **Step 2: 执行脚本与单元测试**

```bash
bash -n Linux_ROS_WS/scripts/sync_to_jetson.sh
bash -n Linux_ROS_WS/scripts/pull_from_jetson.sh
python3 -m unittest discover STM32/tests -v
python3 -m unittest discover -s Linux_ROS_WS/src/stm32_jetson_serial_comm/tests -t Linux_ROS_WS/src/stm32_jetson_serial_comm -v
```

Expected: Bash 语法检查通过；STM32 48 项、Jetson 83 项测试通过。

- [ ] **Step 3: 执行两套固件构建**

```bash
make -C STM32 clean
make -C STM32 app
make -C STM32 bootloader
```

Expected: 生成 Application 与 Bootloader 的 ELF/HEX/BIN。若工具链环境失败，报告原始命令、退出码和缺失组件。

- [ ] **Step 4: 逐项审计原始需求**

Record evidence for: GitHub baseline backup, all in-scope code comments, root README, both child README structures, root-relative Mac commands, Chinese language, test/build results, report presence, and no post-review GitHub push.

- [ ] **Step 5: 编写并提交工作报告**

The report must contain these exact sections:

```markdown
# 中文注释与 README 完善工作报告
## 审核结论摘要
## GitHub 基线备份
## 中文注释改动
## README 改动
## 验证结果
## 已知限制
## 本地提交清单
## 用户审核项
```

```bash
git add docs/2026-07-11-chinese-comments-readme-work-report.md docs/superpowers/plans/2026-07-11-chinese-comments-readme.md
git commit -m "docs: add documentation overhaul work report"
git status --short --branch
git rev-list --left-right --count main...origin/main
```

Expected: 工作区干净、本地领先远端、没有执行最终 push。

- [ ] **Step 6: 交付用户审核**

Provide links to the report and three README files. Wait for explicit user approval before running `git push origin main`.
