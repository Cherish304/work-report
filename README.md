# Work Report

**把分散的工作记录，整理成先预览、再提交的钉钉日报与周报。**

在 Codex 中调用 Skill，汇总工作摘要与钉钉记录；核对正文后再发送。支持指定日期、取消与修改，以及可选的定时安排。

<p>
  <a href="#快速开始">快速开始</a> ·
  <a href="docs/install-macos.md">macOS 安装</a> ·
  <a href="docs/install-windows.md">Windows 兼容说明</a> ·
  <a href="docs/configuration.md">配置</a>
</p>

> 默认需要明确回复“提交”才发送。macOS 为首发验证平台；Windows 尚未完成真机验收。

## 先看一次调用

安装后，在 Codex 中发送：

```text
$daily-report 仅预览今天的日报，不提交
```

预览包含 **今日完成工作、未完成工作、需协调工作**，以及来源覆盖情况。先看成果与缺口，再决定是否提交；只要求预览不会创建提交心跳。

周报也可以指定范围：

```text
$weekly-report 汇总 2026-07-27 至 2026-07-31 的工作，仅预览
```

周报按 **本周完成工作、本周工作总结、下周工作计划、需协调与帮助** 四字段组织，不在正文重复日期标题，也不虚构计划或完成情况。

## 快速开始

### 1. 准备环境

需要可使用 Skills 的 Codex 环境、Python 3.9+，以及已登录的原生 [DingTalk Workspace CLI（DWS）](https://github.com/DingTalk-Real-AI/dingtalk-workspace-cli)。

macOS 使用 Bash/zsh 与 Darwin 版 `dws`；Windows 使用 PowerShell 与 `dws.exe`。安装与认证步骤分别见 [macOS 手册](docs/install-macos.md)和 [Windows 说明](docs/install-windows.md)。

### 2. 安装三个 Skill

克隆仓库后，在仓库根目录运行：

```bash
bash scripts/install-macos.sh
```

安装 **daily-report、weekly-report、work-report-schedules**。安装器不下载第三方代码，不替用户登录，不创建定时任务，也不发送报告。已有同名 Skill 会停止安装；如需备份后替换，见[安装手册](docs/install-macos.md#2-安装报告-skills)。

### 3. 新开对话，先预览

```text
$daily-report 仅预览今天的日报，不提交
```

确认来源覆盖和正文后，可在新的生成请求中明确要求“生成并提交日报”。完整预览后，回复“提交”才会发送。

## 从记录到报告

**工作记录 → Codex 归纳 → 三／四字段预览 → 用户确认 → DWS 提交与回读。**

| 来源 | 日报 | 周报 |
|---|---|---|
| Codex 工作摘要（rollout summaries） | 当日摘要 | 统计期摘要 |
| Codex 已完成回合 | 补充尚未生成的摘要 | 补充尚未生成的摘要 |
| 钉钉记录 | 同期工作聊天文本 | 同期已发出的日报 |

Codex 负责理解与起草；Python 核心负责时间窗口、载荷、状态和哈希；DWS 负责钉钉接口。本项目不提供独立后台服务，不读取完整会话文件或 Git 历史。摘要缺失、接口超时或分页未完成会标为覆盖缺口，而不是当作没有工作。

## 发送由你决定

- **提交**：确认当前预览，检查状态、模板与重复报告后发送。
- **取消**：停止本次提交。
- **修改**：更新正文、重新预览；启用自动提交时重新计时。

如需“预览后至少 5 分钟无回复自动提交”，首次安装时主动开启：

```bash
bash scripts/install-macos.sh --auto-submit
```

已有配置不会被此参数覆盖；后续修改见[配置说明](docs/configuration.md)。身份、模板、去重或用户回复不明确时不自动提交；提交超时记为“结果未知”，不会自动重试。

### 可选：安排定时报告

```text
$work-report-schedules 创建工作日 18:30 日报、每周一 18:00 周报安排
```

默认时区为 **Asia/Shanghai**，周报汇总**上一完整工作周的周一至周五**。时间与统计模式均可配置，安装本身不会创建安排。

安排由 Codex 的自动化能力执行。项目级本地任务需要电脑开机、桌面应用运行、所选项目仍可访问；不是关机后仍能运行的云服务。[官方定时任务说明](https://learn.chatgpt.com/docs/automations?surface=app)

## 隐私与验证边界

公开代码不包含个人姓名、机器路径、凭证、企业模板 ID 或实际工作记录。草稿、状态与备份保存在当前用户的数据目录，使用钉钉当前登录态和组织模板，不额外指定接收人。

**这不等于“数据从不离开本机”**：工作记录会进入当前 Codex 模型上下文，经确认的正文会发送到钉钉；访问与接收范围由组织权限决定。

macOS 已做隔离安装、离线单元测试和原生 DWS 中文 stdin dry-run。Windows 目前有兼容设计与 CI 配置，不能将它们视为真机端到端已验证。

```bash
python3 -m unittest discover -s tests -v
python3 runtime/work_report.py doctor
```

测试使用临时目录、合成数据与 Mock；本机有 DWS 时只做 dry-run，不发送真实报告。完整覆盖与待验收项目见[验证说明](docs/verification.md)。

## 继续阅读

- [macOS 安装](docs/install-macos.md) / [Windows 兼容说明](docs/install-windows.md)
- [配置与定时周期](docs/configuration.md)
- [架构与执行边界](docs/architecture.md)
- [隐私与故障处理](docs/privacy-and-troubleshooting.md)

## License

[Apache-2.0](LICENSE)
