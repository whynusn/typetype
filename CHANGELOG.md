# 更新日志

本文档记录 typetype 项目所有版本的变更。遵循 [Semantic Versioning](https://semver.org/)。

**维护规则**：
- 变更记录按**日期倒序**排列（最新的在前）
- 按版本号分组，每个版本号内按**功能类型分类**（Added/Changed/Fixed/Removed）
- 详细的实现细节应记录在此，架构相关内容通过 `@see ARCHITECTURE.md` 指向
- 请勿在 `ARCHITECTURE.md` 中维护版本历史（该文档专注当前架构事实）

---

## [Unreleased] - In Development

### Added

- **内置 OTT Repo 政策收口**：保留 OTT L1 声明式规则的协议与联邦能力；未完成来源权利、归属和稳定性审核的具体规则不随官方内置 manifest 分发，`ott-script` 继续不进入内置仓。
- **智能路由（SmartRouteSelector）**：刷新/拉取链路按**实时延迟与连通性**在候选路径间选路——候选 = 原始地址 → jsDelivr CDN → 配置的镜像/代理前缀（`ott.route_mirrors`，如 ghproxy 形态）→ manifest mirrors，纯动态派生不硬编码。短超时（2s）并发探测 + TTL 缓存（`ott.route_probe_ttl_seconds`，默认 300s）+ 失败指数退避冷却（30s→300s 封顶）+ 真实请求回写（延迟 EWMA）。接入 manifest 拉取（`RepoManifestCache`）、instance 条目/分段（`OttCachedFetcher`）、脚本下载（`ScriptCache`）；不可达候选不再消耗 10s 超时，修复「刷新一直转圈直到 45s 硬超时」；`router=None` 时保持原固定 failover，测试兼容
- **内置默认文本源（ADR-011 Phase 4）**：首启自动注入 `file://` 内置 OTT Repo（经典中文短句 / 拼音声调练习 / 唐诗精选），完全离线可用；静态 profile 补齐 `sources.json` 与 `entries/{id}.json`，摘要不再嵌全文，entry_id 符合 schema pattern，逐条标注 rights/license/origin。内置仓允许 L0/L1 能力，但未经来源权利审核的规则源默认关闭，`ott-script` 不进入内置仓
- **默认内容独立仓库（ADR-011 Phase 4 收口）**：官方默认 OTT Repo 迁移到 `whynusn/typetype-default-ott-repo`；该仓后续归档，`resources/ott-repo` 作为客户端内置 file:// 仓唯一事实来源，不再依赖同步脚本
- **适配器包规范上移标准仓**：`docs/adapter-package.md` 与 `schemas/ott-adapter-v1.schema.json` 权威位置迁到 open-typing-texts，typetype SDK/测试引用兄弟仓，不再重复维护
- **OTT DSL 组合安全加固（ADR-011 Phase 1.5）**：整数纳入单值字节上限（`bit_length` 估算），超大位移直接拒绝，字面量/结果超限检查前置到求值器内部；新增组合矩阵 + 固定种子模糊测试，随机表达式只可能成功或抛 `DslError`
- **default_enabled 消费（ADR-011 Phase 3.4）**：联邦聚合按 manifest 声明的 `default_enabled` 启用/禁用 ott-instance 源，未声明时默认启用
- **manifest 条件请求与镜像 failover（ADR-011 Phase 3.1/3.2）**：拉取携带 `If-None-Match`，304 刷新缓存 mtime 不换内容；主地址失败时按已缓存 manifest 的 http(s) mirrors 依次回退，ETag 持久化到订阅
- **联邦客户端复用与结果缓存（ADR-011 Phase 3.9）**：rule/script 共用单个 `httpx.Client`，按订阅+manifest mtime 签名复用客户端实例；rule/script 条目结果按 `cache_ttl_seconds` 缓存，避免每次查询全量重抓
- **requires 协商（ADR-011 Phase 3.3）**：manifest 声明 `ott_core` 版本约束与 `client_features`，不满足整仓标记不兼容并跳过，订阅列表显示 `incompatible_reason`，不再静默部分启用
- **ott-bridge 决策落地（ADR-011 Phase 3.5）**：明确暂不实现 L2 provider；联邦跳过桥接源并在订阅面板显示"桥接源暂不支持"，ARCHITECTURE 同步为未落地
- **本地内容屏蔽清单（ADR-011 Phase 7.2）**：`blocked_content_hashes` 配置持久化，联邦按 `content_hash` 屏蔽条目详情，takedown 可即时生效；新增 OTT Repo 治理操作手册（贡献协议/收稿红线/takedown 流程）
- **L3 签名门槛（ADR-011 Phase 2.3）**：ott-script 仅允许 `trust_state=verified` 的仓库执行，未签名/未确认/签名失败仓库跳过；新增适配器签名方案设计文档（Phase 2.0，canonical JSON/裸 Ed25519/TOFU/撤销）

### Fixed

- **开源文库分组精度到源（authority）级**：列表按**每一条规则/源**分组展示（一言 / 极速杯 / 今日诗词桥接 / 英文名言 / 内置静态源各一组），组头显示源名（manifest `source.label` 注入 `_source_label`，不硬编码）+ 所属订阅源标识（`_repo_name` 小字）+ 计数/上限；订阅源（repo）本身不再作为分组出现在列表中（管理按钮仍作用于所属订阅源弹窗）。存量旧快照缺 `_source_label` 时回退 `source_label` 原文，自愈逻辑同步补写
- **刷新作用域与分组一致（源级）**：组头刷新改为 `refreshFederatedSource(authority)` → 只物化该源并重发列表（旧 repo 级 `refreshRepoEntries` 保留后端能力）；刷新动画标记改为 `refreshingFederatedSource`（authority），成功/失败/超时三路都清除标记——修复「刷新动画无限显示、没有结束状态」
- **源级刷新动画不再随机永转（worker 生命周期 + 双定时器）**：`RegistryAdapter` 提交 `QRunnable` 后曾不持有 Python wrapper 引用，跨线程排队的「清标记」连接随机丢失——文本已更新但组头转圈直到 45s 超时；现统一 `_start_worker()`（`setAutoDelete(False)` + `_active_workers` 持有到 `finished`）、成功/失败各只连一个槽并在 `try/finally` 中清标记 + 序号守卫。手动刷新与后台 revalidate 拆成两个独立 45s 单发定时器，操作完成即停表——不再出现「源级刷新已成功，残留 revalidate 定时器到点误报刷新超时」
- **规则/脚本源断网也计入刷新失败**：`OttRuleInterpreter` 在「一条都没抓到且请求/域名解析失败」时返回 `None`（配置非法/成功但空仍 `[]`）；`ScriptSandbox.execute_strict()` 区分执行失败（`None`，脚本内网络不可达/非零退出/超时/非法输出）与成功但空；`_RuleClient`/`_ScriptClient` 将 `None` 透传为源不可用，刷新全部断网时能真正提示「刷新失败，当前显示缓存快照」。脚本非零退出的日志只保留最后一行异常摘要（截断 400 字符），不再把整段 Python traceback 打进 WARNING
- **快照时间语义拆分（captured_at / last_checked_at）**：手动总刷新与源级刷新不再无条件推进 `captured_at`——内容与归属元数据未变时保留原内容更新时间，只写 `last_checked_at`；静态源点「检查更新」后 UI 显示「刚检查，内容无变化」，不再虚刷「刚刚/最新」。`EntrySnapshotStore` 原子写两套时间，旧快照自动补写
- **源健康状态持久化（SourceStatusStore）**：per-authority 记录最近检查/成功/失败时间、错误信息与连续失败计数；`SnapshotCatalogService` 物化后回写，进入开源文库时经 `getFederatedSourceStatuses` 同步到源组健康芯片，重启后状态仍在
- **源级刷新错误不再盖全列表**：`RegistryAdapter` 新增 `sourceStatusChanged(authority, status)`——单源刷新失败只在该源组头显示「刷新失败 · 显示缓存」芯片与 tooltip，列表和其他源保持可交互；只有总刷新全部失败才进入全局错误页
- **并发源级刷新动画独立化**：`refreshing_authority` 单值标记改为 `refreshing_authorities` 集合（Bridge `refreshingFederatedSources`），多源同时刷新各播各的动画，序号守卫保证旧 worker 晚完成不清新一轮标记
- **manifest 公共字段消费与 refresh 策略**：rule/bridge/script 的 `tags/default_enabled` 归一化保留；`rule.schedule` / 公共 `refresh` 映射为 `RefreshPolicy`（manual→on_demand，hourly/daily/weekly→interval），用户 per-source override 优先级不变；快照指纹比对纳入 `_refresh_policy` 与 `_repo_trust_state`
- **源卡片信息升级**：组头新增 L0-L3 能力层级 badge、repo trust badge（已验证/待确认/未验证/失败）、源健康芯片；随机源（rule/script/bridge）默认只显示最新一条，可点历史按钮展开最近 N 条；搜索扩展覆盖 `_source_label`/category/tags
- **新增 SourceInfoDialog**：展示源类型、authority、最近检查/成功/错误时间、所属订阅源描述与 license、不兼容原因；提供「跟随声明 / 仅手动 / 每小时 / 每天 / 每周」刷新频率覆盖（接 `setSourceRefreshOverride`），并可直接刷新该源
- **添加订阅支持目录预览**：`previewRepoManifest` 拉取 manifest 识别 `directory`，列出 `repository-ref` 供用户显式选择添加（不自动订阅）；`RepoConfigDialog` 补充描述/维护者/license/不兼容原因/不支持源展示
- **开源文库筛选修正**：来源筛选统一使用 `_source_label || source_label`，修复 instance 源（组名来自 `_source_label`、条目 `source_label` 为空）筛选失效的问题
- **断网刷新明确反馈，不再静默回退快照**：federation 物化统计成功/失败 authority（`last_list_ok/failed`，client 返回 `None` 视为源不可用），手动刷新（全部/源级）完成后检查——**全部失败 → 明确报错「刷新失败（网络不可达或源不可用），当前显示的是缓存快照」**；部分失败 → 日志提示；后台 revalidate 失败仍静默（保持快照视图不打扰）
- **订阅源卡片展示「N / M 条」上限进度**：组头计数区升级——外部 manifest 声明 `max_entries` 时显示「N / M 条」+ 细进度条（接近上限 80% 转琥珀色、满格绿色），未声明（无上限）保持「N 条」；快照归属元数据比对扩展至 `_repo_max_entries` 等全部字段——manifest 调整上限后 revalidate 自动补写，卡片展示即时更新。内置混合仓不声明该字段，避免将静态源上限误套到可选动态规则源
- **开源文库组内条目不再串组**：`RepoEntriesPanel` 分组重建改为两遍构建（先按条目顺序收集有序组 + 组内条目，再按组顺序整组渲染）——旧实现单遍追加，同组条目在 entries 中不连续（随机源多次物化、新旧条目按 captured_at 交错）时，后到的条目会被追加到别的组头之下（实测 jisubei 的条目跑到「英文名言」组下面），展开组只显示部分条目；现组头与组内条目永远连续输出
- **开源文库源组头可正常展开/收起**：`toggleGroup` 折叠判定曾写为 `!(x === false)`（恒等于 `x !== false`）——展开态点击恒置回展开、折叠态点击恒置回折叠，状态永不变、点击无法收起；现改为真正的状态切换（缺省展开，首次点击即折叠，再点展开）
- **开源文库归类自愈（订阅源分组不再拆散）**：旧构建物化的快照缺 `_repo_id`/`_repo_name` 归属字段，且因内容指纹相同被 revalidate 永久跳过补写——同一订阅源的条目曾按 authority 回退拆成多个假源组（组名还来自 QML 硬编码的 source_label→中文映射）。现快照指纹比对同时校验归属字段（缺失/变化即补写，内容未变时保留原 `captured_at` 不虚刷 freshness），并删除 QML 硬编码映射（组名统一由 manifest `name` 提供）；存量旧快照在下次进入开源文库时后台自动补写归组
- **开源文库视图 = 当前快照存储（永久语义）**：每次进入开源文库都同步显示当前全部已存快照（零网络、即时渲染、不白屏），随后后台重新物化过期源并原地更新列表——不再每次进入都全量重新物化（旧实现 15s 超时空白等待），也不停留在「仅首屏」的陈旧视图；存储新鲜度由后台 revalidate + RefreshScheduler + 过期/prune 机制维护，手动刷新才强制换新
- **刷新不再让条目变少**：`refresh_and_list_all` 返回值改为当前全部已存快照（物化只更新存储）——曾因部分源网络失败/超时整源从视图消失（「点刷新后变少很多」），其快照明明还在存储里；失败源保留旧快照（可刷新/可载入），视图只随存储变化、不随单次物化成败波动
- **开源文库「载入跟打」闪退/无限加载修复**：联邦条目载文（segmented instance / inline 规则源）改为同步镜像本地文库链路——旧实现经 worker 子线程构建会话 + `textContentLoaded` 间接回传，instance 源实测 **double free or corruption**（共享 httpx client 跨线程并发）、规则源信号丢失导致「一直加载动画」（快照明明在却不载文）。现主线程同步建会话 + 直发 `textLoaded`，与「本地文库」同一条落地链路
- **开源文库刷新按钮真正生效且按层级作用域**：rule/script/bridge 条目内存缓存（TTL 默认 3600s）与 instance 文件缓存曾拦截手动刷新——TTL 内点刷新返回旧条目。现手动刷新一律 force 绕过缓存：右栏「刷新」/列表顶部总刷新（`refreshFederatedAll`）全部源强制换新，源组头刷新（`refreshFederatedRepo`）只物化该订阅源下的全部源（不再全量列所有源再过滤），on_demand 源点一次换新一篇；刷新完成后视图走 `list_cached()` 纯读已落盘快照（不重物化其他源、不重置其他源 freshness 徽章/相对时间）；刷新动画同层级：列表级刷新盖整列表 loading，repo 刷新仅对应源组头转圈（`refreshingFederatedRepo`），列表保持可交互
- **后台 revalidate 不再虚刷 freshness**：`refresh_and_list_all` 非 force 路径按内容指纹（`snap_fingerprint`）比对——内容未变的快照跳过落盘、保留原 `captured_at`（曾无条件 `save(captured_at=now)`，每次进入开源文库后台刷新后所有源徽章被重置成「刚刚/最新」，即使根本没重新抓取）；内容真正变化（TTL 过期源重抓）或手动刷新（force）才更新时间戳。指纹由 catalog 层按内容相关字段自算（instance 摘要与 rule/script/bridge 条目无统一 `content_hash`）；旧快照无指纹首次 revalidate 补写（一次性）
- **刷新动画不再卡死/永转**：`RegistryAdapter` 恢复条目物化/刷新硬超时兜底（45s，`loadFederatedEntries` 重构时曾把旧 15s QTimer 兜底删掉）——网络 hang 时 worker 永不完成、loading/动画永转；现在到点只清理状态并提示「刷新超时，请检查网络」（后台 revalidate 超时静默保持快照视图），不等待 worker 线程
- **开源文库按订阅源分组展示**：列表改为「源组头 + 组内条目」两级结构——条目物化时按**所属订阅源动态归组**（federation 注入 `_repo_id/_repo_name/_repo_url/_repo_max_entries`，不硬编码）；组头 = 展开/收起 + 源名 + 条目计数 + 源级刷新（动画只在组头播放一份，同源几千文本不会同时播几千份动画）+ 管理按钮；卡片只保留 freshness 徽章，刷新操作收敛到组头。修复 delegate 绑定 TypeError（不可见分支对 undefined role 求值报错，双组件 Loader 方案）
- **订阅源配置弹窗取代独立管理页**：`ReposManagementPage`/`ReposManagementPanel` 删除——组头「管理该源」打开 `RepoConfigDialog`（启用/信任确认/删除订阅）；「添加订阅」在开源文库列表头部弹窗输入 URL；**删除订阅连带清理该源全部已缓存文本**（`catalog.remove_repo` → `store.clear_authority`，不再残留孤儿快照目录），列表即时移除该源
- **文本计数 x / 上限**：manifest 新增可选字段 `max_entries`（订阅源声明文本上限，缺失/非正 = 无上限），组头显示「当前 N 条」或「N / M 条」；repo 级刷新（`refreshFederatedRepo`）只物化该订阅源下的全部源，其他订阅源零调用
- **脚本下载 GitHub raw 超时兜底**：`ScriptCache` 与 `OttCachedFetcher` 主地址失败时自动走 jsDelivr CDN 降级（raw.githubusercontent.com → cdn.jsdelivr.net，与 manifest 拉取同款），修复脚本源/instance 源在国内网络下 `read operation timed out`
- **占位订阅清理后补回内置源**：配置里只剩 `example.org` 测试占位时，清理后自动重新注入内置 OTT Repo，避免应用启动后源列表为空

### Removed

- **typetype 内 `public-ott-repo/`**：默认内容已由独立仓库接管，避免 GitHub main 旧版违规内容（hitokoto rule / daily_quote 脚本）继续随客户端分发
- **OTT Repo 控制面（ADR-010）**：去中心化文本源订阅生态。多 authority 联邦聚合（`OttFederationConfig`）、订阅管理 UI（`ReposManagementPanel`）、声明式规则源（L1 `OttRuleInterpreter`）、ott-script 脚本源（L3 子进程沙箱）、旧 `registry.primary_url` 自动迁移
- **打词率（word typing rate）指标**：统计会话中 CJK 字符被作为词组输入的比例。
  算法将间隔 ≤ 300ms 的连续 CJK 字符视为词组输入，打词率 = 词组字符数 / 总 CJK 字符数 × 100。
  - ：记录每个字符的提交时间戳
  - ：打词率计算核心逻辑
  - ：领域模型字段
  -  和 ：成绩展示和历史记录
  - 新测试文件 （10 个用例覆盖边界条件）
  - 对应 Issue #2: 用户反馈 "统计里能加上打词率"

### Fixed

- **内置源 Windows 无法加载**：`file://` URI 转本地路径兼容 Windows 盘符（`/D:/...` → `D:\...`），manifest 占位符展开使用正斜杠盘符形式，修复 CI Windows 上内置源 0 条目的问题
- **ott-script 沙箱逃逸（严重）**：原进程内 `exec()` + 模块注入可被 `json.__builtins__['open']` 单行逃逸。重写为独立 Python 子进程（`ott_script_runner.py`），资源限制（256MB 内存 / 30s CPU / RLIMIT_NPROC=0）+ AST 白名单 import + 别名解析 + `__builtins__` 检测
- **规则解释器 ReDoS 与 fetch 大小绕过**：正则匹配输入截断至 50KB 防灾难性回溯；`_fetch()` 改为 streaming 截断（不依赖 `content-length` 头，堵住 chunked 传输绕过）
- **用户配置写入路径污染**：`RuntimeConfig._save_to_file()` 尊重显式加载的 `_config_path`，避免测试或临时配置写入真实 `~/.config/typetype/config.json`
- **启动默认载文报错**：首次进入跟打页时优先使用本地可用来源自动载文，避免默认远程来源（如 `old`）在服务端不可用时每次启动弹出“无法获取网络文本”
- **启动默认网络载文误报失败**：远程文本解析兼容 `content`/`text`/`textContent`/`articleContent` 与顶层响应格式，避免 `/api/v1/texts/latest/{sourceKey}` 返回 200 时仍显示“无法获取网络文本”
- **个人中心趋势图横轴**：图表内部类目改用唯一索引，横轴标签按 `ChartView.plotArea` 中心点独立渲染，避免 Qt Charts 因重复空白类目导致刻度重叠、缺失或柱状数据错位
- **个人中心趋势粒度**：`按小时` 改为小时刻度，`按周` 改为 ISO 周刻度，`按月` 改为后端按月聚合，避免前端把日数据误折叠导致月图为空
- ** 重复项修复**：移除条目列表中多余的"用时"重复项

- **文本排行页崩溃**：`TextLeaderboardPage.qml` 缺少 `DataCell` 类型引用导致页面无法打开；排行榜布局改为响应式（宽屏左右分栏、窄屏上下堆叠），列宽不再截断内容
- **开源文库加载状态**：开源文库列表不再错误复用 `typetype-server` 的 `textListLoading`，改为独立的 `catalogLoading` 属性

### Changed

- **个人中心趋势图**：趋势图改用 PySide6 Qt Charts 成品 `ChartView`/`BarSeries` 组件渲染，并沿用 RinUI 主题色与时间范围切换
- **统一载文中心**：极速杯、本地文库、开源文库、练单器、自定义 5 个载文入口合并为单一 `TextLoadHubPage.qml`，顶部 Segmented 切换来源，左侧列表/输入区与右侧切片设置/预览区统一；删除 `JisuBeiPage.qml`、`LocalArticlesPage.qml`、`TextLibraryPage.qml`、`CustomLoadTextPage.qml`、`TrainerPage.qml`
- **开源文库动态源快照机制**：联邦条目物化落盘（EntrySnapshotStore），选中载入从快照取（修复随机源选中失配）；RepoEntriesPanel 卡片新增新鲜度徽章/相对时间/单源刷新；订阅管理页支持 per-source 刷新间隔设置（用户覆盖 source_refresh_overrides）；常驻 RefreshScheduler 只自动刷新 interval 到期源
- **载文中心重构**：载文中心扩展为 6 个来源 tab（本地文库/开源文库/练单器/晴发文/AI 推荐/自定义，RinUI Segmented 切换）；开源文库 tab 直接浏览联邦聚合条目（选中即载入，删除独立条目列表页 `RepoEntriesPage.qml`）；晴发文/AI 推荐入口纳入载文中心（即时拉取面板）；订阅管理独立为 `ReposManagementPage.qml`；修复 F2 载文设置入口、OTT 分段大小 hint（`segment_size_hint`）丢失与 bridge 源 authority 缺失
- **顶部来源切换**：`SelectorBar` 替换为 RinUI `Segmented`/`SegmentedItem`，带背景容器与间距，视觉层次更清晰；无边框、紧贴下方组件的问题已解决
- **个人中心重构**：登录后展示用户信息卡片、6 项统计卡片（今日字数/总字数/平均速度/最高速度/平均键准/总场次）、最近 30 天打字趋势迷你柱状图、最近 50 条成绩列表（右键复制成绩）
- **全应用内部通知统一**：抽取 `AppNotification.qml` + `AppNotificationManager.qml`，替换 `HistoryArea`、`TextInfoCard`、`DailyLeaderboard`、`UploadTextPage` 中各页面硬编码的 `copyToast`/`InfoBar`
- **自定义载文去重**：统一载文中心内的自定义面板隐藏与顶部来源切换功能重叠的"从文本库选择"，仅保留纯文本输入 + 切片设置

### Added

- **打字历史记录持久化**：新增 `TypingHistoryStore` 端口、`JsonTypingHistoryStore` 实现、`TypingHistoryGateway` 业务网关；每次跟打完成自动持久化到 `~/.local/share/typetype/typing_history.json`，最多 5000 条；Bridge 暴露 `typingHistoryCount`/`typingHistoryAverageSpeed`/`typingHistoryMaxSpeed`/`typingHistoryAverageKeyAccuracy`/`typingHistoryTotalChars`/`typingHistoryRecords`/`typingHistoryDailyTrend`
- **Bridge `catalogLoading` 属性**：开源文库目录加载的独立状态信号

---

## [0.2.0] - 2026-06-04

### Changed

- **Bridge 架构重构**：分片载文业务逻辑下沉到 `TypingSessionContext`，Bridge 瘦身为薄适配层（属性代理/信号转发/Slot 入口）；删除 200+ 行业务逻辑代码
- **NavigationView 单实例重构**：移除 StackView 及 push/pop 动画，改用 `pageInstances` 字典缓存实例，通过 `visible` + `active` 属性切换页面；所有 QML 页面信号守卫迁移为 `page.active`
- **Bridge 类型合规**：`UploadTextAdapter` 和 `Bridge` 类型注解从 `integration.*` 改为 `ports.*`（消除 Presentation→Integration 违规）
- **Bridge 代码清理**：提取 `_clear_text_id()` 方法消除 4 处重复

### Added

- **TypingSessionContext 会话状态机**：集中管理会话阶段、来源模式、上传资格推导、分片载文
- **配置文件自动初始化**：启动时检查 `config.json` 不存在则从 example 复制
- **服务地址运行时配置**：SettingsPage 输入框 → Bridge.setBaseUrl() → 闭包传播到所有依赖对象 + 持久化
- **回改/退格统计指标**：`SessionStat` 新增 `backspace_count`/`correction_count`，Wayland 通过 evdev 检测
- **macOS 兼容**：新增 Quartz CGEventTap 全局键盘监听；配置和数据库写入用户可写目录
- **分片载文修复**：光标重置防越界、`_color_text` 边界检查、片段切换时达标次数归零
- **文档体系重构**：ARCHITECTURE.md 精简（去掉重复目录树，从 683→170 行）；AGENTS.md 精简（去掉重复导航卡，从 497→200 行）；7 个 ADR 覆盖核心架构决策；tutorials/ 和 guides/ 目录有实际内容

### Fixed

- **本地文本加载两阶段异步**：Worker 只读文件，HTTP 回查移至 daemon thread（消除主线程阻塞）
- **FluentPage OpacityMask 移除**：GPU 离屏渲染阻塞页面切换
- **ContextMenu height 动画修复**：`enter` transition 改为 `Behavior on height`（修复首次打开缩回 6px）
- **FluentPage anchors → x/y**：消除 ColumnLayout 与 anchors 冲突警告
- **TextAdapter 统一走 Worker**：所有文本加载后台执行，不再主线程同步 I/O

---

## [0.1.0] - 2026-04-13

### Changed

- 架构重构：只有服务端文本才能提交成绩；客户端移除 hash 计算；删除无感上传回调链路；source_key 不再进入成绩提交链路

### Added

- 新增 TextUploader Port、text_id 生成逻辑、无感上传链路；移除配置中 text_id 字段

---

## [0.0.1] - 2026-04-06

### Changed

- 基于当前源码重写：补充对象装配、QML 页面结构、真实数据流与边界判断
- 2026-04-03: 重写文本加载闭口后的边界规则

### Added

- 2026-03-21: 首次创建架构文档

---

**最后更新**: 2026-06-04  
**相关文档**: [@see docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) — 当前架构事实源
