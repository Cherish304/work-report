# Windows 兼容说明（未真机验收）

macOS 首发已验证；本文件是 Windows 后续验收与安装路径，不保证当前端到端已可用。使用原生 PowerShell、Python 3.9+ 和 Windows 版 `dws.exe`，不照搬 macOS 命令。

| macOS | Windows PowerShell |
|---|---|
| `python3` | 通常 `py -3`，以本机安装为准 |
| `command -v dws` | `Get-Command dws` |
| `dws` Darwin arm64/amd64 | `dws.exe` Windows 适配架构 |
| `install.sh` | `install.ps1` |
| `export PATH=...` | `$env:Path`，或 Windows 用户环境设置 |
| Bash 的反斜杠续行 | PowerShell 不使用反斜杠续行；示例优先单行 |
| `< file` stdin 重定向 | 不照搬，使用本项目 Python UTF-8 stdin 适配 |
| chmod 0600 | 用户 ACL，chmod 不等于 Windows 访问控制 |

先检查：

```powershell
py -3 --version
Get-Command dws
dws --version
```

没有 DWS 时审阅[官方 PowerShell 安装器](https://github.com/DingTalk-Real-AI/dingtalk-workspace-cli/blob/main/scripts/install.ps1)后安装，或按钉钉插件提供的流程执行。不要通过降低全局 ExecutionPolicy 来绕过安装限制。安装路径以官方安装器实际输出为准，安装后重新打开终端；非 PATH 路径可在配置中指定 `dws_path`。

```powershell
irm https://raw.githubusercontent.com/DingTalk-Real-AI/dingtalk-workspace-cli/main/scripts/install.ps1 | iex
dws auth login --device
```

上面的安装命令会下载并执行远程代码；本项目不自动运行。

仓库根目录下可演练同一个 Python 安装器：

```powershell
py -3 scripts/install.py --dry-run
py -3 scripts/install.py
py -3 runtime/work_report.py doctor
```

缺少 IANA 时区数据库时，在当前 Python 环境安装 `tzdata`。不要使用 `Get-Content ... | dws` 提交中文 JSON，尤其是 Windows PowerShell 5.1；本项目核心用 UTF-8 字节和参数数组调用 DWS，避免 BOM、默认编码及含空格路径的问题。

WSL 和原生 Windows 是两套用户目录、凭证和 Codex 数据环境，不假定可共享记忆或登录态。先以原生 Windows 路径验收，不把 WSL 结果当 Windows 真机结果。

正式发布前必须验收：原生安装、dws.exe PATH/显式路径、登录授权、中文字段 dry-run、取消/修改心跳、状态重复提交保护、用户 ACL，以及电脑休眠/应用关闭后的任务行为。
