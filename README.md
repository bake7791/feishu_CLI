# 燃料电池每日情报自动化推送

基于飞书机器人 + GitHub Actions 的全球燃料电池行业情报每日自动化推送系统。

## 功能概述

- **多语言信源采集**：中文 / 英文 / 日文 / 韩文 / 德文 Google News + 自定义 RSS
- **AI 智能分析**：GPT-4o 结构化生成摘要 + 五段式简报（政策/技术/竞争/市场/行动建议）
- **飞书卡片推送**：交互式卡片，自动分片，按地区分组展示
- **定时自动化**：GitHub Actions 每日定时执行，无需服务器
- **崩溃告警**：脚本异常自动推送飞书故障通知

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

然后编辑刚复制的文件：

| 文件 | 说明 |
|------|------|
| `settings.json` | AI 端点、模型、卡片样式、地区映射、屏蔽词 |
| `sources.json` | Google News 检索词（多语言）、自定义 RSS 源 |
| `prompt_system.txt` | AI 系统提示词（分析角色与输出格式） |
| `prompt_user.txt` | AI 用户提示词（使用 `{article_count}` 和 `{articles_text}` 占位符）|
| `prompt_fallback.txt` | AI 降级提示词（JSON 输出失败时的纯文本模式）|

### 3. 配置 GitHub Secrets

进入仓库 **Settings → Secrets and variables → Actions**，添加三个密钥：

| Secret 名称 | 值 |
|-------------|-----|
| `FEISHU_WEBHOOK_URL` | 飞书机器人 Webhook 地址 |
| `FEISHU_SECRET` | 飞书机器人签名校验密钥 |
| `AI_API_TOKEN` | OpenAI / 兼容 API 的 Token |

## 手动触发调试

1. 进入仓库 **Actions** 标签
2. 选择 **燃料电池每日情报推送**
3. 点击 **Run workflow** → **Run workflow**

## 本地调试

```bash
# 安装依赖（仅标准库，无需 pip install）
# 设置环境变量后运行
DRY_RUN=1 python main.py
```

`DRY_RUN=1` 模式仅打印卡片内容到控制台，不实际推送。

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
├── .github/workflows/daily_report.yml   # GitHub Actions 定时任务
├── config/                              # 配置文件（用户仅修改此处）
│   ├── settings.example.json
│   ├── sources.example.json
│   ├── prompt_system.example.txt
│   ├── prompt_user.example.txt
│   └── prompt_fallback.example.txt
├── src/                                 # 功能模块（普通用户无需改动）
│   ├── config_loader.py                 # 配置加载与校验
│   ├── crawler.py                       # 新闻采集
│   ├── ai_client.py                     # AI 分析
│   ├── feishu_bot.py                    # 飞书推送
│   └── utils.py                         # 通用工具
├── main.py                              # 主入口
└── .gitignore                           # 屏蔽真实配置文件
```

## v2.0 更新说明

相比旧版 `test.py`，本版本修复了以下关键问题：

- **HMAC 签名 BUG**：传入实际请求 Body 替代空字节，修复飞书拦截
- **全局异常捕获**：崩溃自动推送飞书故障告警
- **多格式 RSS 时间解析**：支持 8 种日期格式，修复排序错乱
- **配置前置校验**：缺失必填字段输出中文提示
- **URL 去重**：URL 优先 + 标题辅助，防止漏删和误删
- **配置化屏蔽词**：消除代码内硬编码
- **智能 Markdown 分片**：优先在二级标题处切割
- **防重复推送**：本地记录执行日期
