# OTT Repo 治理与法律风控操作手册

<!-- 状态: active | 创建: 2026-08-08 | 关联: ADR-011 Phase 7 -->

> 面向官方默认源与适配器仓库维护者。协议细节见 open-typing-texts `docs/repo-manifest-spec.md`，客户端屏蔽机制见 ADR-010 决策 7（blocklist 为客户端本地策略）。

## 1. 贡献者协议

向官方默认源提交内容即声明：

- 提交内容是公有领域、自有授权或已获权利人明确授权
- 同意在仓库 `LICENSE`（当前 CC-BY-SA-4.0）下分发
- 逐条在 entry/source 填写 `rights_summary`、`license`、`origin`，不得留空

提交 PR 时在描述中粘贴以下模板：

```text
声明：我拥有或以合法授权提交本内容，同意在仓库 LICENSE 下分发。
内容来源：<source / origin>
授权类型：<public-domain | original | licensed>
```

## 2. 官方适配器仓库收稿红线

- 只收：源所有者自荐/授权、公开 API、公有领域或自有授权内容
- 不收：逆向工程类适配、绕过访问控制、未授权抓取
- 每条规则/脚本必须能通过 `ott-repo.schema.json` 校验与 mock 沙箱测试后再合并

## 3. Takedown 流程

1. 权利人投诉（含侵权内容 hash / URL 与权利证明）
2. 维护者核验 `rights_summary`/`license`/`origin` 与投诉材料
3. 核验通过：从官方仓移除内容；协议级撤销列表（`revocations[]`）待 Phase 2.7 落地后推送
4. 客户端侧立即生效：维护者可指导用户加入本地屏蔽清单（`blocked_content_hashes`），对应条目详情将不再返回

验证：

```bash
uv run pytest tests/test_builtin_default_source.py tests/test_runtime_config.py -k blocked
```

## 4. 合规复核

Phase 7.4 外部律师评审未完成前，官方托管第三方适配器的发布保持关闭。
