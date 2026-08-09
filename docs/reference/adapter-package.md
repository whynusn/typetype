# 适配器包格式 v1（ott-adapter）
<!-- 状态: active | 最后验证: 2026-08-09 -->

> 适配器（adapter）是 OTT 生态中可独立分发、校验、签名的源单元。v1 定义包布局与 `adapter.json` 字段；运行时消费与 CI 流水线由 ADR-011 Phase 2.2/2.4 落地。权威 schema 见 `ott-adapter-v1.schema.json`。

## 包布局

| 路径 | 必选 | 说明 |
|:--- |:--- |:--- |
| `adapter.json` | ✅ | 适配器清单：元数据 + 权限 + rights + 载荷指针 + 签名 |
| `code/script.py` | type=script | `fetch_entries() -> list[dict]` 实现（AST 白名单 + 子进程沙箱执行） |
| `code/rule.json` | type=rule | L1 旧字段或 L1.5 `steps` 规则 dict（运行时分流，不混用 `transform` 与 `steps`） |
| `fixtures/responses/` | 可选 | mock HTTP 响应（`adapter.py debug` 用，1.4 极速杯模式） |
| `fixtures/expected.json` | 可选 | 期望输出（`adapter.py validate` 对照） |
| `README.md` | 可选 | 来源说明、抓取许可声明 |

> type=instance 无代码文件：端点声明内联在 `adapter.json` 的 `content.endpoints`。

## adapter.json 字段

| 字段 | 类型 | 必选 | 约束 |
|:--- |:--- |:--- |:--- |
| `protocol` | str | ✅ | 固定 `"ott-adapter"` |
| `version` | int | ✅ | `1` |
| `adapter_id` | str | ✅ | `^[A-Za-z0-9_-]+$`（与 entry_id/source_key 统一） |
| `name` | str | ✅ | 展示名，非空 |
| `repo_id` | str | ✅ | 归属仓库（防跨仓冲突，同源 entry authority 前缀） |
| `type` | str | ✅ | `script` / `rule` / `instance` |
| `label` | str | | 源标签，缺省 = `name` |
| `description` | str | | 摘要 |
| `tags` | list[str] | | 同 manifest tags 归一化 |
| `rights.min_api_level` | int | | 要求客户端 API level ≥ 此值，否则跳过（对照 `CLIENT_API_LEVEL`） |
| `permissions.network` | list[str] | | 域名白名单（子域匹配，声明时生效；未声明回退 `validate_url`） |
| `content.path` | str | script/rule | 相对包根载荷路径（script → `code/script.py`；rule → `code/rule.json`） |
| `content.endpoints` | list[dict] | instance | ott-instance 端点声明（同 manifest 归一化：url/weight/health） |
| `fixtures` | str | | fixtures 目录相对路径，缺省 `"fixtures"` |
| `checksum` | str | ✅ | `sha256:<64hex>`，对 content 载荷文件内容 |
| `signature.pubkey` | str | ✅ | `ed25519:<64hex>` 或裸 64 hex |
| `signature.sig` | str | ✅ | `ed25519:<128hex>` 或裸 128 hex，对 canonical JSON |

> 权限模型：`permissions.network` 声明时生效（2.2 运行时强制）；storage/process 默认 none，无字段可开启。

## 签名与校验

```python
canonical = {k: v for k, v in adapter.items() if k != "signature"}
canonical_bytes = json.dumps(
    canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")
).encode("utf-8")
# verify: Ed25519PublicKey.verify(sig, canonical_bytes)
```

规则：UTF-8、键按字节序排序、无空白、无尾逗号（与 ADR-011 决策 12 / 2.0 一致）；`trust` 不在 adapter.json 顶层（信任状态存客户端订阅侧，不随包分发）。

校验顺序（`adapter.py validate` 计划）：schema → checksum（载荷未变）→ 签名（canonical 匹配）→ 权限白名单 → rights 兼容性 → mock 执行对比 `fixtures/expected.json`。

## 分发与消费（Phase 2.2/2.4 落地）

| 路径 | 现状 |
|:--- |:--- |
| repo manifest source 内联（`ott-script`/`ott-rule`/`ott-instance`） | ✅ 已消费 |
| 仓库内适配器包（manifest source 引用 `adapter_id`） | 🔲 2.2 包内文件拉取 + 2.4 CI 流水线产出 |
| 签名门槛（L3 仅 verified 仓库执行） | ✅ 2.3 已落地（TOFU 流程见 `adapter-signing.md`） |

> 跨仓同步：open-typing-texts 仓 spec 对齐（canonical JSON / minisign 移除）为待确认项，见 ADR-011 待外部确认。
