# 铜及预焙阳极每日情报推送 — 企业自建应用增强版

基于飞书企业自建应用 + GitHub Actions + GitHub Models 免费 GPT-4o 的自动化情报推送系统，新增**量化数据采集**与**图表可视化**能力。

## 与群机器人 Webhook 版的区别

| | 企业自建应用版（本项目） | 群机器人 Webhook 版 |
|---|---|---|
| 推送目标 | 指定用户（open_id） | 群聊（所有成员可见） |
| 鉴权方式 | tenant_access_token | HMAC-SHA256 签名 |
| 所需凭证 | App ID + App Secret + Receive ID | Webhook URL + 签名密钥 |
| **图片推送** | **支持（im/v1/images 上传 + 卡片嵌入）** | 不支持 |
| **KPI 看板** | **支持（column_set 多列布局）** | 仅 markdown |
| **量化图表** | **支持（matplotlib PNG 趋势图/柱状图）** | 仅 Unicode 字符图 |
| 部署复杂度 | 3 步（创建应用、申请权限、发布） | 1 步（创建机器人获取 URL） |

## 增强能力

### 量化数据采集
- 沪铜主力、沪铝主力（东方财富期货行情）
- LME 铜、美元指数（新浪财经外盘行情）
- 近 7 日 K 线历史数据（趋势图用）

### 图表可视化（发挥自建应用发图优势）
- 近 7 日价格趋势折线图（带涨跌底色 + 最新价标注）
- 当日涨跌幅横向柱状图（涨红跌绿）
- 中文字体自动检测（Noto CJK / 微软雅黑），找不到自动降级英文

### AI 情绪量化
- 综合情绪指数（-10 偏空 ~ +10 偏多）
- 重要新闻逐条情绪打分 + 影响星级

## 推送卡片结构

1. **摘要卡片** — 核心结论 + 情绪指数 + 关键要点
2. **KPI 看板卡片** — column_set 多列价格看板 + 数据明细表（新增）
3. **图表卡片** — 趋势折线图 + 涨跌幅柱状图 PNG（新增）
4. **报告正文卡片** — 8 模块决策级 Markdown
5. **信源列表卡片** — 按地区分组

## 四步部署

### 1. 创建飞书企业自建应用
1. 进入[飞书开放平台](https://open.feishu.cn/) → 创建企业自建应用
2. 申请权限：`im:message`、`im:image`
3. 发布应用版本，等待企业管理员审批
4. 记录 **App ID** 和 **App Secret**
5. 获取接收者 **open_id**（通讯录中查看用户详情）

### 2. Fork 本仓库

### 3. 配置 4 个 GitHub Secrets

| Secret 名称 | 值 |
|---|---|
| `FEISHU_APP_ID` | 应用 App ID |
| `FEISHU_APP_SECRET` | 应用 App Secret |
| `FEISHU_RECEIVE_ID` | 接收者 open_id |
| `AI_API_TOKEN` | GitHub Token（免费 GPT-4o）或 OpenAI Key |

### 4. 启用 Actions
Fork 后在仓库 Settings → Actions → 允许 workflows 运行。
每日 UTC 1:00（北京时间 9:00）自动推送。

## 本地测试

```bash
$env:FEISHU_APP_ID="cli_xxx"
$env:FEISHU_APP_SECRET="xxx"
$env:FEISHU_RECEIVE_ID="ou_xxx"
$env:AI_API_TOKEN="ghp_xxx"
$env:DRY_RUN=1; python main.py    # 预览不推送（使用示例数据）
python main.py                    # 正式推送
```

## 项目结构

```
main.py                    入口：采集→数据→AI→图表→推送
src/
  config_loader.py         配置加载与校验
  crawler.py               新闻采集（Google News + RSS）
  data_fetcher.py          量化数据采集（新增）
  chart_renderer.py        matplotlib 图表渲染（新增）
  ai_client.py             AI 分析 + 情绪量化
  feishu_bot.py            飞书推送（图片上传 + KPI看板 + 卡片）
  utils.py                 HTTP 工具 + RSS 日期解析
config/                    配置文件（.example 模板）
.github/workflows/         GitHub Actions 定时任务
```

## 换品种

修改 config/ 目录下的配置文件，代码无需改动。
在 `data_fetcher.py` 中调整品种的 secid 映射即可采集不同期货品种。
