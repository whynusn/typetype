# TypeType 客户端项目文档

## 1. 项目概述

TypeType 是一个基于 PySide6 (Qt for Python) 和 RinUI (Fluent Design 风格 QML 组件库) 的桌面打字练习应用程序。项目采用分层架构（领域驱动设计），支持本地和远程文本来源、用户认证、排行榜、文本上传等功能。

## 2. 项目结构

```
typetype/
├── config/                    # 配置文件
│   ├── config.example.json
│   └── config.json
├── data/                      # 本地数据存储
├── deployment/                # 部署相关文件
├── docs/                      # 设计文档
├── resources/                 # 资源文件（字体、图片、文本）
├── RinUI/                     # RinUI 组件库（自定义）
├── skills/                    # 技能文件
├── src/
│   ├── backend/               # Python 后端逻辑
│   │   ├── application/       # 应用层（用例、网关）
│   │   ├── config/            # 运行时配置
│   │   ├── domain/            # 领域层（服务、实体、仓储）
│   │   ├── infrastructure/    # 基础设施层（API 客户端、网络错误）
│   │   ├── integration/       # 集成层（具体实现）
│   │   ├── models/            # 数据模型
│   │   ├── ports/             # 端口接口
│   │   ├── presentation/      # 表示层（Bridge、适配器）
│   │   ├── security/          # 安全相关（JWT 存储）
│   │   └── utils/             # 工具类
│   └── qml/                   # QML 界面文件
│       ├── Main.qml           # 主窗口
│       ├── components/        # 自定义组件
│       ├── pages/             # 页面
│       └── typing/            # 打字相关组件
├── tests/                     # 测试文件
├── main.py                    # 应用程序入口
├── pyproject.toml             # 项目配置
└── README.md                  # 项目说明
```

## 3. 功能清单

### 3.1 核心功能
1.  **打字练习（跟打）**
    -   实时统计：时间、速度（字/分钟）、击键（次/秒）、码长（键/字）、错字数、总字数。
    -   支持富文本显示，高亮当前光标位置。
    -   支持重新打字（F3 快捷键）。
    -   支持从剪贴板加载文本。
    -   支持字体大小调整（Ctrl +/-）。

2.  **文本来源管理**
    -   支持本地文本文件（配置在 `config.json`）。
    -   支持从服务器获取文本（按来源、按 ID）。
    -   文本来源目录可动态加载。

3.  **用户系统**
    -   登录/注销（基于 JWT）。
    -   令牌自动刷新。
    -   用户信息显示（昵称、用户名）。

4.  **排行榜**
    -   按文本查看排行榜（支持分页）。
    -   显示用户排名、速度、击键、码长、准确率、错字数、时长、日期。
    -   支持刷新排行榜数据。

5.  **薄弱字统计**
    -   记录每个汉字的错误次数、总次数、错误率、平均用时。
    -   按错误率排序，突出显示高错误率汉字。
    -   数据本地持久化（SQLite）。

6.  **文本上传**
    -   支持上传自定义文本到本地或云端。
    -   上传时需填写标题、内容、选择来源。
    -   云端上传需登录。

7.  **历史记录**
    -   记录每次打字练习的速度、击键、码长、错字数、字数、时间、日期。
    -   以表格形式显示在打字页面底部。

8.  **设置（占位）**
    -   设置页面正在建设中。

### 3.2 UI/UX 设计
-   采用 Fluent Design 风格，使用 RinUI 组件库。
-   主界面布局：
    -   顶部工具栏：Logo、文本来源选择器、载文、剪贴板载文、重打、排行榜切换按钮。
    -   左侧主要内容区（可滚动）：
        -   UpperPane：显示待打文本（只读）。
        -   ScoreArea：实时统计信息（时间、速度、击键、码长、字数）。
        -   LowerPane：用户输入区域。
        -   HistoryArea：历史记录表格。
    -   右侧排行榜面板（可切换显示）：
        -   显示当前文本的排行榜。
        -   显示我的排名（如果已登录）。
-   薄弱字页面：以卡片形式展示，包含汉字、错误次数、总次数、错误率进度条、平均用时、最后出现时间。
-   文本排行榜页面：左侧为文本列表（按来源分组），右侧为排行榜表格（支持水平滚动）。
-   个人中心：登录/注销，显示用户信息。
-   上传文本页面：表单填写，支持上传到本地或云端。

## 4. API 端点使用情况

### 4.1 文本相关
| 端点 | 方法 | 描述 | 使用位置 |
|------|------|------|----------|
| `/api/v1/texts/catalog` | GET | 获取所有可用文本来源 | `LeaderboardFetcher.get_catalog()`, `RemoteTextProvider.get_catalog()` |
| `/api/v1/texts/latest/{sourceKey}` | GET | 获取指定来源的最新文本 | `LeaderboardFetcher.get_latest_text_by_source()`, `RemoteTextProvider.fetch_text_by_key()` |
| `/api/v1/texts/by-source/{sourceKey}` | GET | 获取来源下所有文本的摘要列表 | `LeaderboardFetcher.get_texts_by_source()` |
| `/api/v1/texts/{textId}` | GET | 通过文本 ID 获取文本详情 | `LeaderboardFetcher.get_text_by_id()` |
| `/api/v1/texts/{textId}/leaderboard` | GET | 获取指定文本的排行榜 | `LeaderboardFetcher.get_leaderboard()` |
| `/api/v1/texts/upload` | POST | 上传文本（需认证） | `TextUploader.upload()` |
| `/api/v1/texts/by-client-text-id/{clientTextId}` | GET | 通过客户端文本 ID 查找文本 | `RemoteTextProvider.fetch_text_by_client_id()` |

### 4.2 成绩相关
| 端点 | 方法 | 描述 | 使用位置 |
|------|------|------|----------|
| `/api/v1/scores` | POST | 提交成绩（需认证） | `ApiClientScoreSubmitter.submit()` |

### 4.3 认证相关
| 端点 | 方法 | 描述 | 使用位置 |
|------|------|------|----------|
| `/api/v1/auth/login` | POST | 登录 | `ApiClientAuthProvider.login()` |
| `/api/v1/auth/refresh` | POST | 刷新令牌 | `ApiClientAuthProvider.refresh_token()` |
| `/api/v1/users/me` | GET | 验证令牌并获取用户信息 | `ApiClientAuthProvider.validate_token()` |

## 5. 技术细节

### 5.1 技术栈
-   **前端**：PySide6 (Qt for Python) + QML + RinUI (自定义 Fluent Design 组件库)
-   **后端**：Python 3.12，分层架构（领域驱动设计）
-   **HTTP 客户端**：httpx
-   **本地存储**：SQLite（用于字符统计数据）
-   **安全**：JWT 认证，令牌存储在系统密钥环（通过 `SecureStorage`）

### 5.2 关键组件
-   **Bridge**：QML 与 Python 后端的通信桥梁，负责属性代理、信号转发、Slot 入口。
-   **ApiClient**：通用 HTTP 客户端，集中处理请求和异常。
-   **TypingService**：打字业务逻辑，计算实时统计数据。
-   **CharStatsService**：字符统计服务，管理薄弱字数据。
-   **AuthService**：认证服务，管理登录状态和令牌。
-   **LeaderboardFetcher**：排行榜数据获取器。

### 5.3 平台兼容性
-   支持 Windows、macOS、Linux。
-   在 Linux Wayland 平台上，使用 `GlobalKeyListener` 全局监听键盘事件（因为 Qt 在 Wayland 下无法正确捕获输入法事件）。

### 5.4 配置
-   配置文件：`config/config.json`（或 `config.example.json`）。
-   主要配置项：
    -   `base_url`：服务器地址。
    -   `api_timeout`：API 请求超时时间。
    -   `text_sources`：文本来源配置（本地文件路径、是否有排行榜）。

## 6. 构建与运行

### 6.1 依赖
-   Python 3.12+
-   PySide6
-   httpx
-   darkdetect
-   RinUI（项目内自定义组件）

### 6.2 运行
```bash
# 安装依赖（推荐使用 uv）
uv sync

# 运行应用程序
python main.py
```

### 6.3 配置
1.  复制 `config/config.example.json` 为 `config/config.json`。
2.  修改 `config.json` 中的 `base_url` 为实际服务器地址。
3.  根据需要调整 `text_sources` 配置。

## 7. 未来改进方向

1.  完善设置页面（字体、主题、快捷键等配置）。
2.  添加用户注册功能。
3.  支持更多排行榜类型（日榜、周榜、总榜）。
4.  支持文本分类和标签。
5.  支持练习模式（如限时练习、错字重练）。
6.  添加音效和视觉反馈。
7.  支持多语言（i18n）。

---
*文档生成时间：2026-04-16*
*基于项目代码分析*