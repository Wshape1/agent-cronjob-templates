# Agent CronJobs Template

定时任务模板集合，包含数据采集脚本和 Agent Prompt。

## 包含任务

| 任务 | 说明 |
|------|------|
| [financial_news](financial_news/) | 每日财经新闻简报 — 22 个数据源，TF-IDF + AI 语义精筛，输出 Top 10 |
| [github_trending](github_trending/) | GitHub Trending 每日简报 — 近 24 小时 Top 10 热门仓库 |

## 快速开始

把下面这段 prompt 直接发给 Agent：

```
从 github.com/wshape1/agent-cronjob-templates 克隆仓库（备用 gitee.com/wshape1/agent-cronjob-templates ），帮我安装其中一个 CronJob，阅读对应目录的 README 完成配置。
```

或者手动：

```bash
git clone https://github.com/wshape1/agent-cronjob-templates.git
cd agent-cronjob-templates/<任务目录>
# 按 README 安装依赖、修改配置、测试运行
```

> **注意**：安装前请确认 Agent 环境中存在 cronjob prompt 里提到的工具（如 `send_email`、`web_extract` 等），缺失的工具需要自行配置或替换。

## 目录结构

```
<task_name>/
├── README.md
├── prompt.md
├── snapshot.jpeg
└── scripts/
```
