# typetype 项目开发指南

## 构建、代码检查和测试命令

### 开发环境
- Python 3.12+（在 `.python-version` 中指定）
- 使用 `uv` 作为包管理器（版本 0.9.26+）
- 虚拟环境：`.venv/`

### 构建和运行
```bash
uv sync
uv run python main.py
```

### 测试
测试框架：pytest

```bash
uv run pytest              # 所有测试
uv run pytest path/to/file.py  # 特定文件
uv run pytest -k test_name     # 单个函数
uv run pytest -v              # 详细输出
```

## 代码风格指南

### Python 代码风格

**导入语句**
- 顺序：标准库 → 第三方包 → 本地导入
- 分组导入：先用没有逗号的单独导入，再分组导入（用逗号分隔）
- 同包内的模块使用相对导入（如 `from . import Crypt`）
- 将所有导入放在文件顶部

```python
# 好的写法
import os
from typing import Tuple
from PySide6.QtCore import QObject, Signal
```

**命名规范**
- 类名：PascalCase（如 `Backend`、`SystemIdentifier`）
- 函数和变量：snake_case（如 `get_system_info`、`_handle_events`）
- 私有方法：用 `_` 前缀（如 `_calculate_speed`）
- 信号：PascalCase，以 `Changed` 结尾（如 `typeSpeedChanged`）

**类型提示**
- 函数参数和返回值必须使用类型提示
- 使用标准 Python 类型（str, int, bool, list, dict 等）
- 复杂类型使用 typing 模块（Optional, Tuple, Dict, Any 等）

**文档字符串**
- 使用中文文档字符串
- 文档参数和返回值

```python
def encrypt(obj):
    """
    加密函数
    
    参数:
        obj: 字符串或可 JSON 序列化的对象
    
    返回:
        Base64 编码的加密字符串
    """
    pass
```

**错误处理**
- 对外部 API 调用和系统操作使用 try-except 块
- 用 print 语句记录错误
- 尽可能捕获特定异常，一般异常使用 Exception
- 优雅处理不影响应用稳定性的错误

```python
# 好的写法
try:
    newText = GetSaiWen.get_sai_wen(url)
except Exception as e:
    print(f"错误: {e}")
    return None
```

**类设计**
- 从 `QObject` 继承以实现 Qt 集成
- 使用信号在 Python 和 QML 之间通信
- 使用槽函数接收 QML 的调用

### Qt/QML 集成

**属性暴露**
- 使用 `@Property` 装饰器将 Python 属性暴露给 QML
- 指定 notify 信号以实现响应式更新

**信号/槽通信**
- 信号：从 Python 发射到 QML
- 槽：在 Python 中定义并从 QML 连接
- 使用类型安全的参数传递（如 `Signal(int, str)`）

**定时器使用**
- 使用 QTimer 进行定期更新（如速度计算使用 100ms）
- 将定时器实例作为实例变量存储
- 需要时正确启动和停止定时器

## 项目结构

```
typetype/
├── main.py                    # 应用入口点
├── pyproject.toml             # 项目配置和依赖
├── uv.lock                    # 锁定的依赖
├── src/
│   ├── backend/
│   │   ├── backend.py         # 主要后端逻辑
│   │   ├── crypt.py           # 加密工具
│   │   ├── get_sai_wen.py     # 网络请求处理
│   │   ├── global_key_listener.py  # Linux 键盘监听器
│   │   ├── system_identifier.py   # 操作系统检测
│   │   ├── score_data.py      # 成绩数据管理
│   │   └── text_properties.py    # 文本处理
│   └── qml/                   # QML UI 文件
│       ├── Main.qml
│       ├── UpperPane.qml
│       ├── LowerPane.qml
│       ├── EndDialog.qml      # 打字结束对话框
│       └── ...
```

## 特殊注意事项

### 平台检测和权限
- 检查 Linux 特定功能（GlobalKeyListener）
- 检测显示服务器（Wayland vs X11）
- 为不支持的平台提供优雅的降级处理
- **Wayland 环境**：需要将用户加入 input 组或使用 sudo 运行

### QML 集成
- 后端通过 `setContextProperty` 暴露为 QML 的单例
- QML 文件引用后端属性和信号
- 使用 `src.backend` 导入路径访问 Python 模块

### 依赖管理
- 所有依赖列在 `pyproject.toml` 的 `[project.dependencies]` 下
- 使用 `uv sync` 安装/更新依赖
- 锁定文件 `uv.lock` 确保可重现构建
- **注意**: `evdev` 依赖在 Linux 系统上需要 root 权限或 input 组权限

### 测试策略
- 为业务逻辑编写测试（不是 UI 组件）
- 测试 Python 后端时模拟 Qt 对象
- 测试错误处理路径
- 验证类型提示是否正确

### 代码质量
- 保持函数简洁且小（理想情况少于 50 行）
- 避免深层嵌套（超过 3 层）
- 使用描述性的变量和函数名
- 为复杂逻辑添加注释
- 保持与现有代码风格的一致性（包括中文注释的地方）
