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

## 三线审查归档（2026-08-09）

ADR-011 实施三线审查（进度审计 / 代码质量 / 方向正确性）结论归档。三份独立结论交叉验证，唯一红线项（TOFU UI）三方一致。

**进度审计**（explore，逐 Phase 文件:行号核对）：
- IMPLEMENTED：Phase 0A 全 10 项、0.B1、Phase 1（1.1/1.2/1.4-mock/1.5；1.3 运行时）、3.1-3.8、Phase 4、7.1-7.3（文档级）、2.0/2.1（文档级）
- PARTIAL：2.3（执行门槛 ✅ / TOFU UI ✗）、3.9（复用+缓存 ✅ / httpx.Client 显式 close ✗，全仓零 `.close()`）、1.3（typetype 运行时 ✅ / 跨仓 `ott-rule-v2.schema.json` 未产出，ADR 自身标 ⚠️）、2.2/2.6（规则侧已实现但 ADR 状态注标"未开工"，script 侧无强制）、5.2（0.A6 兜底分支 ✅）
- MISSING（与 ADR 未标落地一致）：2.4（无 adapter-publish.yml）、2.5（无 scripts/adapter.py）、2.7（无 revocations[] 解析）、3.6（无 expires_at/snapshot_hash）、5.1 seccomp、5.3 出口代理、5.4 凭据注入、7.4 律师评审

**代码质量**（general，10 文件逐文件审查）：
- 1 BLOCKER：TOFU 首次信任自动 verified，违反决策 12（"必须 UI 显式确认"）；`ott_repo_manifest.py:546-547` 自认 TODO 过渡行为
- 3 MAJOR：Landlock `/etc` 白名单过宽（含 /etc/shadow 等，建议收窄为 resolv.conf+hosts+nsswitch.conf）；DSL `_Budget` 只计 calls 不计 steps（无循环绕过但无法精确限单 step）；regex_worker 无自身资源限制（依赖调用方 1s 超时，建议 `signal.alarm` 二级防护）
- 8 MINOR：script authority/source_key 硬编码不一致（ott_script_client.py:272-274）；`_read_local_json` 先 `json.loads` 再查 max_bytes（顺序反）；`REGEX_MAX_INPUT_CHARS` 三处重复定义；`_fetch_json` 无 content-length 预检；脚本缓存 TTL 与 cache_ttl_seconds 不统一；httpx.Client 无 close（低风险）；canonical JSON ensure_ascii=False；僵尸字段 registry.primary_url
- 确认健康：DSL 非图灵完备（无循环/无变量赋值/四重硬上限）；沙箱三道防线成立（AST+受限 builtins+Landlock/rlimits）；正则子进程化真正解决 ReDoS

**方向正确性**（general）：VERDICT **PROCEED（有条件）**。决策 1-13 设计合理、安全红线贯彻正确、依赖链 2.0→2.3→2.7 无需调整。2 个需修正项：
1. 脚本沙箱 `__subclasses__()` 逃逸：AST 是静态分析，拦不住运行时 `().__class__.__bases__[0].__subclasses__()` 对象模型遍历（`type`/`object`/`getattr` 已禁，但 `__subclasses__` 是属性方法不在禁列）。缓解：即使逃逸 safe_globals 仍在受限子进程内（256MB/30s/Landlock）。修复：safe_globals 覆盖 `__class__`/`__mro__`/`__subclasses__` 为 None，或 AST 拦截这些属性访问。
2. TOFU UI 确认流程：与代码质量 BLOCKER 同源，Phase 2.0 定稿时必须包含 TOFU UI 交互规范（首次信任弹窗 / key 变更通知 / 降级确认）。

**推进优先级**（后续工作依据）：BLOCKER（TOFU UI）→ MAJOR（沙箱加固 / Landlock 收窄 / signal.alarm）→ MINOR 批 → 归档后按此推进。

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

| 任务 | 文件 | 改动 | 验收 | 状态 |
|---|---|---|---|---|
| 0.A1 修订 `validate_url()` | `src/backend/integration/ott_rule_interpreter.py` | percent-decode host；punycode；拒绝 host 含 `%`/非 ASCII；解析失败一律拒绝；IPv4 映射 IPv6 与十六进制/十进制/八进制 IP 字面量检测；端口限 80/443 | 攻击用例全过：编码 host、IP 混淆、`[::ffff:127.0.0.1]`、DNS 失败均拒绝 | ✅ 已落地 |
| 0.A2 JSON 深度预检 | `ott_rule_interpreter.py` `_parse_response()` | 预扫括号深度 ≤256 | 10 万层炸弹直接失败，无 RecursionError | ✅ 已落地 |
| 0.A3 请求与校验共用解析 | `ott_rule_interpreter.py` `_fetch()` | HTTP DNS pin（解析为 IP 直连 + Host 头）；HTTPS 不 pin（TLS 证书按域名校验，内网 IP 无合法证书，commit 4114a21 定案）；`follow_redirects=False`（container/federation 装配） | mock 测试：解析后 IP 变更不生效；`test_http_requests_pinned_ip_with_host_header` / HTTPS 不 pin / pin_url 拒绝内网与解析失败 | ✅ 已落地 |
| 0.A4 沙箱临时文件加固 | `ott_script_client.py` | 私有目录（0700）+ 文件 0600 + 校验属主 | 多用户下无 TOCTOU | ✅ 已落地 |
| 0.A5 日志脱敏（含 federation） | `ott_rule_interpreter.py`、`ott_script_client.py`、`ott_federation_provider.py` | 不记录响应内容/参数/URL query；只记 host、长度、hash | 日志无正文与凭据 | ✅ 已落地 |
| 0.A6 Windows 默认禁用 L3 | `runtime_config.py` + `SettingsPage.qml` | `_default_scripts_enabled()` 按 `sys.platform != "win32"`；配置开关 + UI 明示原因 | Windows 上脚本默认不执行；`test_registry_scripts_enabled_default_disabled_on_windows`；设置页"Windows 默认关闭"提示 | ✅ 已落地 |
| 0.A7 取消自动订阅 | `runtime_config.py` | 首启不自动订阅任何**远程**源；内置 file:// 默认源除外（Phase 4） | 全新配置无远程 source_repos；内置本地源可离线使用 | ✅ 已落地（验收标准同步修订） |
| 0.A8 法律声明 | README + 客户端 | 工具中立性声明；无广告；无聚合搜索 | README「内容与安全声明」章节存在 | ✅ 已落地 |
| 0.A9 脚本沙箱 `file://` 收敛 | `ott_script_safety.py`、`ott_script_runner.py` | AST 白名单不含 `urllib.request`/`urlopen` | `file://` 读取用例全拒 | ✅ 已落地 |
| 0.A10 基线测试记录 | CI/文档 | 每批后全量回归并刷新基线 | 基线可查；当前 956 collected（全部通过，CI 全绿，2026-08-09） | ✅ 已刷新 |

> 复核说明（2026-08-08）：0.A3 与 0.A6 的实现不在评审 grep 的文件内，属漏查而非缺口。0.A3 在 `ott_rule_interpreter.py::_pin_url`（HTTP pin + Host 头）与 container/federation 的 `follow_redirects=False`；0.A6 在 `runtime_config._default_scripts_enabled()` 与 `SettingsPage.qml` 开关，均有对应测试。Phase 0A 全部落地。

### Phase 0B：正则执行子进程化（独立排期，不阻塞 0A）

| 任务 | 文件 | 改动 | 验收 | 状态 |
|---|---|---|---|---|
| 0.B1 正则移出主进程 | `ott_rule_interpreter.py` + 新 `regex_worker.py` | 子进程执行 + 1s 硬超时；输入 ≤10KB；静态拒绝嵌套量词；RE2 作为可选第二阶段 | 100 字符恶意正则 1s 内返回；新增回归测试 | ✅ 已落地 |

> 状态（2026-08-09）：0.B1 已随 #44 落地（`regex_worker.py` 子进程 + `_has_nested_quantifier` 静态拒绝 + `_extract_regex` 走 `subprocess.run` 1s 超时 + 10KB 截断）。`tests/test_ott_rule_interpreter.py` 80 passed 含恶意正则用例（`test_regex_nested_quantifier_rejected` / `test_regex_worker_timeout_fallback_empty` / `test_worker_rejects_nested_quantifier`）。RE2 引擎列为可选强化，未引入。
>
> 状态（2026-08-09 三线审查后修复）：**0.B1 二级防护 + 常量统一已落地**：`_run()` 内 `signal.alarm(1)` 包裹仅 `re.search`/`re.sub`（`hasattr(signal,"alarm")` 守卫，Windows no-op，导入时间不计入），超时 → `{"ok": false, "error": "timeout"}`；`REGEX_WORKER_MAX_INPUT_CHARS` 为唯一事实源，`ott_rule_interpreter.py`/`ott_dsl.py` 以 `as REGEX_MAX_INPUT_CHARS` 别名导入（无循环依赖）。新增 `test_worker_self_timeout_alarm`（monkeypatch re.search → sleep 2s，断言 <1.5s 返回 timeout）。

### Phase 1：受限 DSL 原语引擎（L1.5）

| 任务 | 改动 | 验收 | 状态 |
|---|---|---|---|
| 1.0 DSL 设计文档先行 | 新 `docs/designs/ott-dsl.md`（本地草稿） | 原语签名、类型系统（str/bytes/int/bool/list/dict）、组合约束、与 L1 的关系；评审通过后再排 1.1-1.5 | ✅ 已落地 |
| 1.1 原语白名单实现 | 新 `ott_dsl.py`（纯函数求值器，L1 解释器扩展） | 首批：基础值/编码解码/时间/随机/文本正则/算术位/集合/JSON/URL 构造/条件；加密原语（md5/sha1/sha256/hmac/aes_cbc/xor）第二批 | ✅ 已落地 |
| 1.2 引擎约束 | `ott_dsl.py` | 纯函数无状态；单值 ≤1MB；步间 ≤2MB；深度 ≤32；调用 ≤1000；steps ≤8；无循环原语；字节串显式类型；异常不暴露细节 | ✅ 已落地 |
| 1.3 规则 schema v2 | 新 `ott-rule-v2.schema.json` | `request.body`、`steps`、`permissions`、`rights` 字段；旧规则向后兼容；运行时分流：仅含旧字段走 L1 子集路径 | ⚠️ typetype 运行时已落地；跨仓 schema 文件未产出 |
| 1.4 极速杯迁移验证 | 新 `tests/fixtures/rule-samples/jisubei.json` | 用 DSL 表达 AES 请求并跑通 mock；**前置：确认 www.jsxiaoshi.com 可用性与抓取许可** | ✅ mock 验证完成；真实服务可用性/抓取许可仍待确认项 3 |
| 1.5 组合安全测试 | 新 `tests/test_ott_dsl_security.py` | 组合矩阵用例全过 + 模糊测试（随机组合断言资源上限） | ✅ 已落地 |

> 状态（2026-08-08）：**Phase 1.1-1.5 已落地**。引擎补上整数资源上限（超大整数/超大位移拒绝、字面量与结果超限检查前置），`tests/test_ott_dsl_security.py` 组合矩阵 + 300 例固定种子模糊测试全过。

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

> 状态（2026-08-08）：**2.0 设计文档已产出**（`docs/designs/adapter-signing.md`）；**2.3 执行门槛已落地**（L3 仅 verified 仓库执行）。2.2/2.4-2.7 未开工；2.4/2.5 依赖 2.1 的适配器包格式。
>
> 状态（2026-08-09）：**2.1 适配器包格式已落地**：`docs/reference/adapter-package.md`（包布局 + `adapter.json` 字段表 + 签名/校验流程）+ `docs/reference/ott-adapter-v1.schema.json`（draft-07，script/rule 要求 `content.path`、instance 要求 `content.endpoints`、signature 格式 `ed25519:` 前缀可选）。schema 已用 `jsonschema` 验证：合法示例过、坏 type/checksum/缺 content 拒。运行时消费（manifest source 引用 adapter_id → 包内文件拉取）留给 2.2；跨仓 spec 同步仍为待确认项。
>
> 状态（2026-08-09 三线审查后修复）：**2.3 TOFU UI 确认流程已补齐**（红线项，决策 12 落实）：`trust_state` 新增 `pending`；首次有效签名 → pending + 固定公钥（不再自动 verified）；key 变更 → pending（需用户重新确认，不再静默 failed）；pending 跨刷新保持 sticky；L3 仍仅 `verified` 执行（`!= "verified"` 门槛未动）。UI：`ReposManagementPanel` 待确认徽章（systemCautionColor）+ 信任/拒绝按钮 → `confirmRepoTrust`/`rejectRepoTrust`（bridge → RegistryAdapter → runtime_config）。`runtime_config` 新增 `confirm_source_repo_trust`/`reject_source_repo_trust`（reject 清公钥回 unverified，订阅保留，下次刷新重新评估）。测试 11 个新增用例全绿，全量 977 passed。

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

> 状态（2026-08-08）：**3.1-3.5、3.9 已落地**。3.1 按已缓存 manifest 的 http(s) mirrors 依次 failover（file:// 镜像忽略）；3.2 携带 `If-None-Match`、304 仅刷新缓存 mtime 并持久化 ETag；3.3 `ott_core` 版本约束 + `client_features` 协商，不满足整仓跳过并显示 `incompatible_reason`；3.4 ott-instance 按 `default_enabled` 消费（rule/script 该字段不在当前 schema，归一化不输出）；3.5 选择"明示暂不开放"：联邦跳过 ott-bridge，订阅面板显示"桥接源暂不支持"，ARCHITECTURE 改未落地；3.9 联邦共享单 `httpx.Client`、按订阅+manifest mtime 签名复用客户端、rule/script 结果按 `cache_ttl_seconds` 缓存。
>
> 状态（2026-08-09）：**3.7、3.8 已落地**。3.7 联邦分段进度 key 已是 `ott:{authority}:{entry_id}@{revision_id}`（bridge `_compute_progress_key("ott", ...)` 拼接，随 #44 落地），旧 OTT 直连路径以 `local` 兜底，`_find_progress` 按标题前缀扫描兼容旧格式 key 完成迁移；3.8 `_ScriptClient` authority 从裸 `script` 改为 `script:{sha256(url)[:12]}`（`_script_authority()`），`list_all_entries`/`ReposManagementPanel` 统计同步，同 entry_id 跨脚本不再被 dedupe 吞掉，新增 `test_authority_namespaced_by_url` 用例。
>
> 状态（2026-08-09 三线审查后修复）：**3.9 httpx.Client 显式 close 已补齐**：`OttFederationProvider.close()`（幂等，客户端未创建时安全）+ `main.py` teardown 接线（与 `infra.api_client.close()` 并列）。**3.9 脚本 authority 一致性已补齐**：`_script_authority` 移至 `ott_normalization.py`（单一事实源），`ScriptSandbox.execute` 计算后贯穿 `_normalize_entries(raw, authority)`，entry `authority` 与 `normalize_summary` 一致；`source_key` 保持稳定分组键（已注释说明）。

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

> 状态（2026-08-09 三线审查后修复）：**5.1 前置加固已落地**（seccomp 仍缺，留作 5.1 正式项）：① AST 检查新增 `BANNED_DUNDER_ATTRIBUTES`（16 个对象模型属性：`__class__`/`__mro__`/`__bases__`/`__subclasses__`/`__globals__`/`__closure__`/`__code__`/`__dict__`/`__builtins__`/`__self__`/`__func__`/`__getattribute__`/`__getattr__`/`__setattr__`/`__delattr__`/`__module__`），拦截 `().__class__.__subclasses__()` 类对象模型遍历（代码 `banned_object_model_access`）；`__init__` 不拦截（`super().__init__()` 合法，`def __init__` 是 FunctionDef 名不受影响，逃逸后续步骤已被拦）。② Landlock `/etc` 全目录读取收窄为逐文件 `/etc/resolv.conf` + `/etc/hosts` + `/etc/nsswitch.conf`（仅 READ_FILE，OSError 逐文件跳过）。③ 运行时 `_build_safe_builtins` 明确不 monkeypatch 对象内建（会破坏 bs4/Crypto），AST + 子进程隔离为边界，已注释说明。④ 端到端 Landlock 逃逸测试在真实内核 5.13+ 上验证仍 READ_BLOCKED。测试：`test_rejects_object_model_subclasses_escape`/`test_rejects_globals_attribute`/`test_allows_realistic_whitelisted_script`/`test_allows_super_init_in_class` + `TestLandlockNarrowing` 2 例，全绿。
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

> 状态（2026-08-08）：**7.1-7.3 文档与本地屏蔽机制已落地**（`docs/guides/ott-repo-governance.md` + `blocked_content_hashes` 本地清单）；7.2 的协议级 `revocations[]` 依赖 Phase 2.7；7.4 外部律师评审未启动。

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
9. 基线回归：每批改动后全量通过并刷新基线（当前 956 collected 全部通过，CI 全绿，2026-08-09）。

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
3. 极速杯服务（www.jsxiaoshi.com）可用性与抓取许可（1.4 验收前置；mock 验证已完成，真实服务验证仍待此确认）。
4. 无头浏览器类抓取是否立项（红线第 8 条默认禁止）。
