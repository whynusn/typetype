# 适配器签名方案（Phase 2.0 设计）

<!-- 状态: active（2.0 已定稿）| 创建: 2026-08-08 | 最后验证: 2026-08-10 | 关联: ADR-011 Phase 2 -->

> ⚠️ **权威声明**：schema / 包格式的权威定义在兄弟仓 open-typing-texts `docs/adapter-package.md` + `schemas/ott-adapter-v1.schema.json`；canonical JSON 定义已并入 `repo-manifest-spec.md`（3.10）。本文件仅描述 typetype 侧实现，不再重复维护上游 schema。
>
> 依据：ADR-011 决策 12（canonical JSON 以 open-typing-texts 为权威；minisign 不支持；签名统一裸 Ed25519 hex；TOFU 首次信任必须 UI 显式确认）。

## 1. Canonical JSON

签名对象为剔除 `trust` 字段后的 manifest：

```python
canonical = {k: v for k, v in manifest.items() if k != "trust"}
canonical_bytes = json.dumps(
    canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")
).encode("utf-8")
```

规则：UTF-8、键按字节序排序、无空白、无尾逗号。typetype `_verify_ed25519_signature` 已按此实现，open-typing-texts spec 已同步此定义（2026-08-09 批次 4，`repo-manifest-spec.md`）。

## 2. 密钥与签名格式

- 签名：`ed25519:<128 hex>` 或裸 128 hex（Ed25519 64 字节签名）
- 公钥：`ed25519:<64 hex>` 或裸 64 hex
- 不支持 minisign 前缀（决策 12：明确移除）
- 签名验证：`Ed25519PublicKey.verify(signature, canonical_bytes)`

## 3. TOFU 首次信任

1. 客户端首次拉到带签名的 manifest → 校验签名有效后固定其 `pubkey`，`trust_state=pending`，UI 展示 `pubkey` 指纹（前 24 hex）与签名者
2. 用户 UI 显式确认信任 → `pinned_pubkey` 持久化到订阅，`trust_state=verified`
3. 未确认 → 保持 `trust_state=pending`（公钥已固定，等待用户决定，不自动升级）
4. 关键变更（key rotation：签名 `pubkey` 与 pinned 不一致）→ 重置 `trust_state=pending`，UI 展示"信任降级"并要求重新确认；确认后重新固定新公钥
5. 签名无效 → `trust_state=failed`，L3 脚本跳过不执行

> 注：首次信任**不会**自动 verified——"再次拉到同一 `pubkey` 且签名有效 → 自动 verified"是已修复的 BLOCKER 行为（ADR-011:35），本实现一律需用户显式确认。

## 4. 执行门槛（Phase 2.3）

- L3 ott-script 仅允许 `trust_state=verified` 的仓库执行
- 未签名/未确认/签名失败仓库的脚本一律跳过并记日志
- L0/L1/L2 不受签名门槛影响（签名是 L3 的执行门槛，不是徽章）

## 5. 撤销（Phase 2.7 前置设计）

- manifest `revocations[]`：按 `content_hash` 撤销条目，客户端本地屏蔽（`blocked_content_hashes` 已落地存储层）
- key 级撤销：被撤销 key 签过的 manifest/内容标记"信任降级"，由用户选择重新信任或整体移除

## 6. 工具链（Phase 2.5 已落地）

`scripts/adapter.py` 子命令：`new`（生成适配器骨架）、`validate`（schema 校验）、`debug`（mock 沙箱）、`sign`（离线私钥签名 + canonical JSON）。

## 7. 已解决（原待定项）

- open-typing-texts spec 的 canonical JSON 与 minisign 移除已两仓同步完成（3.10，2026-08-09 批次 4）
- 撤销列表协议（2.7）已落地：manifest `revocations[]` + 客户端 `blocked_content_hashes` 本地屏蔽
