# 架构与边界

## 单一业务核心

```text
用户调用 / Codex 定时任务
  → daily-report / weekly-report Skill
  → Codex 模型收集允许的来源并起草
  → 共用 Python 核心：日期、载荷、状态、哈希
  → 当前任务预览及确认
  → DWS：提交钉钉日志、回读结果
```

- `skills/`：两个报告 Skill 和一个定时配置 Skill。命名与原有调用一致。
- `runtime/work_report.py`：唯一业务辅助模块；不调用模型、不内置调度器。
- `runtime/workflow.md`：两个报告共用的来源、归因、确认、去重及提交约束。
- `scripts/install.py`：跨平台、无第三方依赖的安装器，将核心与工作流复制到每个报告 Skill 的私有资源目录；仓库只维护一份核心。
- `scripts/install-macos.sh`：macOS 薄启动器；Windows 用 PowerShell 调用同一安装器。
- `config.example.json`：公开配置示例；实际配置和运行数据仅存当前用户的 Codex 数据目录。

## 平台适配

核心使用 Python 3.9+、`pathlib`、参数数组与 `subprocess.run(shell=False)`。JSON 输入使用 UTF-8 字节直接送到 DWS stdin，不依赖 shell 引号或 PowerShell 管道编码。macOS 查找 PATH 后尝试用户目录 `.local/bin/dws`；Windows 查找 `dws.exe` 后尝试 `.local/bin/dws.exe`，其他目录显式配置，不假定某个安装路径。

`dws` 安装器、系统架构和二进制在两平台不同，业务参数以本机 schema/help 为准。macOS 是 Darwin，不能使用 Linux release；Windows 不执行 `.sh`、`chmod` 或 Bash 重定向。

状态根为 `CODEX_HOME/work-report/`，未指定 `CODEX_HOME` 时为当前用户 `.codex/work-report/`。每个报告类型隔离状态。权限在 Unix 上设为目录 0700、文件 0600；Windows 需要用户 ACL，不能把 chmod 当作安全保证。

## 提交安全

待确认 → 提交中 → 已提交；异常时进入“提交结果未知”，不得自动重试。取消、失败、未知和已提交状态不能通过替换草稿重新激活。修改只允许替换待确认草稿，重新计算哈希及完整等待时间。状态变更和提交使用同一独占锁，避免两个心跳重复提交。

代码验证本地状态、确认模式、等待时间和哈希；Skill 必须检查预览后的用户回复、当前模板、身份与远端去重。这些语义检查不能由脚本猜测。没有来源、身份、模板或确认工具时降级为预览，不绕过检查。

## 首发范围

优先完成 macOS 本地安装与离线测试，不替换作者已安装的个人 Skill，不变更原有定时任务，不测试真实提交。Windows 只有核心兼容设计和 Mock 覆盖，正式支持须 Windows 真机验收。
