# 版本管理

## 分支

- `main` 保存已验证、可运行的开发基线。
- 功能开发使用短期分支，例如 `codex/voice-chat` 或 `codex/device-display`。
- 每次提交围绕一个明确改动；完成对应检查后合并。

## 版本

初始版本为 `0.1.0-alpha.1`，Git 标签为 `v0.1.0-alpha.1`。它只代表任务管理底座，尚非完整应用。

发布时同步更新 `VERSION`、`CHANGELOG.md` 与 Git 标签。已发布标签不移动，需要修复时创建新版本。

## 提交前

```powershell
python -m unittest discover -s tests -v
git diff --check
git status --short
git diff --cached --stat
```

只提交源码、公开文档与可再分发的素材。不要提交 `.local/`、API 密钥、真实录音、私人聊天或公司资料。
