# Security Policy

## Secrets

永远不要把以下内容提交到 GitHub：

- Canvas Access Token
- `.env` 或本地凭证文件
- Canvas 用户资料和真实课程导出
- 课程下载文件和学生作业
- Calendar Feed URL
- 带签名参数的临时下载 URL
- 缓存和调试日志

如果 Token 被提交到 Git，即使后来删除文件，也应立即在 Canvas 中撤销并重新生成。普通删除提交无法保证 Token 已从 Git 历史和所有 Fork 中移除。

## Credential storage

默认长期凭证存储：

- macOS Keychain
- Windows Credential Manager
- Linux 安全凭证后端

不应降级为明文长期保存。如果安全凭证库不可用，只能在用户知情并同意后使用临时会话模式。

## Reporting a vulnerability

请不要在公开 Issue 中粘贴 Token、课程数据或可复现的真实账户信息。报告问题时使用虚构域名、虚构课程 ID 和脱敏响应。

## Submission safeguards

涉及 Canvas 上传或正式提交的问题，应保留以下安全边界：

- 上传和提交是不同操作。
- 每次上传需要确认。
- 每次正式提交需要基于最新状态进行最终确认。
- 不确定的网络结果必须先查询状态，不得自动重复提交。

