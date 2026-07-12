<!-- 状态: active | 最后验证: 2026-07-04 -->
# 如何添加新的文本来源（Guide）

> 目标：添加一个从新位置加载文本的功能（如 PDF、Markdown、API 端点）。

---

## 文本来源的二维模型

TypeType 的文本来源由两个正交维度定义：

- **`loader`**：数据从哪来 — 决定 `TextSourceGateway` 路由到哪个 Provider
- **`leaderboard_mode`**：成绩怎么处理 — 决定 `text_id` 解析路径

### 可用的 loader 值

| 值 | 含义 | 已实现的 Provider |
|----|------|------------------|
| `local_file` | 读本地文件 | `LocalTextLoader` |
| `remote_api` | 调用服务端 API | `RemoteTextProvider` |
| `registry` | OTT 开源文库（历史配置值） | `OttTextProvider` |

### 可用的 leaderboard_mode 值

| 值 | text_id 来源 |
|----|-------------|
| `none` | 不提交 |
| `server_resolved` | 服务端直接返回 |
| `local_lookup` | 本地内容 hash 回查 |

---

## 步骤

### 1. 在 `ports/` 定义新 Port（如果现有 Port 不够用）

如果现有 `LocalTextLoader`、`TextProvider`、`Clipboard` 能覆盖你的场景，跳到这里。

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

### 3. 在用户配置 `config.json` 添加配置

```json
{
    "text_sources": {
        "new_source": {
            "label": "新来源",
            "loader": "remote_api",
            "leaderboard_mode": "server_resolved"
        }
    }
}
```

### 4. 在 `text_source_gateway.py` 添加路由

```python
# 在 TextSourceGateway.load_from_plan() 中添加
if source.loader == Loader.NEW_LOADER:
    return self._route_to_new_source(source)
```

### 5. 在 `main.py` / `container.py` 装配

```python
# container.py
new_source_provider = NewSourceRepository(runtime_config)
# 在 TextSourceGateway 构造时注入
```

### 6. 写测试

```bash
# tests/test_new_source_repository.py
# tests/test_text_source_gateway.py  # 新增路由分支
```

### 7. 更新文档

- `docs/reference/config.md`（新来源的字段）
- `CHANGELOG.md`（用户可见变更）

---

## 常见陷阱

1. **不要**在 Adapter 中做来源路由——路由在 Gateway 中
2. **不要**让 Port 依赖 Qt 类型——Port 是纯 Python 协议
3. **不要**在主线程加载文本——统一走 Worker
4. 新增 Port 后记得在 `container.py` 中正确装配
5. `leaderboard_mode` 仅影响 text_id 决策，不影响加载路径
