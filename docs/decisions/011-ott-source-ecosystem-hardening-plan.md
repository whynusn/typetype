# ADR-011: OTT 源生态加固与去中心化适配器执行方案

<!-- 状态: proposed | 决策日期: 2026-08-07 | 最后验证: 2026-08-07 | 修订: 2026-08-07 审查修订（范围拆分 / 顺序调整 / 补决策） -->

> 本文是"修复当前 OTT 实现缺陷 + 建设去中心化空壳软件与源分发机制"的**可执行方案**。
> 来源：2026-08-07 对 typetype 与 open-typing-texts 两仓的只读审计、主流去中心化空壳软件（mihon / legado / TVBox / Kazumi / F-Droid / TUF）调研、原语安全实测。
> 完整设计见 [decentralized-source-ecosystem.md](../designs/decentralized-source-ecosystem.md)（本地草稿，未纳入版本控制）。

## 审查修订（2026-08-07）

外部审查抽查 8 条证据全部属实；方向正确，主要风险是范围与排序。本修订采纳以下结论：

1. Phase 0 拆批 A/B；批 A 为 2-3 天安全红线批次，先于一切贡献开放。
2. Windows 默认禁用 L3 提前到批 A（不再等 Phase 5）。
3. 脚本沙箱 `urllib.request file://` 访问收敛为 P0，并入批 A。
4. 取消自动订阅（原 4.1）与法律声明（原 7.4）提前到批 A。
5. Phase 6 排行榜拆出为独立 [ADR-012](./012-decentralized-leaderboard.md)，与主线解耦。
6. L1.5 设计文档先行（新增任务 1.0）；L1/L1.5 关系明确为同一解释器扩展。
7. RE2 决策：先纯子进程超时方案，RE2 为可选强化，不阻塞 Phase 0。
8. 签名方案前置任务 2.0：canonical JSON、minisign 取舍、TOFU UI、key 撤销交互在 Phase 2 开工前定稿。

## 背景

typetype 正从"客户端 + typetype-server 中心化"演进为"去中心化空壳客户端 + OTT 源分发生态"。

目标：

1. 保留动态文本获取能力（声明式规则 + 受限脚本），允许第三方个人开发者贡献源适配。
2. 任何原语、规则、脚本及其组合不能造成本机破坏或网络安全事故。
3. 客户端保持"真空壳"：零预置第三方内容、零广告、无跨源聚合搜索。
4. 通过架构与治理把法律风险降到可接受区间（legado 案教训：空壳 + 深链规则仍构成侵犯著作权罪）。

## 已验证事实（证据清单）

以下问题均有代码或实测证据，修复优先级以此为据。

| # | 问题 | 证据 | 严重度 |
|---|---|---|---|
| 1 | 正则 ReDoS：`(a+)+$` 对 **100 字符输入 >8s 不返回**，50KB 截断完全无效；第三方规则可直接 DoS | `src/backend/integration/ott_rule_interpreter.py` `_extract_regex()`（2026-08-07 实测） | 严重 |
| 2 | `validate_url()` 对 URL 编码 host（`http://127.0.0.1.%2e/`）放行；DNS 解析失败也放行；校验与请求两次解析（TOCTOU / DNS rebinding） | `ott_rule_interpreter.py` `validate_url()`（实测） | 严重 |
| 3 | 签名是"徽章非门槛"（ADR-010 决策 4），L3 脚本可经 Repo 分发且无签名门槛；与 open-typing-texts 规范（L3 MUST NOT 分发）和 schema 冲突 | `ott_repo_manifest.py`、open-typing-texts `repo-manifest-spec.md:210`、`ott-repo.schema.json:81` | 高 |
| 4 | L2 ott-bridge 文档标"已落地"但无实现，订阅到 bridge 的 manifest 被静默丢弃 | `docs/ARCHITECTURE.md:420` vs `ott_federation_provider.py:397` | 高 |
| 5 | 联邦分段进度 key 缺 authority（`ott:{entry_id}@{revision}`），跨 authority 同 entry_id 串进度 | `src/backend/presentation/bridge.py:90-98,1455` vs `OTT_SPEC.md:163` | 高 |
| 6 | 官方默认源违规：manifest 含 schema 禁止的 `ott-script`、`default_enabled` 误用；static `entries.json` 的 summary 内嵌全文、entry_id 含连字符（不符 `^[A-Za-z0-9_]+$`）；缺 `sources.json`；entry 无 `rights_summary`/`license`/`origin` | `public-ott-repo/`（实测 schema 校验 2 errors + 6 errors） | 高 |
| 7 | 沙箱跨平台强度不符声明：rlimit 仅 POSIX、Landlock 仅 Linux 5.13+；Windows 只剩 AST + 超时；AST 可被对象模型绕过；`urllib.request` 允许 `file://` 且 Landlock 放行 `/etc` | `ott_script_runner.py:34-55`、`ott_script_safety.py` | 高 |
| 8 | 控制面死字段：mirrors 不参与拉取、ETag 无调用方、`requires` 协商未实现、`default_enabled` 不消费 | `ott_repo_manifest.py:315`、`runtime_config.py:149` | 中 |
| 9 | 脚本 authority 全部硬编码 `script`，无脚本级命名空间，同 entry_id 被 dedupe 吞掉 | `ott_script_client.py:240`、`ott_federation_provider.py:512` | 中 |
| 10 | federation 每次调用重建 clients 与 `httpx.Client`（不 close），rule/script 的 get_entry/segment 每次全量重抓，`schedule.cache_ttl_seconds` 死字段 | `ott_federation_provider.py:370-425`、`ott_rule_interpreter.py:363-430` | 中 |
| 11 | JSON 深度炸弹（10 万层）触发 RecursionError，当前靠上层 catch 兜底，无深度预检 | 实测 | 中 |
| 12 | open-typing-texts 仓 CI 必坏：`tests/test_repo_manifest.py` import jsonschema 但 pyproject 未声明 | `pyproject.toml:10-18`、`tests/test_repo_manifest.py:15` | 中 |
| 13 | 签名 canonical JSON 仅 typetype 侧定义，minisign 前缀解析失败，跨仓不可互操作 | `ott_repo_manifest.py:487-526` | 中 |
| 14 | 客户端自动订阅官方默认源并打包内容，违背"真空壳"原则（法律风险最高点） | `runtime_config.py:253-263,474-486` | 高 |

## 选项

| 方案 | 描述 | 判断 |
|:---|:---|:---|
| A. 安全加固 + 签名门槛 + L1.5 DSL | 保留动态能力；规则/脚本按能力白名单与签名分级；先修实测漏洞 | ✅ 选中 |
| B. 完全回归声明式（砍 L3） | 法律风险最低，但失去复杂抓取能力，极速杯类源无法覆盖 | 作为 A 的兜底选项 |
| C. 维持现状开放贡献 | 不修复直接开第三方贡献 | ❌ ReDoS/SSRF 实测漏洞使不可接受 |

## 决策

1. 采用方案 A：动态能力分层为 L1 声明式、L1.5 受限 DSL、L2 桥接、L3 签名脚本。
2. L1.5 提供白名单计算原语（编码/哈希/AES/时间/文本/集合/JSON/URL 构造/条件），无循环、无任意代码，覆盖极速杯类"算法型"抓取。
3. L3 保留但改为**签名门槛**：未签名拒绝执行，TOFU 指纹固定，key 变更显式确认。
4. 所有原语与组合执行统一资源约束（大小/深度/调用数/耗时/内存），正则移出宿主进程执行。
5. 网络出口收敛到唯一 `request` 原语 + 白名单代理 + DNS pin。
6. 客户端空壳化：取消自动订阅默认源，官方内容只留公有领域/自有授权。
7. 排行榜去中心化：本地记分板优先，可选联邦 board（Ed25519 身份，无账号）。
8. **RE2 取舍**：Phase 0 采用纯子进程 + 硬超时方案（零新依赖）；RE2 引擎（google-re2）列为可选优化，仅在子进程方案不达标时引入。
9. **Windows L3**：Phase 0 批 A 即在 Windows 默认禁用 L3（配置开关 + UI 明示）；Phase 5 评估 Job Object/受限令牌，通过后才重新启用。
10. **Phase 6 拆分**：排行榜去中心化迁出本 ADR，独立 [ADR-012](./012-decentralized-leaderboard.md) 排期，不阻塞源生态主线。
11. **L1/L1.5 关系**：L1 是 L1.5 的受限子集；同一解释器演进，schema v2 向后兼容；运行时分流仅按能力字段（body/steps/permissions 是否存在）选择路径，不维护两套引擎。
12. **签名前置定义**：canonical JSON 以 open-typing-texts 协议规范为权威（typetype 对齐实现）；minisign 不支持，签名格式统一为裸 Ed25519 hex；TOFU 首次信任必须 UI 显式确认；key 变更/撤销时该 key 签过的内容标记"信任降级"，由用户选择重新信任或全部移除。

## 影响与实施阶段

### Phase 0A：安全红线批次（P0，2-3 天，先于一切贡献开放）

| 任务 | 文件 | 改动 | 验收 |
|---|---|---|---|
| 0.A1 修订 `validate_url()` | `src/backend/integration/ott_rule_interpreter.py` | percent-decode host；punycode；拒绝 host 含 `%`/非 ASCII；解析失败一律拒绝；IPv4 映射 IPv6 与十六进制/十进制/八进制 IP 字面量检测；端口限 80/443 | 攻击用例全过：编码 host、IP 混淆、`[::ffff:127.0.0.1]`、DNS 失败均拒绝 |
| 0.A2 JSON 深度预检 | `ott_rule_interpreter.py` `_parse_response()` | 预扫括号深度 ≤256 | 10 万层炸弹直接失败，无 RecursionError |
| 0.A3 请求与校验共用解析 | `ott_rule_interpreter.py` `_fetch()` | DNS pin；显式禁重定向 | mock 测试：解析后 IP 变更不生效 |
| 0.A4 沙箱临时文件加固 | `ott_script_client.py` | 私有目录（0700）+ 文件 0600 + 校验属主 | 多用户下无 TOCTOU |
| 0.A5 日志脱敏（含 federation） | `ott_rule_interpreter.py`、`ott_script_client.py`、`ott_federation_provider.py` | 不记录响应内容/参数/URL query；只记 host、长度、hash | 日志无正文与凭据 |
| 0.A6 Windows 默认禁用 L3 | `ott_script_client.py` + `runtime_config.py` | 平台检测 + 配置开关；UI 明示原因 | Windows 上未签名/已签名脚本均不执行 |
| 0.A7 取消自动订阅 | `runtime_config.py` `_ensure_default_subscription()` | 首启不自动订阅；引导页导入源 | 全新配置无任何 source_repos |
| 0.A8 法律声明 | README + 客户端 | 工具中立性声明；无广告；无聚合搜索 | 发布物含声明 |
| 0.A9 脚本沙箱 `file://` 收敛 | `ott_script_safety.py`、`ott_script_runner.py` | AST 黑名单加 `urllib.request`/`urlopen`；或出口代理统一拦截非 http(s) | `file://` 读取用例全拒 |
| 0.A10 基线测试记录 | CI/文档 | 开工前记录全量基线（当前 803 passed），每批后全量回归 | 基线可查 |

### Phase 0B：正则执行子进程化（独立排期，不阻塞 0A）

| 任务 | 文件 | 改动 | 验收 |
|---|---|---|---|
| 0.B1 正则移出主进程 | `ott_rule_interpreter.py` + 新 `regex_worker.py` | 子进程执行 + 1s 硬超时；输入 ≤10KB；静态拒绝嵌套量词；RE2 作为可选第二阶段 | 100 字符恶意正则 1s 内返回；新增回归测试 |

### Phase 1：受限 DSL 原语引擎（L1.5）

| 任务 | 改动 | 验收 |
|---|---|---|
| 1.0 DSL 设计文档先行 | 新 `docs/designs/ott-dsl.md`（本地草稿） | 原语签名、类型系统（str/bytes/int/bool/list/dict）、组合约束、与 L1 的关系；评审通过后再排 1.1-1.5 |
| 1.1 原语白名单实现 | 新 `ott_dsl.py`（纯函数求值器，L1 解释器扩展） | 首批：基础值/编码解码/时间/随机/文本正则/算术位/集合/JSON/URL 构造/条件；加密原语（md5/sha1/sha256/hmac/aes_cbc/xor）第二批 |
| 1.2 引擎约束 | `ott_dsl.py` | 纯函数无状态；单值 ≤1MB；步间 ≤2MB；深度 ≤32；调用 ≤1000；steps ≤8；无循环原语；字节串显式类型；异常不暴露细节 |
| 1.3 规则 schema v2 | 新 `ott-rule-v2.schema.json` | `request.body`、`steps`、`permissions`、`rights` 字段；旧规则向后兼容；运行时分流：仅含旧字段走 L1 子集路径 |
| 1.4 极速杯迁移验证 | 新 `tests/fixtures/rule-samples/jisubei.json` | 用 DSL 表达 AES 请求并跑通 mock；**前置：确认 www.jsxiaoshi.com 可用性与抓取许可** |
| 1.5 组合安全测试 | 新 `tests/test_ott_dsl_security.py` | 组合矩阵用例全过 + 模糊测试（随机组合断言资源上限） |

### Phase 2：适配器体系与签名门槛

| 任务 | 改动 | 验收 |
|---|---|---|
| 2.0 签名方案定稿 | 新 `docs/designs/adapter-signing.md` + open-typing-texts 同步 | canonical JSON 定义、minisign 移除、TOFU 首次信任 UI 流程、key 变更/撤销交互；2.3/2.7/3.10 以其为前置 |
| 2.1 适配器包格式 | 新 `docs/reference/adapter-package.md` + schema | `adapter.json`（manifest + 权限 + rights + API level）+ 代码/规则 + fixtures + 签名 |
| 2.2 权限清单强制 | `ott_federation_provider.py`、`ott_script_client.py` | `permissions.network` 域名白名单；storage/process 默认 none；运行时强制 |
| 2.3 L3 签名门槛 | `ott_repo_manifest.py`、`ott_script_client.py` | 未签名脚本拒绝执行；TOFU 首次信任 UI 确认；key 变更触发信任降级确认流程 |
| 2.4 CI 签名流水线 | 新 `.github/workflows/adapter-publish.yml`（两仓各自） | schema 校验 → 静态分析 → mock 沙箱 → 可重复构建 → 离线私钥签名 → 发布索引 |
| 2.5 适配器 SDK | 扩展 `scripts/debug_rule.py` → `scripts/adapter.py` | `new`/`validate`/`debug`/`sign` 子命令 + mock server |
| 2.6 API Level | 常量 + 校验 | 规则/脚本声明 api_level；客户端拒绝低于最低版本 |
| 2.7 撤销列表 | `ott_repo_manifest.py` + UI | `revocations[]` 按 content_hash 推送；key 级撤销联动信任降级流程；客户端本地屏蔽 |

### Phase 3：控制面完善

| 任务 | 改动 | 验收 |
|---|---|---|
| 3.1 镜像 failover | `ott_repo_manifest.py` `_fetch_manifest()` | 按 manifest.mirrors 优先级 + 健康度退避；订阅 URL 失败时走镜像 |
| 3.2 ETag | `ott_repo_manifest.py` + `runtime_config.py` | `If-None-Match`/304；持久化 etag |
| 3.3 requires 协商 | `ott_federation_provider.py` | 不满足 `ott_core`/`client_features` 整仓标记不兼容（含原因），不静默部分启用 |
| 3.4 default_enabled 消费 | `ott_federation_provider.py` | 订阅后按声明启用/禁用源 |
| 3.5 ott-bridge 决策 | 文档 + 实现（或明示暂不开放） | 二选一：实现 wenlai 桥示例；或 ARCHITECTURE.md 改"未落地"并在 UI 显示"该源类型暂不支持" |
| 3.6 TUF-lite | `ott_repo_manifest.py` + schema | manifest 含 `expires_at`/`snapshot_hash`；过期与撤销生效 |
| 3.7 进度 key 修复 | `bridge.py` | `ott:{authority}:{entry_id}@{revision_id}`；含旧 key 迁移 |
| 3.8 脚本命名空间 | `ott_federation_provider.py` | authority = `script:{sha256(url)[:12]}`，UI 同步 |
| 3.9 federation 复用 | `ott_federation_provider.py` | 客户端实例缓存；`httpx.Client` 显式 close；rule/script 结果按 `schedule.cache_ttl_seconds` 缓存 |
| 3.10 签名互操作 | `ott_repo_manifest.py` | 与 open-typing-texts 统一 canonical JSON 定义；明确 minisign 支持或移除 |

### Phase 4：空壳化与默认源合规

| 任务 | 改动 | 验收 |
|---|---|---|
| 4.1 默认内容合规 | `public-ott-repo/`、`resources/ott-repo/` | 只留公有领域/自有授权内容；逐条注明 rights/license/origin；hitokoto 规则默认关闭或移除 |
| 4.2 静态 profile 合规 | 两个 static 目录 | 补 `sources.json`、`entries/{id}.json`；summary 不嵌全文；entry_id 符合 schema pattern |
| 4.3 移除 ott-script 示例 | `public-ott-repo/ott-repo.json` | manifest 通过 `ott-repo.schema.json` 校验（CI 门禁） |

> 状态（2026-08-08）：**4.1-4.3 已落地**。两个 static 目录补齐 sources.json + entries/{id}.json，summary 不再嵌全文，entry_id/source_key 统一 `^[A-Za-z0-9_]+$`；内置源以 file:// 订阅形式首启注入（离线可用，不自动订阅远程源）；官方仓已移除 hitokoto rule 与 ott-script 示例。

### Phase 5：沙箱与网络出口加固

| 任务 | 改动 | 验收 |
|---|---|---|
| 5.1 Linux 补齐 | `ott_script_runner.py` | seccomp（禁 ptrace/clone 变体）+ 现有 Landlock + rlimits |
| 5.2 Windows 策略 | `ott_script_runner.py`/文档 | Job Object + 受限令牌；做不到则 L3 在 Windows 默认禁用并在 UI 明示 |
| 5.3 出口代理 | 新 `ott_outbound_proxy.py` | 本地代理按域名白名单放行；DNS pin；审计日志；脚本无直连 |
| 5.4 凭据注入 | `ott_script_client.py` + `secure_token_store.py` | keyring → 子进程一次性 fd；脚本不可读 keyring 文件 |

### Phase 6：已拆出

去中心化排行榜（本地记分板 + ott-board 联邦协议）已迁至 [ADR-012](./012-decentralized-leaderboard.md) 独立排期，与本 ADR 主线解耦。

### Phase 7：治理与法律风控

| 任务 | 产出 | 验收 |
|---|---|---|
| 7.1 贡献者协议 | 文档 + 提交模板 | 提交即声明 rights 授权；违规下架 |
| 7.2 takedown 流程 | 文档 + 撤销列表 | 版权投诉 → 撤销 hash → 客户端屏蔽 |
| 7.3 官方适配器仓库 | GitHub 组织 | 收稿红线：源所有者自荐/授权或公开 API；逆向类不收 |
| 7.4 合规复核 | 外部 | 律师评审后放行 L3 分发 |

## 全局安全红线（不可协商）

1. 不提供 `eval`/`exec`/`compile`/动态函数调用/反射/对象模型访问/任意 import。
2. 不提供文件、进程、环境变量、任意 socket 原语；网络出口只有 `request`，且必须过白名单。
3. 正则不直接在宿主进程执行；任何正则输入都有限时与大小上限。
4. 每个新原语必须过威胁建模 + 组合矩阵 + 模糊测试门禁才能进白名单。
5. 签名状态是 L3 的执行门槛，不是徽章；key 变更必须用户显式确认。
6. 官方默认源只放公有领域/自有授权内容；第三方源默认关闭。
7. 任何日志不得记录响应正文、凭据、中间 token。
8. L3 不允许无头浏览器类抓取（headless/WebDriver）作为规则原语；如业务需要，须单独立项评估沙箱与法律面。
9. 规则执行路径的第三方依赖（httpx/bs4/cryptography）以 uv.lock 锁定；升级必须过回归门禁。

## 验证门禁（CI）

1. 原语边界单测：空输入、超限、Unicode、二进制。
2. 组合矩阵回归：Phase 1.5 的用例。
3. 模糊测试：随机规则组合，断言资源上限恒成立。
4. 网络 mock：恶意 host 全集（IP 混淆、编码、IPv6 映射、rebinding）。
5. ReDoS 回归：100 字符恶意正则，断言 1s 内返回。
6. 性能门禁：单规则 ≤5s、内存 ≤256MB。
7. manifest/schema 门禁：两仓官方样例必须通过 `ott-repo.schema.json` 与 `entry-summary.schema.json`。
8. [外部依赖] 修复 open-typing-texts CI：pyproject 声明 jsonschema（或测试改用仓库自带依赖）；需两仓协作，不阻塞 typetype 主线。
9. 基线回归：Phase 0A 开工前记录全量测试基线（当前 803 passed），每批改动后全量通过。

## 里程碑

```text
Phase 0A（安全红线）→ Phase 0B（正则子进程）→ Phase 1（DSL）→ Phase 2（适配器+签名）→ Phase 3（控制面）
        ↓                                                            ↓
Phase 4（默认源合规）可与 Phase 1 并行               Phase 5（沙箱出口）依赖 Phase 2
                                                              ↓
                                            Phase 7（治理）与 ADR-012（排行榜）独立并行
```

- M0（Phase 0A 完成）：第三方贡献机制可以安全开放（仍限 L1）；Windows L3 禁用；取消自动订阅；基线回归通过。
- M1（Phase 0B 完成）：正则 DoS 消除。
- M2（Phase 1-2 完成）：极速杯 DSL 化 + 签名适配器流水线上线。
- M3（Phase 3-5 完成）：控制面字段全部生效 + 跨平台沙箱声明成立。
- M4（Phase 4/7 完成）：真空壳默认、治理与合规齐备；排行榜见 ADR-012。

## 风险与边界

- 正则 ReDoS 的静态检测可被绕过，因此"子进程 + 硬超时"是硬要求；RE2 为可选强化，启发式只是减面。
- 沙箱无绝对安全；Windows 若无法达到声明强度，正确做法是禁用 L3 而非弱化声明。
- "验证无事故"无法形式化证明；本方案是能力最小化 + 多层约束 + 回归测试。
- 法律风险不能靠技术消除；官方托管第三方适配器仍需外部合规复核。

## 待外部确认项

1. 官方默认源是否允许第三方 API 规则（如 hitokoto）默认开启。
2. ott-bridge 是否立项（wenlai 桥示例）。
3. 极速杯服务（www.jsxiaoshi.com）可用性与抓取许可（1.4 验收前置）。
4. 无头浏览器类抓取是否立项（红线第 8 条默认禁止）。
