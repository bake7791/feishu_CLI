# 燃料电池每日情报自动化推送

基于飞书企业自建应用机器人 + GitHub Actions + GitHub Models 免费 GPT-4o 的全球燃料电池行业情报每日自动化推送系统。

## 功能概述

- **多语言信源采集**：中文 / 英文 / 日文 / 韩文 / 德文 Google News + 自定义 RSS
- **AI 智能分析**：GitHub Models 免费 GPT-4o 结构化生成摘要 + 五段式简报
- **飞书卡片推送**：企业自建应用机器人，通过 open_id 推送到指定用户
- **定时自动化**：GitHub Actions 每日北京时间 09:00 自动执行
- **崩溃告警**：脚本异常自动推送飞书故障通知
- **零成本运行**：GitHub Models 免费额度 + Actions 免费额度

## 前置准备：创建飞书企业自建应用

1. 进入 [飞书开放平台](https://open.feishu.cn/app) → 创建企业自建应用
2. **添加能力**：开启「机器人」能力
3. **权限管理**：在「权限管理」中添加 `im:message:send_as_bot`（以机器人身份发送消息）权限
4. **发布版本**：创建版本并发布，等待管理员审核通过
5. 在「凭证与基础信息」中获取 **App ID** 和 **App Secret**
6. 在飞书中找到目标用户，通过 [飞书开放平台 API](https://open.feishu.cn/document/server-docs/contact-v3/user/) 获取其 **open_id**

## 三步部署

### 1. Fork 本仓库

点击右上角 Fork → 选择你的账号。

### 2. 复制配置模板

```bash
cd config
cp settings.example.json settings.json
cp sources.example.json sources.json
cp prompt_system.example.txt prompt_system.txt
cp prompt_user.example.txt prompt_user.txt
cp prompt_fallback.example.txt prompt_fallback.txt
```

然后按需编辑：

| 文件 | 说明 |
|------|------|
| `settings.json` | AI 端点（默认 GitHub Models）、卡片样式、地区映射、屏蔽词 |
| `sources.json` | Google News 检索词（多语言）、自定义 RSS 源 |
| `prompt_system.txt` | AI 系统提示词（分析角色与输出格式） |
| `prompt_user.txt` | AI 用户提示词（`{article_count}` 和 `{articles_text}` 占位符）|
| `prompt_fallback.txt` | AI 降级提示词（JSON 输出失败时的纯文本模式）|

### 3. 配置 GitHub Secrets

进入仓库 **Settings → Secrets and variables → Actions**，添加 **三个** 密钥：

| Secret 名称 | 值 |
|-------------|-----|
| `FEISHU_APP_ID` | 飞书应用 App ID（如 `cli_aaeb3f6171789bfb`）|
| `FEISHU_APP_SECRET` | 飞书应用 App Secret |
| `FEISHU_RECEIVE_ID` | 消息接收者的 open_id（如 `ou_24a2c63f...`）|

> GitHub Models 的 GPT-4o 认证使用 Actions 内置的 `GITHUB_TOKEN`，无需额外配置。

## 手动触发调试

1. 进入仓库 **Actions** 标签
2. 选择 **燃料电池每日情报推送**
3. 点击 **Run workflow** → **Run workflow**

## 本地调试验证

```bash
# 零依赖（仅 Python 标准库）
# 设置环境变量后运行
$env:FEISHU_APP_ID="cli_xxxxxxxxxxxx"
$env:FEISHU_APP_SECRET="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
$env:FEISHU_RECEIVE_ID="ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
$env:GITHUB_TOKEN="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
DRY_RUN=1 python main.py    # 预览模式，不实际推送
python main.py               # 正式推送
```

## 修改指南

### 新增信源

编辑 `config/sources.json`：

```json
{
  "queries": [
    { "query": "关键词", "hl": "zh-CN", "gl": "CN" }
  ],
  "feeds": [
    { "name": "来源名", "url": "https://example.com/rss", "region": "GLOBAL" }
  ]
}
```

### 调整 AI 输出风格

编辑 `config/prompt_system.txt` 和 `config/prompt_user.txt`。

### 修改飞书卡片样式

编辑 `config/settings.json` 中的颜色和标签字段。

## 项目结构

```
├── .github/workflows/daily_report.yml
├── config/
│   ├── settings.example.json
│   ├── sources.example.json
│   ├── prompt_system.example.txt
│   ├── prompt_user.example.txt
│   └── prompt_fallback.example.txt
├── src/
│   ├── config_loader.py      # 配置加载与校验
│   ├── crawler.py             # 新闻采集
│   ├── ai_client.py           # AI 分析
│   ├── feishu_bot.py          # 飞书企业自建应用推送
│   └── utils.py               # 通用工具
├── main.py                    # 主入口
└── .gitignore
```
