# Initialization prompts

Use these prompts as written apart from translating them to the user's language and replacing runtime placeholders. Do not add personal data from earlier conversations to examples.

## Round one

```text
首次使用需要提供 Canvas 地址和 Access Token。

获取 Token：

Canvas → Account → Settings → Approved Integrations → + New Access Token

Canvas 地址填写平时登录 Canvas 使用的域名，例如：

https://canvas.example.edu

请回复：

Canvas 地址：
Access Token：
Token 到期日期（可选）：

Token 会出现在当前对话记录中，请不要分享这段对话。收到后，我不会复述或显示 Token。
```

## Connection complete

```text
Canvas 连接成功。

账户：{用户姓名}
时区：{时区}
可访问课程：{课程数量}

Token 已默认保存在电脑自带的安全凭证库中，不会写入 Skill、普通配置文件或日志。

如果系统显示权限提示，请选择“始终允许”，这样以后读取 Canvas 凭证时不需要重复确认。授权只应针对 Canvas 学习助手自己的凭证。

如果你只想在当前会话临时使用，可以随时告诉我“切换为仅本次使用”。

系统默认使用标准缓存，以提高查询速度。课程、作业和文件信息会短期保存，但排期、下载和提交前会自动检查最新数据。

你可以随时要求刷新数据、清空缓存、更新 Token 或断开 Canvas。

```

This is a completion notice, not another question. Do not ask the user to choose a credential mode during normal initialization.
