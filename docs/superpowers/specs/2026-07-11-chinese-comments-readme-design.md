# 中文注释与工程文档完善设计

## 目标

在不改变固件、通信协议和 Jetson 端运行行为的前提下，为项目自研代码补全有维护价值的中文注释，并建立根目录、STM32 子工程和 Linux/ROS2 子工程三级中文 README。文档必须覆盖环境搭建、工程编译、代码烧录或部署、功能测试、二次开发接口，并保证所有 Mac 端快捷命令都能从 `DM2.1_BAT` 仓库根目录直接执行。

## 已完成的基线备份

开始文档改造前，`main` 已推送到 GitHub，备份基线为提交 `72b7fc3`。后续注释和 README 改动只创建本地提交；工作报告经用户审核通过前不得再次推送 GitHub。

## 用户代码范围

### STM32 自研代码

- `STM32/Core/Inc/app_*.h` 与 `STM32/Core/Src/app_*.c`。
- `STM32/Bootloader/Core/Inc/bootloader_*.h` 与 `STM32/Bootloader/Core/Src/bootloader_*.c`。
- CubeMX 生成文件中的 `USER CODE` 区域，以及项目明确加入的初始化、调度、通信和中断分发逻辑。
- `STM32/USB_DEVICE/App/usbd_cdc_if.c` 中项目自定义的应用协议接收、发送完成和 USB 重枚举逻辑。
- 自定义链接分区、Makefile 构建/烧录目标和 `STM32/tests/` 中的项目测试代码。

### Jetson/ROS2 自研代码

- `Linux_ROS_WS/src/stm32_jetson_serial_comm/stm32_jetson_serial_comm/*.py`。
- `launch/*.py`、入口脚本、`setup.py` 和项目自定义包配置。
- `Linux_ROS_WS/scripts/*.sh` 中的同步与拉取逻辑。
- `Linux_ROS_WS/src/stm32_jetson_serial_comm/tests/*.py` 中的项目测试代码。

### 排除项

- `STM32/Drivers/`、`STM32/Middlewares/`、工具链、构建产物和二进制资料。
- CubeMX、ST USB 库、启动文件和系统模板中未被项目修改的供应商样板代码。
- `.ioc`、PDF、XLSX 等不能通过源码注释维护的文件。

## 中文注释规则

1. 模块开头说明职责、依赖关系和关键约束。
2. 对外函数或类说明用途、主要参数、返回值和错误条件。
3. 状态机、环形缓冲、协议帧、Flash 边界、中断与主循环协作、校准换算等非直观逻辑必须解释设计原因。
4. 测试文件说明所验证的行为；测试方法名和协议常量保持原有代码命名，不翻译标识符。
5. 项目自有英文说明性注释改为中文；协议名称、芯片名、工具名和代码标识符可保留英文。
6. 不逐行复述显而易见的赋值、循环和标准库调用，不修改供应商版权头或许可证文本。
7. 只改注释和文档；若发现代码缺陷，记录到工作报告，不借本任务修改运行逻辑。

## README 体系

### 根目录 `README.md`

作为整个仓库的统一入口，包含：

- STM32 固件工程和 Jetson ROS2 工程的职责、依赖和数据流。
- 目录结构、硬件链路、推荐开发顺序和首次部署流程。
- Mac 开发机环境、STM32 编译与烧录、Linux 工程同步与拉取。
- 两套单元测试入口和硬件功能验证清单。
- 面向二次开发的协议、模块、GPIO、ADC、RTK、Bootloader 和 ROS2 接口导航。
- 指向两个子工程 README 和硬件资料的链接。

### `STM32/README.md`

保留现有协议与硬件信息，按以下一级章节顺序重组：

1. 工程概览
2. 环境搭建
3. 工程编译
4. 代码烧录
5. 功能测试
6. 二次开发接口
7. 常见问题与参考资料

二次开发接口覆盖应用/Bootloader Flash 分区、UART5/USB CDC 应用协议、Bootloader 协议、GPIO、超声波、CS1237、UM982、周期任务和新增模块接入方法。

### `Linux_ROS_WS/src/stm32_jetson_serial_comm/README.md`

保留现有 Jetson 使用说明，按以下一级章节顺序重组：

1. 工程概览
2. 环境搭建
3. 工程编译
4. 代码烧录与部署
5. 功能测试
6. 二次开发接口
7. 常见问题与协议参考

“代码烧录与部署”同时说明 Mac 到 Jetson 的源码/固件同步，以及 Jetson 通过 Bootloader 更新 STM32 应用固件的完整流程。

### 其他 README

`firmware/README.md` 保持专项目录说明定位，统一中文表述，并确保构建、同步命令从仓库根目录执行。

## 命令约束

- 所有标注为 Mac 端执行的命令，默认当前目录是 `DM2.1_BAT`。
- STM32 命令使用 `make -C STM32 ...`，不得先执行 `cd STM32`。
- Linux 同步与拉取使用 `Linux_ROS_WS/scripts/sync_to_jetson.sh` 和 `Linux_ROS_WS/scripts/pull_from_jetson.sh`。
- Mac 本地单元测试使用完整的仓库相对路径。
- 只有明确标注“在 Jetson 上执行”的 ROS2/colcon 命令可以使用 `/home/jetson/ros_ws` 或 `~/ros_ws`。
- OpenOCD 直接命令若必须保留，使用 `-s STM32` 或完整的 `STM32/build/...` 路径，确保不改变当前目录。

## 验证设计

1. 使用 Git 差异确认没有非注释性的源码行为变化。
2. 搜索项目自有源码中的说明性英文注释，逐项确认已中文化或属于允许保留的技术名词、许可证和生成标记。
3. 搜索 README 中的 `cd STM32`、错误相对路径和 Mac 命令，确认根目录执行约束。
4. 运行 `bash -n` 检查同步脚本语法。
5. 运行 STM32 的 Python 结构测试和 Jetson 包单元测试。
6. 运行 STM32 Application 与 Bootloader 构建；若本机工具链缺失，记录准确失败命令和环境原因，不将其误报为通过。
7. 检查 README 内部链接、文件路径、Makefile 目标和 ROS2 入口与当前仓库一致。

## 提交与审核

- 设计、注释、README 可分成便于审阅的本地提交。
- 完成后生成中文工作报告，列出改动范围、文件统计、验证结果、已知限制和本地提交。
- 报告提交用户审核时保持 `origin/main` 不变。
- 只有用户明确审核通过后，才把最终本地提交推送到 GitHub。
