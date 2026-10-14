# open-typing-texts

> 历史模板（已废弃）。此文档记录早期 registry/CI 抓取方案，不能作为新项目或新贡献流程使用。当前方案以 OTT Core v1 为准：贡献者本地抓取与验证，CI 不抓取第三方内容，不提交真实 `content/`。

**命名说明**：`open-typing-texts` 不绑定任何特定客户端。它是打字圈的开放文本内容标准，任何打字练习应用（typetype、TypeSunny、其他）都可接入。

## 仓库结构

```
open-typing-texts/
├── README.md                     ← 本文件：贡献指南
├── registry_index.json           ← 声明式索引（CI 自动生成）
├── content/                      ← 各文本源正文 JSON
│   ├── static-classic-sentences.json   ← 经典中文短句（静态示例）
│   ├── static-pinyin-practice.json     ← 拼音声调练习（静态示例）
│   ├── jisubei-2026-07-05.json         ← 历史示例（不再由 CI 生成）
│   └── ...
├── scripts/                      ← 历史抓取/解析脚本
│   ├── fetch_daily.py            ← 每日一文抓取脚本（本地运行）
│   └── gen_index.py              ← 索引生成脚本（历史）
└── .github/workflows/
    ├── daily.yml                 ← 每日 0 点 cron + 手动触发
    └── weekly-static.yml         ← 每周全量刷新
```

## 接入方式

任何打字练习应用只需配置一个 `primary_url` 指向本仓库的 CDN 地址：

```
# 主地址（jsDelivr CDN）
https://cdn.jsdelivr.net/gh/whynusn/open-typing-texts@main/

# 镜像地址（GitHub raw）
https://raw.githubusercontent.com/whynusn/open-typing-texts/main/
```

客户端发起 HTTP GET：
- `GET /registry_index.json` — 获取文本源目录
- `GET /content/{source_key}.json` — 获取单篇正文

详见 `registry_index.json` 文件中的 schema 注释。

### typetype 客户端接入示例

```python
from backend.integration.registry_text_provider import RegistryTextProvider
from backend.config.runtime_config import RegistryConfig

provider = RegistryTextProvider(
    config=RegistryConfig(
        primary_url="https://cdn.jsdelivr.net/gh/whynusn/open-typing-texts@main",
        mirror_url="https://raw.githubusercontent.com/whynusn/open-typing-texts/main",
        cache_ttl_seconds=3600,
    ),
    cache_dir=Path.home() / ".cache" / "typetype" / "registry",
)

# 获取文本源目录
catalog = provider.get_catalog()

# 获取单篇文本
text = provider.fetch_text_by_key("static-classic-sentences")
```

## 贡献指南

### 1. 添加静态文本源

1. 往 `content/` 添加 `source_key.json`（格式见下方 schema）
2. 运行 `python scripts/gen_index.py` 生成/更新索引
3. 提交 PR

### 2. 添加动态文本源（历史方案，禁止新用）

不要在 `.github/workflows/` 下创建 workflow 调用抓取脚本。当前 OTT 贡献流程要求脚本拆分为本地 `fetch_raw()` 与纯 `transform()`，CI 只跑 fixture、schema、静态安全扫描；真实抓取只能由贡献者在本机运行并粘贴 validator 摘要。

### 3. 文本内容 JSON schema

```json
{
  "source_key": "static-classic-sentences",
  "title": "经典中文短句练习",
  "content": "春风又绿江南岸，明月何时照我还。但愿人长久，千里共婵娟。...",
  "text_id": null,
  "metadata": {
    "description": "精选经典中文短句，适合中文打字练习",
    "category": "static",
    "tags": ["经典", "中文", "短句", "练习"],
    "author": "open-typing-texts 维护者",
    "license": "CC0-1.0"
  }
}
```

**字段说明**：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| `source_key` | `str` | ✅ | 唯一标识，匹配文件名（不含 `.json`），只含字母数字/下划线/连字符 |
| `content` | `str` | ✅ | 正文内容，支持 `\n` 换行 |
| `title` | `str` | ❌ | 显示标题 |
| `text_id` | `int | null` | ❌ | 服务端 text_id（用于排行榜），registry 源通常为 null |
| `metadata` | `dict` | ❌ | 扩展元数据（description、category、tags、author、license 等） |

**限制**：单文件 ≤ 1MB（见 typetype ADR-008 `max_content_bytes` 配置）。

### 4. registry_index.json schema

```json
{
  "version": 1,
  "updated_at": "2026-07-05T00:00:00Z",
  "sources": [
    {
      "id": 1001,
      "source_key": "static-classic-sentences",
      "label": "经典中文短句",
      "description": "精选经典中文短句，适合中文打字练习",
      "category": "static",
      "update_freq": "static",
      "has_ranking": false
    },
    {
      "id": 2001,
      "source_key": "jisubei-daily",
      "label": "极速杯每日挑战",
      "description": "极速杯每日打字挑战",
      "category": "jisubei",
      "update_freq": "daily",
      "has_ranking": true
    }
  ]
}
```

### 5. CI workflow（历史方案，禁止新用）

早期设计曾考虑用 `daily.yml` 自动抓取并更新动态文本源。该方向已经被 ADR-009 否决：CI 不应代表项目方访问第三方内容源，也不应生成或提交真实文本内容。新方案只允许无网络 schema/fixture/validator/script-safety 检查。

## 安全模型

> 抓取/解析脚本**仅在 GitHub Actions CI 阶段运行**，产物为纯 JSON。客户端只通过 HTTP GET 拉取 JSON，**从不执行任何远程代码**。无 RCE 风险。

具体安全措施：
- 客户端使用 `httpx.Client(trust_env=False)` 防止代理劫持
- 源文件有 `source_key` 白名单验证（禁止 `..` 路径穿越）
- 客户端缓存层有文件大小限制（`max_content_bytes`）
- 写入使用原子操作（tmp + replace），避免半写入状态

## 许可证

内容采用 [CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/) 公共领域贡献。
代码采用 MIT 许可证。
