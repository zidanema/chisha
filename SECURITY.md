# Security Policy

chisha 是个人 hobby 项目, 非商业, **没有 SLA 承诺**.

## Reporting a Vulnerability

发现安全问题 (credential 泄漏 / RCE / 数据越权等), 请发邮件:

- **Email**: <mzd5646241@gmail.com>

或在 GitHub 开 issue (低敏感问题). 不保证响应时间, 这是 spare-time 项目, best effort.

## Scope

涉及本仓代码 + 默认配置. 不含:
- 用户自己的 `~/.chisha/` 状态文件 (用户责任)
- 用户配置的 LLM provider API key (`~/.chisha/.env` 等, 用户责任)
- 第三方依赖 (上游报)
