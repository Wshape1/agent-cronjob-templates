# 新闻快闪 CronJob

实时推送财经新闻快讯到飞书，每2小时自动执行。基于 news-flash skill 抓取财联社电报、新浪财经7x24等信源，从基金投资视角精选最重要的3条新闻。

## 工作流程

```
Agent 加载 news-flash skill → web_fetch 抓取信源 → AI 精选+格式化 → 推送飞书
```

1. **信源抓取**：web_fetch 并行抓取财联社电报、新浪财经7x24
2. **AI 精选**：从基金投资视角选出最重要的3条
3. **格式化输出**：emoji短标题 + 精确时间戳 + 简评 + 基金影响
4. **推送**：通过飞书发送给用户

## 文件说明

```
news_flash/
├── README.md          ← 你在看的这个
├── prompt.md          ← CronJob 的 prompt
└── skill/
    └── SKILL.md       ← news-flash skill（格式规范+抓取方法+已知坑）
```

## 使用方法

### 一键安装

将以下 prompt 直接发送给 Agent，自动完成安装：

```
帮我安装新闻快闪 CronJob：
1. 克隆仓库 git clone https://github.com/wshape1/agent-cronjob-templates.git （如失败用备用源 https://gitee.com/wshape1/agent-cronjob-templates.git ）
2. 将 news_flash/skill/SKILL.md 安装为 news-flash skill（放到 ~/.hermes/skills/news-flash/SKILL.md）
3. 将 news_flash/prompt.md 设为 CronJob 的 prompt
4. schedule 设为 "0 0,8-23/2 * * *"（每2小时，0点和8-23点的偶数小时）
5. deliver 设为 "feishu"
6. enabled_toolsets 设为 ["web", "file", "terminal"]
```

### 手动安装

**1. 安装 skill**

```bash
mkdir -p ~/.hermes/skills/news-flash
cp news_flash/skill/SKILL.md ~/.hermes/skills/news-flash/SKILL.md
```

**2. 创建 CronJob**

在 Agent 中执行：

```
创建一个 CronJob：
- name: 新闻快闪-每小时推送
- schedule: 0 0,8-23/2 * * *
- deliver: feishu
- skills: ["news-flash"]
- enabled_toolsets: ["web", "file", "terminal"]
- prompt: （粘贴 prompt.md 的内容）
```

### CronJob 参数

| 参数 | 值 |
|------|-----|
| schedule | `0 0,8-23/2 * * *` |
| deliver | `feishu` |
| skills | `["news-flash"]` |
| enabled_toolsets | `["web", "file", "terminal"]` |
| script | 无（纯 Agent 驱动） |

## 快闪特点

- **基金视角**：从 A 股基金投资角度筛选新闻
- **3条精选**：不贪多，只推最重要的
- **精确时间戳**：每条标注具体时间
- **实操建议**：每条带板块利好/利空和调仓建议
- **信源可靠**：财联社电报 + 新浪7x24，数据验证铁律

## 已知限制

- 飞书投递，不支持微信（iLink API 频率限制）
- 依赖 web_fetch 抓取，部分网站可能间歇性不可用
- Cron 频率受限于 API 调用成本
