<!-- 状态: active | 最后验证: 2026-06-04 -->
# 开发环境设置（Guide）

> 目标：在本地搭建可运行的开发环境。

---

## 环境要求

- **Python** 3.12+
- **uv** 0.9.26+（包管理器）
- **系统**：Linux (Wayland/X11)、macOS 或 Windows

## 安装步骤

```bash
# 1. 克隆项目
git clone https://github.com/whynusn/typetype.git
cd typetype

# 2. 安装依赖
uv sync

# 3. 启动应用
uv run python main.py
```

## 验证

```bash
# 跑测试
uv run pytest -v

# 代码检查
uv run ruff check .
uv run ruff format --check .

# 所有检查都通过
uv run ruff check . && uv run ruff format --check . && uv run pytest
```

## 可选：配置 API 服务端地址

1. 首次启动时 `~/.config/typetype/config.json` 自动生成
2. 编辑用户配置文件，设置 `base_url` 为你的后端地址
3. 或使用运行时配置：设置页面输入地址 → 应用

## 日志调试

```bash
# 开启 debug 日志
TYPETYPE_DEBUG=1 uv run python main.py

# 或精确控制
TYPETYPE_LOG_LEVEL=debug uv run python main.py
```

## 平台权限

| 平台 | 键盘监听权限 |
|:--- |:--- |
| Linux Wayland | `input` 组（可选，不满足则降级） |
| Linux X11 | 通常不需要 |
| macOS | 系统偏好设置 → 隐私 → 辅助功能 |
| Windows | 通常不需要 |

不满足权限时，应用会优雅降级：码长/击键统计回退到 QML 路径，基础打字功能不受影响。
