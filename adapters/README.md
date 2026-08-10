# 适配器包（Adapters）

OTT 文本源适配器包存放目录。贡献者用 SDK 脚手架搭建：

```bash
uv run python scripts/adapter.py new <name> --type script|rule|instance
```

- 包格式规范：[open-typing-texts docs/adapter-package.md](https://github.com/whynusn/open-typing-texts/blob/main/docs/adapter-package.md)
- SDK 工具：[scripts/adapter.py](../scripts/adapter.py)（`new` / `validate` / `sign` / `debug`）

提交前本地验证：`uv run python scripts/adapter.py validate <dir>`。CI 签名流水线见
[.github/workflows/adapter-publish.yml](../.github/workflows/adapter-publish.yml)。
