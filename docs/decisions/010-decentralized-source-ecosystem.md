# ADR-010: 去中心化文本源生态（OTT Repo 控制面）

<!-- 状态: accepted | 决策日期: 2026-07-26 | 最后验证: 2026-07-27 -->

> Phase 1（多 authority 客户端，零协议变更）已于 2026-07-26 落地。Phase 2（OTT Repo v1 定稿：spec + schema + fixtures + authority_id/repo_url 增量字段）已于 2026-07-27 落地。Phase 3（L1 声明式规则解释器 + L3 ott-script 沙箱脚本源）已于 2026-07-27 落地。Phase 4+（签名信任、官方默认目录、ott:// 深链）待后续推进。

> 本 ADR 是 ADR-009 的后续。核心结论：**OTT Core v1 数据面保持不变；新增独立的 OTT Repo 协议构件承载控制面（订阅、信任、发现）**，使 typetype 演进为 mihon / kazumi / 开源阅读式的去中心化文本源生态客户端。完整设计见 [docs/designs/decentralized-source-ecosystem.md](../designs/decentralized-source-ecosystem.md)，协议草案见 open-typing-texts 仓 `docs/repo-manifest-spec-draft.md`。

## 背景

ADR-009 完成 OTT Core v1 数据面后，生态仍停在"任何人可自托管"阶段，未达到"客户端可订阅多个、可发现新实例"：

- `RegistryConfig` 是单 authority（`primary_url` + `mirror_url` 指同一仓的镜像），客户端无法订阅多实例。
- 没有"源仓库"概念：mihon 的 extension repo、legado 的订阅链接、kazumi 的规则仓库本质都是**可分发的源清单**，OTT 无对应物。
- 没有信任分级（纯数据 / 声明式规则 / 可执行脚本的风险敞口无设计）与发现机制。
- `authority` 只出现在进度键 `ott:{authority}:{entry_id}@{revision_id}` 中，未升格为身份体系。

## 选项

| 方案 | 描述 | 判断 |
|:---|:---|:---|
| A. 控制面叠加 | Core v1 不动，新增独立 OTT Repo 构件（manifest + 信任 + 目录） | ✅ 选中 |
| B. 推翻重做统一大协议 | 重写"OTT v2"把数据面控制面合一 | ❌ Core v1 刚稳定、兼容测试包刚建立，重写浪费且违背"稳定数据面"承诺 |
| C. 仅客户端多配置 | typetype 支持多 URL 配置，不标准化 repo 格式 | ❌ 生态无法形成：repo 格式不标准则各仓各自为政（legado 书源格式碎片化的教训） |
| D. mihon APK 式可执行扩展 | 分发可执行抓取代码到客户端 | ❌ 签名/审核/兼容性负担重，且可执行物是法律攻击面；违背声明式哲学 |

## 决策

1. **三层概念模型**：Directory（可选，repo-of-repos，不嵌套）→ Repo（源清单，`ott-repo.json`）→ Instance / Rule / Bridge（源）→ Entry（Core v1 数据面）。
2. **Repo Manifest 三种源类型**：`ott-instance`（OTT 端点 + 镜像列表）、`ott-rule`（内联声明式规则）、`ott-bridge`（即时 API 桥，凭据本地）。
3. **四级信任模型**：L0 数据实例、L1 声明式规则（客户端受限解释器，无任意代码）、L2 桥接源（凭据本地持有）、L3 抓取脚本（**协议禁止进入 Repo 分发**，仅用户本地 adapter 侧）。不变式：客户端从网络订阅的一切内容均无任意代码执行面。
4. **签名为徽章非门槛**：可选 minisign/ed25519 + TOFU 固定；UI 显示验证徽章，永不作为准入强制。
5. **authority 身份规范**：反向域名 / `key:ed25519:<指纹>` / `local`；实例经 `ott.json` 与 `capabilities` 可选声明 `authority_id`（Core 向后兼容增量）。条目 URN `ott:{authority}:{entry_id}@{revision_id}` 正式化，深链 `ott://{authority}/{entry_id}`。
6. **客户端演进**：`RegistryConfig` → `SourceReposConfig` 订阅列表（旧配置自动迁移）；`OttTextProvider` 之上加联邦聚合层；trait flags 由 manifest × capabilities 运行时合成；订阅管理进载文中心。
7. **治理**：官方默认目录可关可换；blocklist 是客户端本地策略而非协议强制；OTT Core 与 OTT Repo 独立语义化版本；兼容测试包扩展到 manifest fixtures。

## 影响

- **typetype**：新增设计文档 `docs/designs/decentralized-source-ecosystem.md`；实现按五阶段路线（Phase 1 多 authority 客户端为零协议变更，可立即启动）。
- **open-typing-texts**：新增 `docs/repo-manifest-spec-draft.md`（OTT Repo v1 草案）；Phase 2 时补 schema 与 fixtures。`OTT_SPEC.md`（Core v1）不动。
- **兼容性**：现有单 authority 用户经配置自动迁移无缝过渡；`registry.primary_url` 语义保留为"默认订阅"。
- **文档**：ADR-008/009 的三层模型与 Phase 划分继续有效；本 ADR 的 Phase 1-5 是其后续路线而非替代。
