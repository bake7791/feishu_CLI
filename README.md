# 每日情报推送机器人 — 飞书企业自建应用版

基于飞书企业自建应用 + GitHub Actions 的自动化情报推送系统。  
**换品种、换行业、换数据源、调卡片顺序只需编辑 JSON 文件，无需改代码。**

---

## 推送效果

- **摘要卡片** — 核心结论 + 情绪指数 + 关键要点
- **KPI 看板卡片** — 多列价格看板 + 数据明细表（国内+国际数据同时展示）
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

## 自定义报告内容

打开 `config/report_config.json`，这是**唯一需要编辑的报告配置文件**。四个核心区域：

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

> 国内品种配置 `fallback: "sina"` 后，GitHub Actions 中东方财富被封时自动切换新浪财经，保证数据不缺失。如果两个源都失败，系统会自动用备用数据填充，KPI 看板始终显示全部品种。

### ② `news.topics` — 搜哪些新闻

```json
"topics": ["copper price forecast", "copper mining", "pre-baked anode", ...]
```

换成你自己的行业关键词。Google News 会自动搜索这些词的中英文结果。

### ③ `layout.cards` — 卡片顺序和显隐

```json
"cards": [
  {"id": "summary",       "enabled": true, "color": "blue"},
  {"id": "kpi_dashboard", "enabled": true, "color": "blue"},
  {"id": "charts",        "enabled": true, "color": "wathet"},
  {"id": "report_body",   "enabled": true, "color": "green"}
]
```

| 操作 | 方法 |
|------|------|
| 图表放最前面 | 把 `charts` 拖到数组第一项 |
| 不想发 KPI 看板 | `"enabled": false` |
| 换个颜色 | 改 `color`：blue / green / red / turquoise / purple / wathet |

### ④ `report` — 标题和配色

```json
"title": "铜及预焙阳极每日情报报告",
"industry": "铜及预焙阳极",
```

---

## 自定义信源

编辑 `config/sources.json`（首次使用复制 `sources.example.json`）。

### Google News 关键词搜索

在 `queries` 数组中添加：

```json
{"query": "你要搜的关键词", "hl": "zh-CN", "gl": "CN"}
```

`hl`=界面语言，`gl`=搜索地区。`zh-CN`/`en-US`/`es-CL` 等。

### 指定网站 RSS

在 `feeds` 数组中添加：

```json
{"name": "显示名称", "url": "https://网站.com/rss", "region": "CN"}
```

RSS 地址一般在网站底部找"RSS订阅"链接。没有 RSS 的网站可用 [RSSHub](https://docs.rsshub.app/) 生成。

### 付费 API

如果购买的付费数据源提供 REST API，在 `feeds` 中配置 URL 即可。需要 Token 认证的 API 可联系我扩展 crawler 支持（模板已预留 `paid_apis` 字段）。

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

编辑 `config/prompt_system.example.txt`（或复制为 `prompt_system.txt`）。

提示词决定了 AI 日报的模块结构（如"政策动态"、"技术与成本"等），换行业时记得同步修改。

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
main.py                        入口：采集→数据→AI→图表→推送（layout 驱动）
requirements.txt               Python 依赖
config/
  report_config.json           报告数据模型（品种/新闻话题/卡片布局/配色）
  settings.example.json        系统参数（AI 端点、卡片限制等）
  sources.json / .example      信源配置（Google News 检索词 + RSS feeds）
  prompt_system.example.txt    AI 系统提示词（换行业时编辑此文件）
  prompt_user.example.txt      AI 用户提示词模板
src/
  env_vars.py                  环境变量名集中定义（一处改名全局生效）
  config_loader.py             配置加载与校验（自动回退 .example）
  crawler.py                   新闻采集（Google News + RSS feeds）
  data_fetcher.py              量化数据采集（Yahoo / 东方财富 / 新浪，配置驱动）
  chart_renderer.py            matplotlib 图表渲染（自动检测中文字体）
  ai_client.py                 AI 分析 + 情绪量化
  feishu_bot.py                飞书推送（图片上传 + KPI 看板 + column_set 表格）
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

国内品种（`source: "eastmoney"` + `fallback: "sina"`）在 GitHub Actions 中会先尝试东方财富，失败后自动切换新浪，两个都失败则用备用数据填充。对使用者完全透明。

---


## 实战示例

### 示例一：换行业——从铜改成氢燃料电池

改 `config/report_config.json` 三个地方：

**report 元数据：**
```json
"report": {
  "title": "氢燃料电池产业每日情报",
  "industry": "氢燃料电池",
  "audience": "企业高管、技术负责人、投资决策者"
}
```

**data_items（追踪铂金、天然气、碳配额、美元指数）：**
```json
"data_items": [
  {
    "name": "铂金期货", "source": "yahoo", "symbol": "PL=F",
    "unit": "美元/盎司", "exchange": "NYMEX", "region": "GLOBAL",
    "category": "catalyst", "enabled": true
  },
  {
    "name": "天然气主力", "source": "eastmoney", "fallback": "sina",
    "symbol": "NG0", "market": "113", "unit": "元/吨",
    "exchange": "SHFE", "region": "CN", "category": "feedstock", "enabled": true
  },
  {
    "name": "碳配额价格", "source": "yahoo", "symbol": "KRN=F",
    "unit": "欧元/吨", "exchange": "ICE", "region": "GLOBAL",
    "category": "policy", "enabled": true
  },
  {
    "name": "美元指数", "source": "yahoo", "symbol": "DX-Y.NYB",
    "unit": "", "exchange": "ICE", "region": "GLOBAL",
    "category": "macro", "enabled": true
  }
]
```

**news.topics（氢燃料电池关键词）：**
```json
"topics": [
  "hydrogen fuel cell policy",
  "green hydrogen production",
  "PEM fuel cell technology",
  "hydrogen refueling station",
  "fuel cell vehicle China",
  "electrolyzer manufacturing",
  "碳交易 氢能",
  "燃料电池 补贴",
  "氢能 示范城市"
]
```

然后编辑 `config/prompt_system.example.txt`，把提示词里的“铜产业链行情”等模块换成“政策动态”“技术与成本”“产业链动态”等。**全程不改 Python 代码。**

---

### 示例二：调整卡片——只要摘要和正文，图表放前面

```json
"layout": {
  "cards": [
    {"id": "charts",      "enabled": true, "color": "wathet"},
    {"id": "summary",     "enabled": true, "color": "blue"},
    {"id": "report_body", "enabled": true, "color": "green"},
    {"id": "kpi_dashboard","enabled": false}
  ]
}
```

---

### 示例三：增加品种——加一个 LME 铜

在 `data_items` 数组中插入（注意找对 Yahoo Finance 的 symbol）：

```json
{
  "name": "LME铜3M",
  "source": "yahoo",
  "symbol": "LME=F",
  "unit": "美元/吨",
  "exchange": "LME",
  "region": "GLOBAL",
  "category": "copper",
  "enabled": true
}
```

推送、保存。下次报告 KPI 看板自动多一列 LME 铜，无需动代码。

---

### 示例四：加行业 RSS——接入上海有色网和 Mysteel

编辑 `config/sources.json`，在 `feeds` 数组中加：

```json
"feeds": [
  {"name": "SMM 铜",  "url": "https://news.smm.cn/rss/copper",    "region": "CN"},
  {"name": "SMM 铝",  "url": "https://news.smm.cn/rss/aluminum",  "region": "CN"},
  {"name": "Mysteel",     "url": "https://feed.mysteel.com/有色", "region": "CN"}
]
```

crawler 自动抓取，和 Google News 一起去重排序。

---

### 示例五：改环境变量名——FEISHU_APP_ID → MY_BOT_ID

编辑 `src/env_vars.py`：

```python
ENV_FEISHU_APP_ID = "MY_BOT_ID"
```

然后同步更新 GitHub Secrets 名称 + `.github/workflows/daily_report.yml` 第 32 行：

```yaml
MY_BOT_ID: ${{ secrets.MY_BOT_ID }}
```

其他 3 个凭据变量同理。

---

### 示例六：本地测试完整流程

```powershell
# 1. 进入项目
cd feishu_robot

# 2. 装依赖
pip install -r requirements.txt

# 3. 设环境变量
$env:FEISHU_APP_ID="cli_xxxxx"
$env:FEISHU_APP_SECRET="xxxxx"
$env:FEISHU_RECEIVE_ID="ou_xxxxx"
$env:AI_API_TOKEN="ghp_xxxxx"

# 4. 预览（不推送，验证所有卡片和数据）
$env:DRY_RUN=1
python main.py

# 5. 确认无误后正式推送
$env:DRY_RUN=$null
python main.py
```


## 常见问题

**Q: Fork 后 Actions 没有自动运行？**  
A: Fork 的仓库默认禁用 Actions，需要手动去 Settings → Actions → General 开启。

**Q: 推送报错"获取 tenant_access_token 失败"？**  
A: App ID 或 App Secret 填错了，或者应用没有发布。

**Q: KPI 卡片只有国际品种，国内的是空的？**  
A: GitHub Actions 跑在美国 IP 上，东方财富和新浪可能同时被封。系统会自动用备用数据填充缺失项，日志中会标注"使用备用数据"。

**Q: 想更频繁地推送（比如每小时）？**  
A: 编辑 `.github/workflows/daily_report.yml` 中的 `cron` 表达式。`0 */6 * * *` 表示每 6 小时一次。

**Q: COMEX 铜价格显示不对？**  
A: Yahoo Finance 返回的是美元/磅，不是美分/磅。当前配置已修正为单位"美元/磅"，价格小于 100 的品种自动保留 2 位小数。
