# 适配器签名方案（Phase 2.0 设计）

<!-- 状态: draft | 创建: 2026-08-08 | 关联: ADR-011 Phase 2 -->

> 依据：ADR-011 决策 12（canonical JSON 以 open-typing-texts 为权威；minisign 不支持；签名统一裸 Ed25519 hex；TOFU 首次信任必须 UI 显式确认）。

## 1. Canonical JSON

签名对象为剔除 `trust` 字段后的 manifest：

```python
canonical = {k: v for k, v in manifest.items() if k != "trust"}
canonical_bytes = json.dumps(
    canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")
).encode("utf-8")
```

规则：UTF-8、键按字节序排序、无空白、无尾逗号。typetype `_verify_ed25519_signature` 已按此实现，open-typing-texts spec 同步此定义。

## 2. 密钥与签名格式

- 签名：`ed25519:<128 hex>` 或裸 128 hex（Ed25519 64 字节签名）
- 公钥：`ed25519:<64 hex>` 或裸 64 hex
- 不支持 minisign 前缀（决策 12：明确移除）
- 签名验证：`Ed25519PublicKey.verify(signature, canonical_bytes)`

## 3. TOFU 首次信任

1. 客户端首次拉到带签名的 manifest → 展示 `pubkey` 指纹（前 24 hex）与签名者
2. 用户显式确认信任 → `pinned_pubkey` 持久化到订阅，`trust_state=verified`
3. 未确认 → `trust_state=unverified`
4. 再次拉到同一 `pubkey` 且签名有效 → 自动 verified
5. `pubkey` 与 pinned 不一致 → `trust_state=failed`，UI 展示"信任降级"并要求重新信任或移除订阅

## 4. 执行门槛（Phase 2.3）

- L3 ott-script 仅允许 `trust_state=verified` 的仓库执行
- 未签名/未确认/签名失败仓库的脚本一律跳过并记日志
- L0/L1/L2 不受签名门槛影响（签名是 L3 的执行门槛，不是徽章）

## 5. 撤销（Phase 2.7 前置设计）

- manifest `revocations[]`：按 `content_hash` 撤销条目，客户端本地屏蔽（`blocked_content_hashes` 已落地存储层）
- key 级撤销：被撤销 key 签过的 manifest/内容标记"信任降级"，由用户选择重新信任或整体移除

## 6. 工具链（Phase 2.5 排期）

`scripts/adapter.py` 子命令：`new`（生成适配器骨架）、`validate`（schema 校验）、`debug`（mock 沙箱）、`sign`（离线私钥签名 + canonical JSON）。

## 7. 待定

- open-typing-texts spec 的 canonical JSON 与 minisign 移除需两仓同步（兄弟仓占用中）
- 撤销列表的推送/消费协议（2.7）
