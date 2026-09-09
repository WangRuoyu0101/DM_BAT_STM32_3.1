# DM3.1 Git 历史恢复设计

日期：2026-07-22

## 目标

让当前 `DM3.1-BAT` 工作区继承相邻 `DM2.1_BAT` 的完整 Git 历史，并将远端
切换为：

```text
git@github.com:WangRuoyu0101/DM_BAT_STM32_3.0.git
```

## 现状

- `DM3.1-BAT` 当前没有 `.git`；
- 相邻 `DM2.1_BAT` 是干净的 Git 工作区，当前分支为 `main`；
- 旧仓库 `origin` 为 `git@github.com:WangRuoyu0101/DM_BAT_STM32.git`；
- 旧历史 HEAD 为 `216c8c8`。

## 执行方式

1. 将 `../DM2.1_BAT/.git` 完整复制到当前工作区，不修改旧工作区；
2. 验证当前仓库仍位于 `main`，且历史 HEAD 为 `216c8c8`；
3. 将 `origin` 的 fetch/push URL 都改为 DM3.1 新仓库；
4. 检查状态，确保构建目录、虚拟环境、缓存和临时文件不会进入提交；
5. 补充最小 `.gitignore`（仅在旧规则未覆盖当前生成物时）；
6. 将当前 DM3.1 源码、文档、测试和必要固件适配作为一个迁移提交提交到
   `main`；
7. 验证提交后的工作区状态和远端配置。

## 安全边界

- 不删除或修改 `../DM2.1_BAT`；
- 不使用 `git init` 创建断裂的新历史；
- 不执行 reset、强制 checkout、rebase 或 force push；
- 不提交 `.venv`、`__pycache__`、构建中间文件、`.DS_Store`、SDD 临时报告；
- 本步骤只建立本地提交，不自动 push；推送由用户另行确认。

## 完成标准

- `git log` 可追溯到 DM2.1 历史；
- `origin` 指向 DM3.1 新仓库；
- DM3.1 改动形成一个本地提交；
- `git status --short` 无未预期文件或改动。
