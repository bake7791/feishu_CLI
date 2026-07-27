"""
================================================================================
环境变量常量定义 (env_vars.py)
================================================================================
职责：所有环境变量名集中在此文件定义，其他模块通过 import 引用。

为什么需要这个文件？
  项目中的飞书凭证、AI Token 等信息通过环境变量注入。
  如果使用者想自定义环境变量名（比如从 FEISHU_APP_ID 改成 MY_BOT_ID），
  过去需要修改 3 个文件（config_loader.py / main.py / daily_report.yml），
  很容易漏改导致运行时报错。

  现在只需修改本文件中的常量值即可，一处改动全局生效。

使用示例：
  from src.env_vars import ENV_FEISHU_APP_ID, ENV_AI_TOKEN
  app_id = os.environ.get(ENV_FEISHU_APP_ID, "")
================================================================================
"""

# ── 飞书企业自建应用凭证 ──
# 在 GitHub Actions 中通过 secrets 注入，本地开发可 export 设置
ENV_FEISHU_APP_ID     = "FEISHU_APP_ID"      # 飞书应用 App ID
ENV_FEISHU_APP_SECRET = "FEISHU_APP_SECRET"  # 飞书应用 App Secret
ENV_FEISHU_RECEIVE_ID = "FEISHU_RECEIVE_ID"  # 消息接收者 open_id / user_id

# ── AI 模型调用凭证 ──
ENV_AI_TOKEN           = "AI_API_TOKEN"       # AI API Token（优先）
ENV_AI_TOKEN_FALLBACK  = "GITHUB_TOKEN"       # AI Token 备选（兼容旧命名）

# ── 运行模式 ──
ENV_DRY_RUN = "DRY_RUN"  # 设为 1 启用预览模式，不实际推送

# ── 可选：自定义接收者列表（逗号分隔） ──
ENV_EXTRA_RECEIVERS = "FEISHU_EXTRA_RECEIVERS"  # 额外的接收者 open_id
