# ADR-014: OTA 更新检查与镜像加速下载（GitHub Releases）

<!-- 状态: accepted | 决策日期: 2026-08-13 | 最后验证: 2026-08-13 -->

> 实施状态（2026-08-13，Wave 2）：**决策 1-6 已落地**。`version.py`（APP_VERSION）+ `build-release.yml` 新增 `assert-version` job（tag==pyproject==APP_VERSION 三断言）；`update_checker.py`（API→version.json 降级链 + 镜像下载 + sha256 强制校验 + Ed25519 验签）；`update_worker.py`/`update_adapter.py`/`resources/updater/{sh,bat}`/设置页「关于与更新」区；`update` 配置段入 v2 schema。镜像默认列表已按 2026-08-13 实测更新（见决策 3）。`UPDATE_PUBKEY` 仍为测试密钥占位，正式发布前须替换（待确认 1）。

> 本 ADR 与 [ADR-013](./013-converge-to-three-repo-model.md) 正交（三仓收敛不依赖本机制），独立评审与排期。核心结论：**typetype 内置基于 GitHub Releases 的 OTA 更新检查（API 权威 + version.json CDN 降级链），二进制下载走内置镜像列表 fallback，所有下载强制 sha256 校验，版本清单 Ed25519 验签（独立于 L3 适配器 key）**。

## 背景

现状事实（2026-08-13 核验）：

1. **没有任何更新检查机制**：grep `src/`/`scripts` 无 update/ota/check_update 相关代码，用户只能手动上 GitHub 下载。
2. **运行时读不到版本号**：版本唯一事实源是 `pyproject.toml:3`（`version = "0.1.0"`），Nuitka 独立产物内不可读。且**发布 tag 与源码版本已脱节**——`pyproject.toml` 停在 `0.1.0`，实际 Releases 已迭代到 `v0.4.5`（`gh release list` 核验），说明发布流程从未同步两处版本。
3. **发布产物三平台齐全**：`build-release.yml`（292 行）含 `build-linux`（`typetype-linux-amd64.tar.gz`，ubuntu-latest）、`build-windows`（`typetype-windows-amd64.zip`，windows-latest）、`build-macos`（`typetype-macos.zip`，`main.app` → ditto，macos-latest）三个 job。`gh release view v0.4.5` 核验三个资产均在（Linux 18 下载 / macOS 10 / Windows 8）。**⚠️ 已知问题：macOS 产物被用户反馈无法正常打开使用**（Gatekeeper 未签名/未公证等，见待确认 4）。
4. **签名基建可复用**：ADR-011 已建立裸 Ed25519 hex + canonical JSON 签名规范，并有 CI 签名流水线（`adapter-publish.yml`，`ADAPTER_SIGNING_PUBKEY`/`ADAPTER_SIGNING_SECRET_KEY` secrets）。

**目标**：用户打开应用即能感知新版本（设置页 + 可选启动检查），一键下载安装更新；下载在国内网络环境下经镜像加速；安全不变式（验签 + 校验和）不因镜像而削弱。

## 选项

| 方案 | 描述 | 判断 |
|:---|:---|:---|
| A. 系统包管理器 | 走 Snap/Flatpak/Homebrew 分发，更新交给包管理器 | ❌ 项目当前是 Nuitka 独立产物直发，无包仓库维护；三平台各自包源维护成本高 |
| B. 仅 GitHub API 检查 + 直链下载 | 最简实现，无镜像 | ❌ 国内访问 GitHub 不稳定，下载体验差，未解决核心痛点 |
| C. GitHub API + version.json CDN 降级链 + 镜像 fallback（本方案） | 检查与下载都分级降级 | ✅ 选中：信任锚在签名，镜像只加速传输 |
| D. 自建更新服务器 | 完全可控 | ❌ 与「三仓去中心化、零自建服务」定位冲突 |

## 决策

1. **运行时版本单一事实源**。新增 `src/backend/version.py` 的 `APP_VERSION` 常量作为运行时版本唯一来源。`build-release.yml` 增加一步：发布 tag（`v*`）与 `APP_VERSION` 一致性断言，阻止版本漂移（现状 pyproject 0.1.0 vs Releases v0.4.5 已脱节）。`pyproject.toml` 版本与 `APP_VERSION` 由 CI 断言一致（同一次发布两个来源，双断言）。

2. **版本检查：GitHub Releases API 权威 + manifest CDN 降级链**。
   - 主路径：`GET https://api.github.com/repos/whynusn/typetype/releases/latest` → `tag_name` + `assets[]`；semver 比较（可复用 `ott_federation_provider.py:66` 的版本约束解析思路）。未认证限流 60 req/h/IP，手动检查 + 自动检查（默认 24h）远在额度内。
   - 降级链：API 不可达（网络封锁/限流）→ 仓库内 `version.json` 清单，经 `raw.githubusercontent.com` → jsDelivr `cdn.jsdelivr.net` → ghproxy 系镜像依次。全部失败则静默，UI 不阻塞。

3. **二进制下载镜像链**。直链 `https://github.com/whynusn/typetype/releases/download/{tag}/{asset}` 优先；内置镜像列表（前缀代理形态，如 ghproxy 系）按序 fallback，命中即用、失败换下一个。镜像列表放配置 `update.mirrors`（默认内置，用户可增删/调序）。**每个下载必须校验 sha256**（来源：已验签 manifest 或 API 返回），校验失败立即丢弃并换下一个镜像，杜绝镜像投毒。

4. **清单签名与安全不变式**。`version.json`（CI 从 release 生成，含 tag / 各平台资产 / sha256）经 Ed25519 签名，复用 ADR-011 决策 12 的裸 Ed25519 hex + canonical JSON 规范；**签名 key 独立于 L3 适配器 key**，避免「能分发代码的 key」与「能宣告新版本的 key」共用（信任域隔离）。不变式：清单必须验签；下载必须校验 sha256；更新器不执行任何随包脚本（解压 → 替换 → 重启）；更新路径与 ADR-010/011 的规则/脚本沙箱体系互不接触（更新器只是文件替换，不是执行通道）。

5. **更新流程**。启动后台异步检查（worker，静默失败）+ 设置页「检查更新」按钮手动触发。有新版 → 下载至临时目录 → sha256 校验 → 用户确认 → 平台小更新器（`updater.sh` / `updater.bat` / macOS `updater.sh`）替换安装目录并重启。Nuitka 产物为自包含用户级目录，替换安全；不做差分更新（YAGNI），每次全量归档。替换用原子目录切换（新目录就绪 → 改名切换 → 失败回滚保留旧目录）。

6. **配置段 `update`**。`update: {enabled, auto_check, check_interval_hours, channel, mirrors[]}`；自动检查默认开启、失败静默；`channel` 预留（stable/beta）。纳入 ADR-013 的 v2 schema（由 ADR-013 的迁移逻辑一并处理默认值）。

## 影响

### 新增文件

| 文件 | 职责 |
|:---|:---|
| `src/backend/version.py` | `APP_VERSION` 运行时版本唯一事实源 |
| `src/backend/integration/update_checker.py` | GitHub API → version.json 降级链 + 镜像下载 + sha256 校验 + 清单验签 |
| `src/backend/workers/update_worker.py` | 后台异步检查，静默失败 |
| `src/backend/presentation/adapters/update_adapter.py` + bridge 槽/属性 | `checkUpdate` / `updateAvailable` / `updateProgress` / `updateStatus` 等 |
| `resources/updater/updater.sh` / `updater.bat` | 平台替换/重启小工具（macOS 复用 updater.sh，`main.app` 整体替换） |
| `scripts/gen_version_manifest.py` | CI 生成并签名 `version.json`（tag / assets / sha256 / Ed25519 签名） |
| QML：`SettingsPage.qml` 新增「关于/更新」区 | 当前版本 + 检查更新 + 更新进度/结果 |

### CI（`build-release.yml` + `adapter-publish.yml` 机制复用）

- 发布时：tag == `APP_VERSION` 断言 → 收集三平台资产 → 计算 sha256 → 生成 `version.json` → 独立 Ed25519 key 签名 → 作为资产附到 release + 提交到仓库 `version.json`（CDN 降级链用）。
- 签名 key 存 GitHub secrets（如 `UPDATE_SIGNING_PUBKEY`/`UPDATE_SIGNING_SECRET_KEY`），与 `ADAPTER_SIGNING_*` 分开。

### 测试

版本比较（semver 边界）、镜像 fallback（首镜像失败换次镜像）、sha256 校验失败丢弃、离线静默、清单验签失败拒绝、API → CDN 降级、替换失败回滚（mock 目录切换）。

### 风险

| 风险 | 等级 | 缓解 |
|:---|:---|:---|
| 更新器替换安装目录失败/断电中断 | 中 | 先下载完整归档并校验；原子目录切换，失败回滚保留旧目录 |
| 镜像站不可用/被投毒 | 中 | 多镜像 fallback + 清单验签 + sha256 强制校验；镜像仅加速传输，信任锚在签名 |
| GitHub API 限流/封锁 | 低 | version.json CDN 降级链 |
| macOS 产物已知打不开（Gatekeeper） | 中 | 本次更新器机制不解决打包质量问题；若 macOS 产物无法使用，则 macOS 端更新器可能长期无实际可分发产物，见待确认 4 |

## 待确认（实施后状态）

1. **版本清单签名 key**（✅ 需在正式发布前完成）：独立生成发布 key（与 ADR-011 L3 适配器 key 隔离——「能宣告新版本并替换整个应用的 key」与「能分发沙箱内脚本的 key」是不同信任域，泄露影响面差一个量级），私钥存 GitHub secret `UPDATE_SIGNING_SECRET_KEY`，公钥替换 `update_checker.py:UPDATE_PUBKEY`（当前为测试密钥占位），并更新 `scripts/gen_version_manifest.py` 默认值。
2. 自动检查默认间隔（落地为 24h）与「更新提示」交互形式（落地为设置页标记；启动自动检查静默、设置页打开时展示）。
3. **镜像站默认列表** ✅ 已实测（2026-08-13，curl 12s 超时，两批 20 个候选）：可用 `ghproxy.net`(1.1s)/`gh-proxy.com`(1.7s)/`gh.ddlc.top`(1.8s)/`ghproxy.link`(1.1s)/`gh.996650.xyz`(1.3s)；失效 `ghproxy.com`/`mirror.ghproxy.com`/`gh.llkk.cc`/`ghps.cc` 等。`DEFAULT_DOWNLOAD_MIRRORS` 已更新为 5 个实测可用镜像；jsDelivr（`cdn.jsdelivr.net`，稳定 200）同时用于 manifest 降级链与默认 hub URL。⚠️ 第三方镜像稳定性随网络环境波动，若上线后发现失效需替换。
4. **macOS 产物问题** ✅ 已批准独立立项（2026-08-13）：`typetype-macos.zip` 用户反馈无法正常打开（疑 Gatekeeper 未签名/未公证，或 `--mode=app` 产物结构问题）→ 单独立项跟踪（另开 ADR/issue），本 ADR 的 Linux/Windows 落地不受阻塞。
