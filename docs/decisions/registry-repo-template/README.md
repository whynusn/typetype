# open-typing-texts

> 开源打字文本注册表。为打字练习应用提供静态 JSON 文本源，由 GitHub Actions CI 生成、客户端只读拉取。

**命名说明**：`open-typing-texts` 不绑定任何特定客户端。它是打字圈的开放文本内容标准，任何打字练习应用（typetype、TypeSunny、其他）都可接入。

## 仓库结构

```
open-typing-texts/
├── README.md                     ← 本文件：贡献指南
├── registry_index.json           ← 声明式索引（CI 自动生成）
├── content/                      ← 各文本源正文 JSON
│   ├── daily.json                ← 每日一文
│   ├── gushiwen-300.json         ← 古诗文 300 首
│   └── community-xxx.json        ← 社区贡献
├── scripts/                      ← CI 抓取/解析脚本
│   ├── fetch_daily.py
│   └── gen_index.py
└── .github/workflows/
    ├── daily.yml                 ← 每日 0 点 cron + 手动触发
    └── weekly-static.yml         ← 每周全量刷新
```

## 接入方式

任何打字练习应用只需配置一个 `primary_url` 指向本仓库的 GitHub Pages 地址：

```
https://open-typing-texts.github.io/   ← 启用 GitHub Pages 后生效
```

客户端发起 HTTP GET：
- `GET /registry_index.json` — 获取文本源目录
- `GET /content/{source_key}.json` — 获取单篇正文

详见 `registry_index.json` 文件中的 schema 注释。

## 贡献指南

### 1. 添加新文本源

1. 往 `content/` 添加 `source_key.json`（格式见下方 schema）
2. 在 `scripts/gen_index.py` 中添加元数据或提交 `registry_index.json` 更新
3. 提交 PR

### 2. 文本内容 JSON schema

```json
{
  "source_key": "daily",
  "content": "这里是正文内容，支持换行符。",
  "title": "标题（可选）",
  "text_id": null,
  "metadata": {
    "description": "描述",
    "category": "daily",
    "tags": ["日常", "短文"]
  }
}
```

**字段说明**：

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| `source_key` | `str` | ✅ | 唯一标识，匹配文件名（不含 `.json`），只含字母数字/下划线/连字符 |
| `content` | `str` | ✅ | 正文内容，支持 `\n` 换行 |
| `title` | `str` | ❌ | 显示标题 |
| `text_id` | `int | null` | ❌ | 服务端 text_id（用于排行榜），通常为 null |
| `metadata` | `dict` | ❌ | 扩展元数据（description、category、tags 等） |

**限制**：单文件 ≤ 1MB（见 ADR-008 `max_content_bytes` 限制）。

### 3. registry_index.json schema

```json
{
  "version": 1,
  "updated_at": "2026-07-05T00:00:00Z",
  "sources": [
    {
      "id": 0,
      "source_key": "daily",
      "label": "每日一文",
      "description": "CI 每日精选",
      "category": "daily",
      "update_freq": "daily",
      "has_ranking": false
    }
  ]
}
```

### 4. CI workflow

本仓库有两条 CI：
- **daily.yml**：每日 0 点自动抓取并更新 `content/daily.json`
- **weekly-static.yml**：每周全量刷新所有静态文集

贡献者也可通过 `workflow_dispatch` 手动触发。

## 安全模型

> 抓取/解析脚本**仅在 GitHub Actions CI 阶段运行**，产物为纯 JSON。客户端只通过 HTTP GET 拉取 JSON，**从不执行任何远程代码**。无 RCE 风险。

## 许可证

内容采用 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) 许可证。
代码采用 MIT 许可证。
