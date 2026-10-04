# macOS 安装

## 1. 准备环境

安装并登录可使用 Skills、任务读取和自动化能力的 Codex 桌面环境。准备 Python 3.9+、Git，以及适配本机 Apple Silicon / Intel 的 macOS DWS。需要的是 Darwin 二进制，不是 Linux 二进制。

```bash
python3 --version
git --version
command -v dws
dws --version
```

如果 DWS 已可用，不重复安装。没有时，可通过 DingTalk Workspace CLI 插件的安装流程安装，或审阅[官方安装脚本](https://github.com/DingTalk-Real-AI/dingtalk-workspace-cli/blob/main/scripts/install.sh)后执行：

```bash
curl -fsSL https://raw.githubusercontent.com/DingTalk-Real-AI/dingtalk-workspace-cli/main/scripts/install.sh | sh
```

该命令会下载并执行远程代码；本项目安装器不会自动执行它。官方默认目录为用户的 `.local/bin`。如果 PATH 找不到它，重新打开终端或配置 PATH；Python 运行核心也支持这个候选目录。

```bash
export PATH="$HOME/.local/bin:$PATH"
dws auth login --device
```

只在用户手机完成授权；凭证由 DWS 保存，不复制到仓库或配置文件。

## 2. 安装报告 Skills

克隆本仓库到自己选择的本地目录，在仓库根目录执行：

```bash
bash scripts/install-macos.sh --dry-run
bash scripts/install-macos.sh
```

目标为 `CODEX_HOME/skills`（默认用户 `.codex/skills`）。已有同名 Skill 会拒绝覆盖。如果确实要替换：

```bash
bash scripts/install-macos.sh --replace
```

替换前会把同名 Skill 移到用户数据目录下的备份；安装失败自动恢复。备份不上传，已有运行数据、配置和自动化不覆盖。

## 3. 自检及试运行

```bash
python3 runtime/work_report.py doctor
```

自检不回显用户姓名、token 或个人路径。缺少时区数据时在自己的 Python 环境安装 `tzdata` 后重试；自检不静默安装依赖。

新开一个 Codex 对话，先发送：

```text
$daily-report 仅预览今天的日报，不提交
```

确认来源覆盖及三字段正文，再要求“生成并提交日报”；明确回复“提交”才发送。默认不向任何额外接收人发送，不承诺“提交日志”等同于“私聊给自己”。接收范围以动态模板和组织配置为准。

## 4. 创建安排

```text
$work-report-schedules 创建工作日 18:30 日报、每周一 18:00 周报安排
```

该步骤由 Codex 自动化工具完成，先检查已有安排，避免重复。周报默认汇总上一完整工作周。要求“预览后 5 分钟未回复自动提交”时，需先明确开启配置选项。

本地项目级任务需要电脑开机、桌面应用运行、项目可访问；休眠、断网、未登录、权限不足或工具不可用可能导致失败。手动预览成功后再启用定时提交。不要设置绕过所有确认或全盘访问来解决安装问题。
