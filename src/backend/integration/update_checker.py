"""OTA 更新检查与镜像下载（ADR-014 决策 2/3/4）。

职责：
- ``check_for_update()``：GitHub Releases API 权威 + ``version.json`` CDN
  降级链，返回 ``UpdateInfo | None``（无新版返回 None；全部失败静默，不抛异常）。
- ``download()``：流式下载 + sha256 强制校验；校验失败/网络错误删除临时文件
  并返回 False（调用方换下一个镜像）。
- ``build_download_candidates()``：直链 + 各镜像前缀拼接（去重）。

安全不变式（ADR-014 决策 4）：
- ``version.json`` 清单必须 Ed25519 验签（``UPDATE_PUBKEY``），验签失败拒绝；
- 每个下载必须 sha256 校验（来源：已验签 manifest 或 API 返回）；
- 更新器只是文件替换，不执行任何随包脚本。

明确不做：
- 不产生任何 UI / 线程（线程由调用方 worker 负责）；
- 不做平台替换/重启（属 updater 脚本职责）。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ..utils.logger import log_info, log_warning
from ..version import APP_VERSION
from .ott_normalization import redact_url

# GitHub Releases API（主路径，ADR-014 决策 2）。未认证限流 60 req/h/IP，
# 手动检查 + 自动检查（默认 24h）远在额度内。
GITHUB_API_URL = "https://api.github.com/repos/whynusn/typetype/releases/latest"

# version.json 降级链：raw.githubusercontent.com → jsDelivr → ghproxy 系。
# 前缀代理形态，可注入/可配置（ADR-014 决策 2、决策 6 update.mirrors）。
VERSION_MANIFEST_PATHS = [
    "https://raw.githubusercontent.com/whynusn/typetype/main/version.json",
    "https://cdn.jsdelivr.net/gh/whynusn/typetype@main/version.json",
    (
        "https://ghproxy.net/https://raw.githubusercontent.com/"
        "whynusn/typetype/main/version.json"
    ),
    (
        "https://gh-proxy.com/https://raw.githubusercontent.com/"
        "whynusn/typetype/main/version.json"
    ),
    (
        "https://gh.ddlc.top/https://raw.githubusercontent.com/"
        "whynusn/typetype/main/version.json"
    ),
]

# 下载镜像前缀（前缀代理），直链优先、镜像按序 fallback。
# 2026-08-13 实测（curl，12s 超时）：ghproxy.net/gh-proxy.com/gh.ddlc.top/
# ghproxy.link/gh.996650.xyz 可达；ghproxy.com/mirror.ghproxy.com 等已失效。
DEFAULT_DOWNLOAD_MIRRORS = [
    "https://ghproxy.net/",
    "https://gh-proxy.com/",
    "https://gh.ddlc.top/",
    "https://ghproxy.link/",
    "https://gh.996650.xyz/",
]

# 版本清单签名公钥（Ed25519，裸 hex 或 ``ed25519:`` 前缀）。
# ⚠️ 占位：当前为测试密钥，正式发布时替换为独立生成的发布 key
# （与 ADR-011 L3 适配器 key 隔离，信任域分离，ADR-014 决策 4）。
UPDATE_PUBKEY = "6ec026104d99919fdb050537d69ea4a6b71993ce124906437aeb4abc1335d16d"

# 单次下载默认 chunk 大小（流式写盘 + 增量 sha256）。
_DOWNLOAD_CHUNK_SIZE = 65536


@dataclass
class UpdateInfo:
    """更新检查结果。

    ``assets`` 为 dict 列表，每条含 ``name`` / ``url`` / ``sha256``。
    GitHub API 不返回资产 sha256 时该字段为空串，调用方需从已验签
    manifest 补全后再下载（下载强制校验 sha256）。
    """

    version: str
    assets: list[dict]
    source: str  # "github_api" | "manifest"
    release_notes: str = ""


def _parse_version(value: str) -> tuple[tuple[int, int, int], list[str] | None]:
    """解析 ``major.minor.patch[-prerelease]`` 版本。

    容忍 ``v`` 前缀与多余数字段。返回
    ``((major, minor, patch), prerelease_identifiers | None)``；
    无法解析的段按 0 处理（比较趋同，不崩溃）。
    """
    text = str(value).strip().lstrip("vV")
    main, sep, pre = text.partition("-")
    if not sep:
        pre = ""
    nums: list[int] = []
    for part in main.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        nums.append(int(digits) if digits else 0)
    while len(nums) < 3:
        nums.append(0)
    pre_ids: list[str] | None = None
    if pre:
        pre_ids = [ident for ident in pre.split(".") if ident]
    return (nums[0], nums[1], nums[2]), pre_ids


def _compare_prerelease(a: list[str], b: list[str]) -> int:
    """semver prerelease 标识符比较：数值标识符 < 字母数字标识符，较短者小。"""
    for x, y in zip(a, b):
        x_num = x.isdigit()
        y_num = y.isdigit()
        if x_num and y_num:
            if int(x) != int(y):
                return -1 if int(x) < int(y) else 1
            continue
        if x_num != y_num:
            return -1 if x_num else 1
        if x != y:
            return -1 if x < y else 1
    if len(a) != len(b):
        return -1 if len(a) < len(b) else 1
    return 0


def _version_gt(a: str, b: str) -> bool:
    """semver 比较：``a > b``。

    规则：core (major.minor.patch) 大者新；core 相同则 release（无
    prerelease）恒大于带 prerelease 的版本；两者都是 prerelease 时按
    semver 规则比较标识符。
    """
    a_core, a_pre = _parse_version(a)
    b_core, b_pre = _parse_version(b)
    if a_core != b_core:
        return a_core > b_core
    if a_pre is None and b_pre is not None:
        return True
    if a_pre is not None and b_pre is None:
        return False
    if a_pre is None and b_pre is None:
        return False
    return _compare_prerelease(a_pre, b_pre) > 0


def _strip_key_prefix(value: str) -> str:
    """剥离 ``ed25519:`` 前缀（裸 hex 则原样返回）。"""
    return value.split(":", 1)[1] if ":" in value else value


def _direct_download_url(release_tag: str, asset_name: str) -> str:
    """GitHub Releases 直链。tag 缺 ``v`` 前缀时自动补上（Release tag 均为 ``v*``）。"""
    tag = str(release_tag).strip()
    if tag and not tag.startswith("v"):
        tag = "v" + tag
    return (
        "https://github.com/whynusn/typetype/releases/download/"
        f"{tag}/{str(asset_name).strip()}"
    )


class UpdateChecker:
    """OTA 更新检查器（纯逻辑，无 UI / 无线程）。

    网络通过注入的 ``httpx.Client`` 或可 mock 的 fetch 函数完成；所有
    方法失败均静默（返回 None / False），由调用方决定 UI 表现。
    """

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        fetch_json: Callable[[str], dict | None] | None = None,
        fetch_bytes: Callable[[str], bytes | None] | None = None,
        current_version: str = APP_VERSION,
        manifest_urls: list[str] | None = None,
        download_mirrors: list[str] | None = None,
        update_pubkey: str = UPDATE_PUBKEY,
    ) -> None:
        """构造检查器。

        Args:
            client: 复用的 httpx.Client（未传则内部自建，带 User-Agent——
                GitHub API 强制要求）。与 fetch_* 二选一即可。
            fetch_json: 注入的 JSON 拉取函数（测试用）；未传则走 client。
            fetch_bytes: 注入的字节拉取函数（测试用）；未传则走 client 流式。
            current_version: 当前运行版本（默认 APP_VERSION）。
            manifest_urls: version.json 降级链 URL（默认 VERSION_MANIFEST_PATHS）。
            download_mirrors: 下载镜像前缀列表（默认 DEFAULT_DOWNLOAD_MIRRORS，
                可注入/可配置，见 ADR-014 决策 6 ``update.mirrors``）。
            update_pubkey: 清单验签公钥（默认 UPDATE_PUBKEY）。
        """
        if client is None:
            timeout = httpx.Timeout(15.0, connect=5.0)
            client = httpx.Client(
                timeout=timeout,
                follow_redirects=True,
                headers={"User-Agent": f"typetype-update-checker/{APP_VERSION}"},
            )
        self._client = client
        self._fetch_json = fetch_json
        self._fetch_bytes = fetch_bytes
        self._current_version = str(current_version)
        self._manifest_urls = list(manifest_urls or VERSION_MANIFEST_PATHS)
        self._download_mirrors = list(download_mirrors or DEFAULT_DOWNLOAD_MIRRORS)
        self._update_pubkey = str(update_pubkey or "")

    # ---- 更新检查 ----

    def check_for_update(self) -> UpdateInfo | None:
        """检查更新：GitHub API 权威 → version.json 降级链。

        API 失败/非 2xx/解析失败/无新版 → 降级 manifest 链；全部失败返回
        None（静默，UI 不阻塞）。
        """
        info = self._check_github_api()
        if info is not None:
            return info
        return self._check_version_manifest()

    def _check_github_api(self) -> UpdateInfo | None:
        data = self._get_json(GITHUB_API_URL)
        if data is None:
            return None
        tag = data.get("tag_name")
        if not isinstance(tag, str) or not tag.strip():
            return None
        version = tag.strip().lstrip("vV")
        if not _version_gt(version, self._current_version):
            return None
        assets = self._parse_api_assets(data.get("assets"))
        body = data.get("body")
        release_notes = str(body) if isinstance(body, str) else ""
        log_info(f"[UpdateChecker] GitHub API 发现新版本 {version}")
        return UpdateInfo(
            version=version,
            assets=assets,
            source="github_api",
            release_notes=release_notes,
        )

    @staticmethod
    def _parse_api_assets(raw_assets: Any) -> list[dict]:
        assets: list[dict] = []
        if not isinstance(raw_assets, list):
            return assets
        for item in raw_assets:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            entry: dict[str, str] = {
                "name": name,
                "url": str(item.get("browser_download_url") or item.get("url") or ""),
            }
            digest = item.get("sha256") or item.get("digest")
            entry["sha256"] = digest.strip() if isinstance(digest, str) else ""
            assets.append(entry)
        return assets

    def _check_version_manifest(self) -> UpdateInfo | None:
        for url in self._manifest_urls:
            data = self._get_json(url)
            if data is None:
                continue
            info = self._build_manifest_info(data, url)
            if info is not None:
                return info
            # 验签失败/结构非法 → 尝试下一个镜像
        return None

    def _build_manifest_info(self, data: dict, url: str) -> UpdateInfo | None:
        signature = data.get("signature")
        if not isinstance(signature, str) or not signature.strip():
            log_warning(f"[UpdateChecker] 清单无签名，拒绝: {redact_url(url)}")
            return None
        version = data.get("version")
        if not isinstance(version, str) or not version.strip():
            return None
        version = version.strip().lstrip("vV")
        if not self._verify_manifest_signature(data, signature):
            log_warning(f"[UpdateChecker] 清单验签失败，拒绝: {redact_url(url)}")
            return None
        if not _version_gt(version, self._current_version):
            return None
        assets: list[dict] = []
        raw_assets = data.get("assets")
        if isinstance(raw_assets, list):
            for item in raw_assets:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                if not isinstance(name, str) or not name.strip():
                    continue
                asset_url = item.get("url")
                sha256 = item.get("sha256")
                assets.append(
                    {
                        "name": name,
                        "url": str(asset_url or ""),
                        "sha256": str(sha256 or ""),
                    }
                )
        log_info(f"[UpdateChecker] version.json 发现新版本 {version}")
        return UpdateInfo(version=version, assets=assets, source="manifest")

    def _verify_manifest_signature(self, data: dict, signature: str) -> bool:
        """Ed25519 验签（ADR-014 决策 4 / ADR-011 决策 12 规范）。

        canonical JSON = 剔除 ``signature`` 键 + ``sort_keys`` +
        ``ensure_ascii=False`` + 紧凑分隔符；signature 与公钥均为裸 hex
        （容忍 ``ed25519:`` 前缀）。验签失败返回 False（拒绝该清单）。
        """
        if not self._update_pubkey:
            return False
        try:
            pubkey_bytes = bytes.fromhex(_strip_key_prefix(self._update_pubkey))
            sig_bytes = bytes.fromhex(_strip_key_prefix(signature))
            if len(pubkey_bytes) != 32 or not sig_bytes:
                return False
            canonical = {k: v for k, v in data.items() if k != "signature"}
            canonical_bytes = json.dumps(
                canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
            key = Ed25519PublicKey.from_public_bytes(pubkey_bytes)
            key.verify(sig_bytes, canonical_bytes)
            return True
        except (ValueError, TypeError, InvalidSignature):
            return False

    # ---- 下载 ----

    def download(self, url: str, sha256: str, dest: Path) -> bool:
        """流式下载到 dest，sha256 强制校验。

        先写入 ``dest.name + ".part"`` 临时文件，校验通过后原子替换
        （``os.replace``，失败回滚删除临时文件）。校验失败 / 网络错误 /
        超时 → 删除临时文件并返回 False（调用方换下一个镜像）。dest 父
        目录不存在时自动创建。
        """
        expected = str(sha256 or "").strip().lower()
        if not expected:
            log_warning("[UpdateChecker] 缺少预期 sha256，拒绝下载")
            return False
        dest_path = Path(dest)
        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False
        tmp_path = dest_path.with_name(dest_path.name + ".part")
        try:
            if self._fetch_bytes is not None:
                data = self._fetch_bytes(url)
                if data is None:
                    log_warning(f"[UpdateChecker] 下载失败: {redact_url(url)}")
                    return False
                digest = hashlib.sha256(data).hexdigest()
                tmp_path.write_bytes(data)
            else:
                digest = self._stream_download(url, tmp_path)
        except httpx.HTTPError as e:
            log_warning(f"[UpdateChecker] 下载失败: {redact_url(url)} — {e}")
            self._remove_file(tmp_path)
            return False
        except OSError as e:
            log_warning(f"[UpdateChecker] 写文件失败: {dest_path} — {e}")
            self._remove_file(tmp_path)
            return False
        if digest != expected:
            log_warning(f"[UpdateChecker] sha256 不匹配，丢弃: {redact_url(url)}")
            self._remove_file(tmp_path)
            return False
        try:
            tmp_path.replace(dest_path)
        except OSError as e:
            log_warning(f"[UpdateChecker] 移动临时文件失败: {dest_path} — {e}")
            self._remove_file(tmp_path)
            return False
        return True

    def _stream_download(self, url: str, tmp_path: Path) -> str:
        """经 httpx 流式下载到 tmp_path，返回内容 sha256。失败抛 httpx/OSError。"""
        hasher = hashlib.sha256()
        with self._client.stream("GET", url) as response:
            response.raise_for_status()
            with tmp_path.open("wb") as fh:
                for chunk in response.iter_bytes(chunk_size=_DOWNLOAD_CHUNK_SIZE):
                    hasher.update(chunk)
                    fh.write(chunk)
        return hasher.hexdigest()

    @staticmethod
    def _remove_file(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    # ---- 下载候选 ----

    def build_download_candidates(
        self, release_tag: str, asset_name: str, mirrors: list[str] | None = None
    ) -> list[str]:
        """构造下载候选：直链 + 各镜像前缀拼接（去重，保持顺序）。

        ``mirrors`` 为 None 时使用实例默认镜像列表（可注入/可配置）。
        """
        direct = _direct_download_url(release_tag, asset_name)
        candidates: list[str] = [direct]
        seen = {direct}
        for mirror in mirrors if mirrors is not None else self._download_mirrors:
            prefix = str(mirror).strip()
            if not prefix:
                continue
            if not prefix.endswith("/"):
                prefix += "/"
            candidate = prefix + direct
            if candidate not in seen:
                seen.add(candidate)
                candidates.append(candidate)
        return candidates

    # ---- 网络原语 ----

    def _get_json(self, url: str) -> dict | None:
        if self._fetch_json is not None:
            try:
                data = self._fetch_json(url)
            except Exception as e:  # noqa: BLE001 - 注入函数失败按不可达处理
                log_warning(f"[UpdateChecker] 拉取失败: {redact_url(url)} — {e}")
                return None
            return data if isinstance(data, dict) else None
        try:
            response = self._client.get(url)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as e:
            log_warning(f"[UpdateChecker] HTTP 请求失败: {redact_url(url)} — {e}")
            return None
        except (ValueError, TypeError, OSError) as e:
            log_warning(f"[UpdateChecker] 响应解析失败: {redact_url(url)} — {e}")
            return None
        return data if isinstance(data, dict) else None
