# OTT Repo v1.2 提案 PR 草稿（供 open-typing-texts 仓使用）

- **日期**: 2026-08-15
- **状态**: 提案草稿，待上游评审
- **目标仓库**: `whynusn/open-typing-texts`（或当前本地 `~/work/open-typing-texts`）
- **客户端依据**: typetype `docs/designs/open-library-ux-ott-repo-alignment.md`
- **原则**: 全部为 additive；不破坏 v1.0/v1.1 manifest 与 OTT Core v1 数据面。

---

## 1. PR 标题与摘要

**Title**: `spec: OTT Repo v1.2 — source display metadata, common refresh policy, derived authority, extension policy`

**Summary**:

客户端 typetype 在开源文库落地过程中发现：源卡片缺少可展示元数据、刷新策略只定义在 rule 内部、script authority 存在多脚本冲突、若干 typetype 事实扩展未纳入 schema、目录订阅缺少客户端行为规范。本 PR 以 additive 方式补齐：

1. 公共 source display metadata（`description/rights_summary/homepage`）；
2. 公共 `refresh` 策略（替代 rule 专属 `schedule`，并加入 `weekly`）；
3. script derived authority 改为 URL 指纹命名空间；
4. 扩展字段政策（`x-` 前缀）并正式化 `entry_limit` / TUF-lite 字段；
5. Directory Client Behavior；
6. Client Presentation Guidance（trust badge / tier / health / L3 跳过提示）；
7. Core EntrySummary 小修（`category`、`fetched_at` 语义、derived entry_id）。

---

## 2. 具体变更清单

### 2.1 `docs/repo-manifest-spec.md`

| 位置 | 变更 |
|:--|:--|
| Version Vocabulary | Repo 版本补 `1.2`；说明 v1.2 additive，客户端最低仍支持 `1.0` |
| Repo Manifest 示例 | 示例 manifest 展示 `entry_limit`、`revocations/expires_at/snapshot_hash`（可选） |
| Field rules | 新增 `entry_limit`（可选，正整数，repo 级默认条目保留上限；客户端 UI 可据此展示 `N / M`） |
| Source Types 公共字段 | 新增小节「Common Source Fields」：`label`（v1.2 建议 required，兼容 fallback 规则）、`description`、`rights_summary`、`homepage`、`tags`、`default_enabled`、`refresh` |
| `ott-rule` | `schedule` 标记 deprecated，指向公共 `refresh`；`schedule` 继续可解析到 v1.3 |
| `ott-bridge` / `ott-script` | 同样支持公共 `refresh` 与 display metadata |
| §Authority Identity | script authority 改为 `script:{sha256(payload_url)[:12]}`；进度键同步；给出多脚本冲突的反例 |
| §Trust | 增加 Client Presentation Guidance：客户端应展示 trust badge；L3 非 verified 跳过时给出可操作提示 |
| §Client Behavior | 新增 Directory Client Behavior：目录只浏览 + 显式添加、不自动订阅、不嵌套 |
| §Extension Policy | 新增小节：未知字段 MUST 以 `x-` 为前缀；`additionalProperties: true` 仅为兼容，正式字段以 schema 为准 |
| TUF-lite | 正式化 `expires_at` / `snapshot_hash` / `revocations` 语义（与 typetype `RepoManifestCache` 现有行为对齐） |

### 2.2 `schemas/ott-repo.schema.json`

```json
{
  "$defs": {
    "source_common": {
      "type": "object",
      "properties": {
        "label": { "type": "string", "minLength": 1 },
        "description": { "type": "string" },
        "rights_summary": { "type": "string" },
        "homepage": { "type": "string", "format": "uri" },
        "tags": { "type": "array", "items": { "type": "string" } },
        "default_enabled": { "type": "boolean", "default": true },
        "refresh": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "mode": { "enum": ["manual", "hourly", "daily", "weekly"] },
            "cache_ttl_seconds": { "type": "integer", "minimum": 0 }
          }
        }
      }
    },
    "tuf_lite": {
      "type": "object",
      "properties": {
        "expires_at": { "type": "string", "format": "date-time" },
        "snapshot_hash": { "type": "string" },
        "revocations": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": false,
            "properties": {
              "content_hash": { "type": "string" },
              "reason": { "type": "string" },
              "pubkey": { "type": "string" }
            }
          }
        }
      }
    }
  },
  "properties": {
    "entry_limit": { "type": "integer", "minimum": 1 },
    "expires_at": { "type": "string", "format": "date-time" },
    "snapshot_hash": { "type": "string" },
    "revocations": { "$ref": "#/$defs/tuf_lite/properties/revocations" }
  }
}
```

各 source `allOf.then.properties` 增加：

```json
"description": { "type": "string" },
"rights_summary": { "type": "string" },
"homepage": { "type": "string", "format": "uri" },
"refresh": { "$ref": "#/$defs/source_common/properties/refresh" }
```

`ott-rule.rule.schedule` 保留但 `"deprecated": true`（JSON Schema 2020-12 支持 `deprecated` 注解）。

### 2.3 `OTT_SPEC.md`

```diff
 EntrySummary:
 + category?: string
 + fetched_at?: string   # 服务端抓取时间；updated_at 为内容更新时间
 + charCount 标注 legacy alias，新发布内容统一 char_count
 Identity Rules:
 + derived entry_id 规则：无显式 entry_id 时 MUST 使用符合
   ^[A-Za-z0-9_]+$ 的稳定哈希，禁止冒号前缀
 Instance Identity:
 + repo_url / authority_id 保持 1.1 candidate 不变
```

### 2.4 `tests/fixtures/ott/repo-manifests/`

新增：

- `v1.2-common-fields.json`：四种 source 类型都携带公共 metadata 与 refresh；
- `v1.2-entry-limit.json`：`entry_limit` 正式字段；
- `v1.2-directory.json`：directory + repository-ref；
- `v1.2-script-authority.json`：文档化 `script:{sha25612}`；
- `invalid/entry-id-with-colon.json`：验证桥接派生 ID 不再出现冒号。

### 2.5 `ott_adapter` 参考实现同步

- `core_validator.py` / `content_validator.py`：接受公共字段；entry_id 校验沿用 Core pattern。
- `server_admin_script_mutations.py`：`weekly` 与公共 refresh 模式对齐。
- `frontend.html`（如纳入本 PR）：source 卡片显示 tier/trust/last run 状态（可拆后续 PR）。

---

## 3. typetype 客户端对应消费计划

| 标准字段 | typetype 消费位置 | 状态 |
|:--|:--|:--|
| `refresh.mode` | `refresh_policy.infer_policy` + `_declared_refresh_policy` | 已实现（rule.schedule 兼容） |
| `default_enabled/tags`（rule/bridge/script） | `ott_repo_manifest._normalize_source` | 已实现 |
| `entry_limit` | 兼容读 `max_entries` 后再切正式字段 | 待上游定稿 |
| script authority | 已为 `script:{sha256(url)[:12]}` | 实现已一致，规范待改 |
| trust badge / L3 skip | `RepoEntriesPanel` / `SourceInfoDialog` / `RepoConfigDialog` | 已实现基础版 |
| directory preview | `Federation.preview_manifest` + 添加订阅弹窗 | 已实现 |
| source health | `SourceStatusStore` + `sourceStatusChanged` | 已实现 |

---

## 4. Review 关注点

1. `label` 是否在 v1.2 设为 required（兼容迁移的 fallback 顺序是否清晰）；
2. script authority 是采纳本 PR 的 URL 指纹，还是保留单一 `script` 并定义冲突解决；
3. `entry_limit` 命名与 `max_entries` 兼容窗口；
4. TUF-lite 字段是否应与签名/撤销管理文档（`docs/signing-key-management.md`）合并；
5. directory 是否需要 `requires` 能力协商（本 PR 建议不引入，保持目录简单）。
