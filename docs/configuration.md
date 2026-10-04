# 配置

实际配置位于 `CODEX_HOME/work-report/config.json`；未设置 `CODEX_HOME` 时使用当前用户 `.codex`。安装器首次创建它，已有配置不覆盖。仓库中的 `config.example.json` 不含身份、凭证或企业数据。

| 配置 | 默认值 | 含义 |
|---|---|---|
| timezone | Asia/Shanghai | 统计与安排的时区 |
| auto_submit | false | 必须主动开启才允许超时自动提交 |
| confirmation_minutes | 5 | 自动提交完整等待时间，不允许少于 5 分钟 |
| dws_path | null | PATH 优先；找不到时允许显式配置原生 DWS 可执行文件 |
| daily_time | 18:30 | 工作日日报截止和默认安排时间 |
| weekly_day | MO | 默认每周一 |
| weekly_time | 18:00 | 周报安排时间 |
| weekly_mode | previous_workweek | 定时汇总上一完整周一到周五 |
| daily_template_name / weekly_template_name | 日报 / 周报 | 动态读取当前组织模板，不内置模板 ID |

`weekly_day` 可设 MO/TU/WE/TH/FR/SA/SU。周五安排并汇总本周时将 `weekly_mode` 设为 `current_workweek`；不要把上一完整周模式误当本周。

安装时明确开启自动提交：

```bash
bash scripts/install-macos.sh --auto-submit
```

此选项只用于首次创建配置；配置已存在时不覆盖。重新配置可要求 Codex 编辑自己的运行配置，随后用 `doctor` 检查，并显式要求更新定时任务。修改配置不自动创建或更新安排。

手动报告默认到调用时刻，定时日报固定到配置的当日截止时间，即使任务延迟启动也不扩大窗口；日期范围优先使用用户明确指定值。
