# 每日情报推送机器人 — 飞书企业自建应用版

基于飞书企业自建应用 + GitHub Actions 的自动化情报推送系统。  
**换品种、换行业、换数据源只需编辑一个 JSON 文件，无需改代码。**

---

## 推送效果

- **摘要卡片** — 核心结论 + 情绪指数 + 关键要点
- **KPI 看板卡片** — 多列价格看板 + 数据明细表
- **图表卡片** — 趋势折线图 + 涨跌幅柱状图（PNG）
- **报告正文卡片** — AI 生成的决策级 Markdown 日报

---

## 对方拿到手只需 4 步

### 第 1 步：Fork 本仓库

点击右上角 Fork，把仓库复制到你的账号下。

### 第 2 步：创建飞书应用

1. 进入 [飞书开放平台](https://open.feishu.cn/) → 创建**企业自建应用**
2. 在"权限管理"中申请：
   - `im:message` — 发送消息
   - `im:image` — 上传图片（图表卡片需要）
3. 发布应用版本，等管理员审批
4. 记下 **App ID** 和 **App Secret**（在"凭证与基础信息"页）
5. 在飞书通讯录中找到你自己，复制 **open_id**（以 `ou_` 开头）

### 第 3 步：配置 GitHub Secrets

进入 Fork 后的仓库 → Settings → Secrets and variables → Actions → New repository secret，添加 4 个：

| Secret 名 | 内容 | 从哪获取 |
|-----------|------|----------|
| `FEISHU_APP_ID` | `cli_xxxxxxxx` | 飞书开放平台 → 应用凭证 |
| `FEISHU_APP_SECRET` | `xxxxxxxx` | 飞书开放平台 → 应用凭证 |
| `FEISHU_RECEIVE_ID` | `ou_xxxxxxxx` | 飞书通讯录 → 你的 open_id |
| `AI_API_TOKEN` | `ghp_xxx` 或 `sk-xxx` | GitHub Token 或 OpenAI Key |

### 第 4 步：启用 Actions

仓库 → Settings → Actions → General → 选择 "Allow all actions"，保存。

推送默认在每天 UTC 1:00（北京时间 9:00）自动执行。你也可以在 Actions 页面手动触发（`workflow_dispatch`）。

---

## 自定义报告内容（换行业/换品种）

打开 `config/report_config.json`，这是**唯一需要编辑的配置文件**。里面有三个核心区域：

### ① `data_items` — 追踪哪些品种

```json
{
  "name": "沪铜主力",        // 显示名称
  "source": "eastmoney",     // 数据源：yahoo / eastmoney / sina
  "fallback": "sina",        // 东方财富不可用时自动切新浪
  "symbol": "CU0",           // 品种代码
  "market": "113",           // 市场代码（上期所=113）
  "unit": "元/吨",           // 单位
  "exchange": "SHFE",        // 交易所缩写
  "region": "CN",            // 地区：CN / GLOBAL
  "category": "copper",      // 分类
  "enabled": true            // 设为 false 可禁用
}
```

**例子**：想追踪钢材，把上面的铜/铝删掉，换成：
```json
{"name": "螺纹钢主力", "source": "eastmoney", "fallback": "sina", "symbol": "RB0", "market": "113", "unit": "元/吨", "exchange": "SHFE", "region": "CN", "category": "steel"},
{"name": "铁矿石主力", "source": "eastmoney", "fallback": "sina", "symbol": "I0",  "market": "113", "unit": "元/吨", "exchange": "DCE", "region": "CN", "category": "steel"}
```

### ② `news.topics` — 搜哪些新闻

```json
"topics": ["copper price forecast", "copper mining", "pre-baked anode", ...]
```

换成你自己的行业关键词。Google News 会自动搜索这些词的中英文结果。

### ③ `report` — 报告标题和配色

```json
"title": "铜及预焙阳极每日情报报告",
"industry": "铜及预焙阳极",
"audience": "企业老板、采购负责人和运营高层"
```

---

## 自定义环境变量名

如果想把 `FEISHU_APP_ID` 改成 `MY_BOT_APP_ID`，只需编辑 `src/env_vars.py`：

```python
ENV_FEISHU_APP_ID = "MY_BOT_APP_ID"  # 改这里
```

然后同步更新：
- GitHub Secrets 的名称
- `.github/workflows/daily_report.yml` 中 `secrets.XXX` 的映射

---

## 自定义 AI 提示词

编辑 `config/prompt_system.example.txt`，或复制为 `prompt_system.txt`。

---

## 本地测试

```bash
# 安装依赖
pip install -r requirements.txt

# 设置环境变量（PowerShell）
$env:FEISHU_APP_ID="cli_xxx"
$env:FEISHU_APP_SECRET="xxx"
$env:FEISHU_RECEIVE_ID="ou_xxx"
$env:AI_API_TOKEN="ghp_xxx"

# 预览模式（不推送，使用示例数据）
$env:DRY_RUN=1
python main.py

# 正式推送
$env:DRY_RUN=$null
python main.py
```

---

## 项目结构

```
main.py                        入口：采集→数据→AI→图表→推送
requirements.txt               Python 依赖
config/
  report_config.json           报告数据模型（品种、新闻话题、配色）
  settings.example.json        系统参数（AI 端点、卡片限制等）
  sources.example.json         信源配置（检索词、RSS 地址）
  prompt_system.example.txt    AI 系统提示词
  prompt_user.example.txt      AI 用户提示词
src/
  env_vars.py                  环境变量名集中定义
  config_loader.py             配置加载与校验
  crawler.py                   新闻采集（Google News + RSS）
  data_fetcher.py              量化数据采集（Yahoo / 东方财富 / 新浪）
  chart_renderer.py            matplotlib 图表渲染
  ai_client.py                 AI 分析 + 情绪量化
  feishu_bot.py                飞书推送（图片上传 + KPI 看板 + 卡片）
  utils.py                     HTTP 工具 + RSS 日期解析
.github/workflows/             GitHub Actions 定时任务
```

---

## 数据源说明

| 类型 | 覆盖范围 | CI 可用性 |
|------|----------|-----------|
| Yahoo Finance | 国际期货、指数（COMEX 铜、美元指数） | ✅ 全球 |
| 东方财富 | 国内期货（沪铜、沪铝） | ⚠️ 国内 IP 最佳 |
| 新浪财经 | 国内期货备用（东方财富不可用时自动切换） | ✅ CDN 对海外较友好 |

国内品种（`source: "eastmoney"` + `fallback: "sina"`）在 GitHub Actions 中会先尝试东方财富，失败后自动切换新浪，对使用者完全透明。

---

## 常见问题

**Q: Fork 后 Actions 没有自动运行？**  
A: Fork 的仓库默认禁用 Actions，需要手动去 Settings → Actions → General 开启。

**Q: 推送报错"获取 tenant_access_token 失败"？**  
A: App ID 或 App Secret 填错了，或者应用没有发布。

**Q: KPI 卡片只有国际品种，国内的是空的？**  
A: GitHub Actions 跑在美国 IP 上，东方财富和新浪可能同时被封。检查 workflow 日志中 `[2/5]` 部分，看是否有 `WARN`。如果两边都失败，系统会自动用示例数据填充。

**Q: 想更频繁地推送（比如每小时）？**  
A: 编辑 `.github/workflows/daily_report.yml` 中的 `cron` 表达式。`0 */6 * * *` 表示每 6 小时一次。
