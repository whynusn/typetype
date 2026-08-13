<!-- 状态: active | 最后验证: 2026-08-13 -->
# 如何添加新的文本来源（Guide）

> 目标：添加一个从新位置加载文本的功能（如 PDF、Markdown、OTT 订阅源）。
> v2（ADR-013）起 `text_sources` 仅剩本地文件；远程内容走 OTT Repo 订阅或独立 Pipeline。

---

## 两条路径

| 想加什么 | 走哪条路径 |
|:---|:---|
| 本地练习文件（txt 等） | 路径 A：`config.json` `text_sources` 加条目（零代码） |
| 远程/静态文本（文章、规则抓取、脚本抓取） | 路径 B：订阅 OTT Repo 源仓库（`source_repos`），或新增独立 Provider 栈 |

---

## 路径 A：添加本地文本来源（零代码）

在 `~/.config/typetype/config.json`（`schema_version=2`）的 `text_sources` 增加条目：

```json
{
    "schema_version": 2,
    "text_sources": {
        "new_local": {
            "label": "新本地来源",
            "local_path": "/absolute/path/to/text.txt"
        }
    }
}
```

或通过设置页/载文中心本地文本导入（`UploadTextAdapter` 写本地文件并更新配置）。

验证：

```bash
uv run pytest tests/test_upload_text_adapter.py
```

## 路径 B：添加远程文本来源（OTT Repo 订阅）

1. 在 OTT Repo 源仓库中定义源（ott-instance / ott-rule / ott-script），见 [ott-repo-governance.md](ott-repo-governance.md) 与 open-typing-texts 仓 `docs/repo-manifest-spec.md`。
2. 客户端侧订阅源仓库 manifest URL：

```json
{
    "source_repos": [
        { "url": "https://example.org/ott-repo.json", "enabled": true }
    ]
}
```

或通过设置页「源仓库」面板（`RegistryAdapter` 后台 Worker 拉取 manifest）。

3. 无需改 typetype 代码即可消费 `source_repos` 中的 ott-instance / ott-rule 源；ott-script 源需启用 L3（`ott.scripts_enabled`，Windows 默认关闭）。

## 路径 C：新增独立 Provider 栈（第三方实时源，如晴发文 / AI）

> 仅当来源不是 OTT 协议、且为即时交互 API 时使用。参考晴发文（`wenlai_provider.py` → `wenlai_gateway.py` → `load_wenlai_text_usecase.py` → `wenlai_adapter.py`）。

### 1. 在 `ports/` 定义新 Port（如果现有 Port 不够用）

如果现有 `LocalTextLoader`、`WenlaiProvider`、`Clipboard` 能覆盖你的场景，跳到这里。

```python
# ports/new_source.py
from abc import ABC, abstractmethod

class NewSourceProvider(Protocol):
    @abstractmethod
    def load_text(self, source_id: str) -> str: ...

    @abstractmethod
    def list_sources(self) -> list[TextCatalogItem]: ...
```

### 2. 在 `integration/` 实现 Port

```python
# integration/new_source_repository.py
from ports.new_source import NewSourceProvider

class NewSourceRepository(NewSourceProvider):
    def load_text(self, source_id: str):
        # 你的实现
        ...

    def list_sources(self):
        return [...]
```

### 3. 在 `main.py` / `container.py` 装配

```python
# container.py
new_source_provider = NewSourceRepository(runtime_config)
# 在对应 Gateway / Adapter 构造时注入
```

### 4. 写测试

```bash
# tests/test_new_source_repository.py
# tests/test_new_source_gateway.py  # 新增路由分支（如需要）
```

### 5. 更新文档

- `docs/reference/config.md`（新来源的字段，如需配置）
- `CHANGELOG.md`（用户可见变更）

---

## 常见陷阱

1. **不要**在 Adapter 中做来源路由——路由在 Gateway（本地）或 `RegistryAdapter`（OTT 订阅）中
2. **不要**让 Port 依赖 Qt 类型——Port 是纯 Python 协议
3. **不要**在主线程加载文本——统一走 Worker（`TextLoadWorker` / `RegistryAdapter`）
4. 新增 Port 后记得在 `container.py` 中正确装配
5. `text_sources` 仅接受本地文件条目；远程来源不要写进 `text_sources`
6. 网络来源的正文/条目大小受 `ott.max_content_bytes` 限制（1 MB 默认）
