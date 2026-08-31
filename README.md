# Canvas Study Assistant

一个面向学生的 Codex Skill，通过 Canvas LMS REST API 在对话中查询课程、整理作业与截止日期、安排学习计划、下载课程资料，并在用户明确确认后辅助上传和提交作业。

本项目只支持学生工作流，不提供教师、批改、课程管理或查看其他学生数据的能力。

## 主要功能

- 查询当前学生可访问的课程、教师和课程状态。
- 获取作业、DDL、开放/锁定时间、分值和提交状态。
- 按截止时间整理未完成作业并生成学习计划。
- 查询并下载 Canvas Course Files，支持所有文件类型。
- 当 Canvas 没有明确标注作业关联文件时，根据标题、编号和描述进行模糊匹配，并明确告知用户匹配置信度和依据。
- 下载后由用户选择需要分析的文件，不自动分析全部资料。
- 总结作业要求，与用户讨论选题和思路，再根据用户指令生成本地 Demo。
- 将“本地 Demo”“上传到 Canvas”“正式提交作业”严格分开。
- Token 到期后支持安全替换。

## 目录结构

```text
canvas-study-assistant/
├── README.md
├── SECURITY.md
├── SKILL.md
├── .gitignore
├── requirements-optional.txt
├── agents/
│   └── openai.yaml
├── references/
│   ├── api-workflows.md
│   ├── assignment-collaboration.md
│   ├── file-matching.md
│   ├── initialization-prompts.md
│   └── submission-safety.md
├── scripts/
│   └── canvas_cli.py
└── tests/
    └── test_cli.py
```

`SKILL.md` 是 Skill 的入口；详细流程按需从 `references/` 加载。`scripts/canvas_cli.py` 负责确定性的 Canvas API 请求、凭证、缓存、文件匹配、下载和提交操作。

## 环境要求

- Python 3.10 或更高版本。
- 一个允许生成个人 Access Token 的 Canvas 学生账户。
- macOS 和 Windows 的长期凭证功能不需要安装额外 Python 包。
- Linux 长期凭证依赖可用的系统 Secret Service/KWallet 和 Python `keyring`；无法使用时可切换为仅当前会话模式。

Linux 可选安装：

```bash
python3 -m pip install -r requirements-optional.txt
```

## 安装到 Codex

### macOS / Linux

```bash
git clone https://github.com/hairoom/canvas-study-assistant-skill.git \
  ~/.codex/skills/canvas-study-assistant
```

### Windows PowerShell

```powershell
git clone https://github.com/hairoom/canvas-study-assistant-skill.git `
  "$env:USERPROFILE\.codex\skills\canvas-study-assistant"
```

安装后重新打开 Codex，或开始一个新任务，然后输入：

```text
使用 $canvas-study-assistant 连接我的 Canvas
```

## 首次初始化

### 1. 获取 Canvas Access Token

登录 Canvas，然后依次进入：

```text
Account → Settings → Approved Integrations → + New Access Token
```

填写用途和过期时间后生成 Token。Token 通常只显示一次，请立即复制并妥善保管。

如果找不到 `New Access Token`，可能是学校管理员关闭了个人 Token 功能，需要联系学校的 Canvas 管理员。

### 2. 确认 Canvas 地址

Canvas 地址是平时登录 Canvas 使用的域名，不包含课程路径或 `/api/v1`。

```text
正确：https://canvas.example.edu
错误：https://canvas.example.edu/courses/12345
错误：https://canvas.example.edu/api/v1
```

### 3. 在对话中初始化

Skill 会显示简短提示，并要求：

```text
Canvas 地址：
Access Token：
Token 到期日期（可选）：
```

直接发送 Token 操作最简单，但 Token 会出现在当前对话历史中。不要分享该对话；如果对话曾被公开，应立即在 Canvas 中撤销 Token 并生成新的 Token。Skill 收到后不会复述或显示 Token。

如果不希望 Token 出现在对话中，可要求使用隐藏的本地输入方式。

### 4. 凭证保存

默认使用电脑的系统安全凭证库长期保存：

- macOS：Keychain
- Windows：Credential Manager
- Linux：可用的 Secret Service/KWallet 后端

Token 不会写入本仓库、`SKILL.md`、普通配置文件或日志。如果 Codex 显示系统权限提示，应只对 Canvas Study Assistant 自己的凭证选择“始终允许”，不要授予读取全部系统密码的宽泛权限。

如果只想临时使用，可以在对话中说：

```text
切换为仅本次使用
```

### 5. 默认缓存

Skill 默认使用标准缓存，以减少重复 API 请求：

- 课程列表：约 30 分钟
- 作业与 DDL：约 5 分钟
- 文件和模块列表：约 15 分钟
- 待办事项：约 2 分钟

生成排期、下载、上传和正式提交前，会自动刷新关键数据。用户可随时说：

```text
刷新 Canvas 数据
以后每次获取最新数据
减少 Canvas API 请求
恢复标准模式
清空 Canvas 缓存
```

## 使用案例

### 查看近期作业

```text
列出未来 7 天内所有未完成作业，按 DDL 排序。
```

### 安排本周学习

```text
我周一到周五每天有两小时，周末各有四小时。根据 DDL 帮我安排本周学习计划。
```

### 查找作业相关文件

```text
找出“Individual Assignment”可能相关的课程文件，并告诉我匹配依据。
```

如果不是 Canvas 明确关联，Skill 会提示这是模糊匹配，例如：

```text
Canvas 没有明确标记关联文件。以下结果来自模糊匹配：

- Assignment Brief.pdf：82%
- Assessment Rubric.docx：74%
```

### 下载和分析资料

```text
下载这个作业相关的文件。下载完成后先列出来，不要自动全部分析。
```

随后可以说：

```text
分析作业说明和评分标准，数据文件暂时不要分析。
```

### 作业要求与选题讨论

```text
总结作业要求，然后给我三个可行的选题方向，比较数据可得性、难度和风险。
```

### 生成作业 Demo

```text
根据我们确定的方向生成一个报告大纲和 Demo，不要上传 Canvas。
```

Demo 默认仅保存在本地，并与上传、提交操作分开。

### 更新 Token

```text
更新 Canvas Token
```

新 Token 会先验证。若属于不同用户，Skill 会要求确认账户切换，然后才替换旧凭证。

## 上传与提交安全

项目将操作划分为三个状态：

1. 本地 Demo：不修改 Canvas。
2. 上传草稿：文件进入 Canvas，但尚未提交作业。
3. 正式提交：Canvas 记录一次提交 Attempt。

上传前，Skill 必须展示课程、作业、文件名和大小并征求确认。

正式提交前，Skill 必须重新读取作业和当前提交状态，并展示：

- 课程和作业
- 待提交文件
- 当前时间和生效的 DDL
- 是否已锁定或可能迟交
- 当前 Attempt，以及本次是否会增加新的 Attempt

只有用户在看到最终摘要后明确确认，才能正式提交。网络结果不确定时，Skill 会先查询提交状态，不会盲目重试。

## CLI 调试

也可以在 Skill 目录中直接调试 CLI：

```bash
python3 scripts/canvas_cli.py --help
python3 scripts/canvas_cli.py status
python3 scripts/canvas_cli.py courses
python3 scripts/canvas_cli.py assignments --course COURSE_ID --pending --refresh
python3 scripts/canvas_cli.py schedule --days 7
python3 scripts/canvas_cli.py files --course COURSE_ID
python3 scripts/canvas_cli.py match-files --course COURSE_ID --assignment ASSIGNMENT_ID
```

`init` 和 `update-token` 使用隐藏输入读取 Token。不要把 Token 写进命令参数、环境变量或测试文件。

## 数据与隐私

- 仓库中不应包含 Token、用户资料、真实课程数据、缓存、下载文件或签名下载链接。
- 非敏感配置和缓存保存在操作系统应用数据目录，而不是 Skill 目录。
- 下载文件由用户管理；断开 Canvas 不会自动删除下载资料。
- 本项目不会主动收集或上传遥测数据。
- Access Token 等同于密码，应设置合理的过期时间并定期更新。

详细安全说明见 [SECURITY.md](SECURITY.md)。

## 已知限制

- 只支持学生账户和当前学生本人可访问的数据。
- 不同学校可能关闭个人 Access Token 或限制 API endpoint。
- Canvas 没有明确关联作业与文件时，匹配结果只是推断，不保证完全准确。
- 学校可自定义课程权限，因此相同 API 在不同机构可能返回不同结果。
- Linux 长期凭证功能取决于本机是否配置安全凭证后端。

## 开发与测试

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/canvas_cli.py
```

测试不得访问真实 Canvas、真实 Keychain 或 Credential Manager。

## 发布前建议

本项目暂未附带开源许可证。公开发布前，请选择并添加合适的许可证，例如 MIT、Apache-2.0 或其他符合你需求的许可证。

