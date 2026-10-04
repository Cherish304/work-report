# Work Report

Summarize daily and weekly work reports through Codex.

在 Codex 中用可复用 Skill 汇总工作记录，预览后提交钉钉日报、周报。身份来自当前用户的钉钉登录态，仓库不包含作者姓名、个人机器路径、企业模板 ID 或实际工作记录。

## 安装与使用

- [macOS 安装手册](docs/install-macos.md)：首发支持；使用 Bash/zsh 和原生 macOS `dws`。
- [Windows 兼容说明](docs/install-windows.md)：PowerShell 与 `dws.exe` 适配已设计，尚未完成 Windows 真机验证，暂不宣称正式支持。
- [配置](docs/configuration.md)、[架构](docs/architecture.md)、[隐私与故障处理](docs/privacy-and-troubleshooting.md)。

克隆本仓库后，在仓库根目录运行：

```bash
bash scripts/install-macos.sh
```

安装不下载或执行第三方代码、不覆盖已有 Skill、不替用户登录，也不会创建定时任务或发送报告。安装后在 Codex 中使用：

```text
$daily-report 仅预览今天的日报
$weekly-report 汇总指定起止日期的工作，先预览
$work-report-schedules 创建工作日 18:30 日报、每周一 18:00 周报安排
```

默认必须明确回复“提交”才发送。可以主动配置“预览后 5 分钟无回复自动提交”；取消和修改始终优先，修改重新计时。只要求预览时绝不创建提交心跳。

## 数据与运行方式

日报使用统计期内的 Codex rollout summaries、已完成任务回合和钉钉工作消息；周报使用 summaries、已完成任务回合和同期钉钉日报。记忆缺失不代表没有工作，超时和分页未完成必须显示覆盖缺口。正文不重复日期标题。

Codex 模型负责理解和起草，Python 负责时间窗口、JSON、状态和哈希，DWS 负责钉钉接口。本项目本身没有独立后台服务，也不会读取完整会话文件或 Git 历史。

定时任务通过 Codex 提供的自动化能力创建，不直接写其内部配置。项目级本地任务要求电脑开机、桌面应用运行、选定项目仍然存在。见[官方说明](https://learn.chatgpt.com/docs/automations?surface=app)。

## 验证

```bash
python3 -m unittest discover -s tests -v
python3 scripts/install.py --dry-run
python3 runtime/work_report.py doctor
```

测试使用临时目录与 Mock，不发送真实钉钉日志。发布前应在目标平台验证安装、DWS 登录、动态模板、预览和取消，再由用户确认真实提交。

实际覆盖与未验证项目见[验证说明](docs/verification.md)。
