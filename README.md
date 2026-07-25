# 铜及预焙阳极每日情报自动化推送

基于飞书企业自建应用机器人 + GitHub Actions + GitHub Models 免费 GPT-4o 的铜价及预焙阳极每日情报自动化推送系统。

## 关注标的

- **铜**：LME/上海铜价走势、铜精矿 TC/RC、全球供需、冶炼厂动态、主要产铜国（智利、秘鲁）政策
- **预焙阳极**：国内预焙阳极价格、煤沥青/石油焦等原料行情、铝用碳素行业动态

## 功能概述

- **多语言信源采集**：中文 / 英文 / 西班牙语 Google News + 自定义 RSS（上海有色网等）
- **AI 智能分析**：GitHub Models 免费 GPT-4o 结构化生成摘要 + 五段式简报
- **飞书卡片推送**：企业自建应用机器人，通过 open_id 推送到指定用户
- **定时自动化**：GitHub Actions 每日北京时间 09:00 自动执行
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

### 3. 配置 GitHub Secrets

进入仓库 **Settings → Secrets and variables → Actions**，添加三个密钥：

| Secret 名称 | 值 |
|-------------|-----|
| `FEISHU_APP_ID` | 飞书应用 App ID |
| `FEISHU_APP_SECRET` | 飞书应用 App Secret |
| `FEISHU_RECEIVE_ID` | 消息接收者的 open_id |

## 如何切换关注品种

所有与品种相关的配置都在 `config/` 目录下，**无需修改任何 Python 代码**：

| 想改什么 | 改哪个文件 |
|----------|-----------|
| 信源 / 检索关键词 | `sources.json` |
| AI 分析角色与输出框架 | `prompt_system.txt` |
| AI 提问方式 | `prompt_user.txt` |
| AI 降级备用提示词 | `prompt_fallback.txt` |
| 地区映射 / 卡片样式 / 屏蔽词 | `settings.json` |

## 项目结构

```
├── .github/workflows/daily_report.yml
├── config/                          # 配置文件（换品种只改这里）
│   ├── settings.example.json
│   ├── sources.example.json
│   ├── prompt_system.example.txt
│   ├── prompt_user.example.txt
│   └── prompt_fallback.example.txt
├── src/                             # 功能模块（无需改动）
│   ├── config_loader.py
│   ├── crawler.py
│   ├── ai_client.py
│   ├── feishu_bot.py
│   └── utils.py
├── main.py
└── .gitignore
```
