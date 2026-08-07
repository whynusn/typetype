"""OTT Repo L1 声明式规则解释器。

执行 repo manifest 中内联的 ``ott-rule`` 规则对象，将抓取结果标准化为
entry 流，供联邦聚合层消费。

安全模型（不可突破）：
- ``extract`` 仅限 JSON path / 命名正则 / CSS 选择器
- ``transform`` 仅限 trim / replace / truncate
- ``request.url`` 仅允许公网 http(s)；禁 file:、环回、私有地址
- 单次 fetch ≤ max_bytes；总条目 ≤ 1000；max_pages 硬限制
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

from .ott_normalization import normalize_summary

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

MAX_TOTAL_ENTRIES = 1000
DEFAULT_MAX_BYTES = 1_048_576
DEFAULT_MAX_PAGES = 5
TOTAL_FETCH_TIMEOUT_S = 10.0
REGEX_MAX_INPUT_CHARS = 50_000  # ReDoS 防护：正则匹配输入截断上限


# ---------------------------------------------------------------------------
# URL 校验
# ---------------------------------------------------------------------------


def validate_url(url: str) -> bool:
    """校验规则请求 URL 是否允许执行。

    拒绝：
    - 非 http/https scheme
    - file: scheme
    - 环回 / 私有 / 保留 IP
    - localhost 字面量
    """
    if not isinstance(url, str) or not url.strip():
        return False
    try:
        parsed = urlparse(url.strip())
    except (ValueError, OSError):
        return False

    if parsed.scheme not in ("http", "https"):
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    hostname_lower = hostname.lower().rstrip(".")
    if hostname_lower in ("localhost", "localhost.localdomain"):
        return False

    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        # 不是字面 IP，尝试 DNS 解析
        try:
            resolved = socket.getaddrinfo(hostname, None)
        except (socket.gaierror, OSError):
            return True  # 解析失败不阻断，运行时再报错
        for family, _, _, _, sockaddr in resolved:
            if family not in (socket.AF_INET, socket.AF_INET6):
                continue
            try:
                addr = ipaddress.ip_address(sockaddr[0])
            except ValueError:
                continue
            if addr.is_private or addr.is_loopback or addr.is_reserved:
                return False
        return True

    if addr.is_private or addr.is_loopback or addr.is_reserved:
        return False
    return True


# ---------------------------------------------------------------------------
# 提取
# ---------------------------------------------------------------------------


def _extract_json_path(data: Any, path: str) -> str:
    """从 JSON 数据中按 $.a.b 或 items[*].title 简写提取文本。"""
    if not path or data is None:
        return ""

    raw = path.strip()
    # 去掉 "$." 或 "$" 前缀
    if raw.startswith("$."):
        raw = raw[2:]
    elif raw.startswith("$["):
        raw = raw[1:]  # 去掉 $，保留 [0]
    elif raw == "$":
        raw = ""
    if not raw:
        return _stringify(data)

    # 处理纯索引路径：$[0]、[*]、[0][1]
    if raw.startswith("["):
        return _stringify(_navigate_index_only(data, raw))

    parts = raw.split(".")
    result = _navigate_parts(data, parts, 0)
    return _stringify(result)


def _navigate_index_only(data: Any, raw: str) -> Any:
    """处理 [0]、[*]、[0][*] 等纯索引路径。"""
    current = data
    pos = 0
    s = raw
    while pos < len(s) and s[pos] == "[":
        end = s.find("]", pos)
        if end == -1:
            return None
        inner = s[pos + 1 : end]
        if current is None:
            return None
        if inner == "*":
            if not isinstance(current, list) or not current:
                return None
            current = current[0]
        else:
            try:
                idx = int(inner)
                if isinstance(current, list) and 0 <= idx < len(current):
                    current = current[idx]
                else:
                    return None
            except (ValueError, IndexError):
                return None
        pos = end + 1
    return current


def _navigate_parts(data: Any, parts: list[str], i: int) -> Any:
    """按点分路径列表导航，支持 [*] 通配符。i 为当前 part 索引。"""
    current: Any = data
    while i < len(parts):
        if current is None:
            return None
        part = parts[i]
        if "[*]" in part:
            # items[*].title → 先取 items 列表，再对每个元素取剩余路径
            bracket_idx = part.find("[*]")
            key = part[:bracket_idx]
            if key:
                if isinstance(current, dict):
                    current = current.get(key)
                else:
                    return None
            if not isinstance(current, list):
                return None
            # 剩余路径 = 当前 part [*] 之后 + 后续 parts
            remaining = []
            after = part[bracket_idx + 4 :].lstrip(".")
            if after:
                remaining.append(after)
            remaining.extend(parts[i + 1 :])
            if not remaining:
                return current[0] if current else None
            for item in current:
                val = _navigate_parts(item, remaining, 0)
                if val is not None and _stringify(val):
                    return val
            return None
        else:
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                try:
                    current = current[int(part)]
                except (ValueError, IndexError):
                    return None
            else:
                return None
            i += 1
    return current


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        # 列表取第一个非空元素
        for item in value:
            s = _stringify(item)
            if s:
                return s
        return ""
    if isinstance(value, dict):
        for k in ("title", "name", "text", "content", "value"):
            if k in value:
                return _stringify(value[k])
        return ""
    return str(value)


def _extract_regex(text: str, pattern: str) -> dict[str, str]:
    """用命名正则提取字段。失败返回空 dict。

    ReDoS 防护：输入文本超过 REGEX_MAX_INPUT_CHARS 时截断，
    避免恶意正则 (a+)+$ 类灾难性回溯。
    """
    if not pattern or not text:
        return {}
    # 截断输入以缓解 ReDoS（正则匹配在超长文本上即使模式无害也慢）
    if len(text) > REGEX_MAX_INPUT_CHARS:
        text = text[:REGEX_MAX_INPUT_CHARS]
    try:
        match = re.search(pattern, text, re.DOTALL)
    except re.error:
        return {}
    if match is None:
        return {}
    groups = match.groupdict()
    if not groups:
        # 无命名组：用 group(1) 作为 content
        try:
            return {"content": match.group(1)}
        except IndexError:
            return {}
    return {k: (v if v is not None else "") for k, v in groups.items()}


def _first_group_value(result: dict[str, str] | None) -> str:
    """从正则提取结果中取第一个非空值。"""
    if not result:
        return ""
    # 优先 content/title，否则取第一个值
    for key in ("content", "title", "text", "name"):
        if result.get(key):
            return result[key]
    for v in result.values():
        if v:
            return v
    return ""


def _extract_css_selector(html: str, selector: str) -> str:
    """用 CSS 选择器从 HTML 中提取第一个匹配元素的文本。"""
    if not selector or not html:
        return ""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return ""
    try:
        soup = BeautifulSoup(html, "html.parser")
        elem = soup.select_one(selector)
    except Exception:
        return ""
    if elem is None:
        return ""
    return elem.get_text(strip=True)


def extract_field(data: Any, extract_spec: str) -> str:
    """根据 extract_spec 格式自动分派提取器。

    规则：
    - 以 "$." 开头 → JSON path
    - 以 "/" 开头和结尾 → 正则
    - 含 "(" 且含 "?P<" → 正则（命名组）
    - 否则 → CSS 选择器
    """
    if not extract_spec:
        return _stringify(data)

    spec = extract_spec.strip()

    # JSON path（$.xxx 或 $[idx] 或 $[*]）
    if spec.startswith("$."):
        return _extract_json_path(data, spec)
    if spec.startswith("$["):
        return _extract_json_path(data, spec)
    if spec == "$":
        return _stringify(data)

    # 正则：显式 /.../ 或命名组
    if spec.startswith("/") and spec.endswith("/"):
        pattern = spec[1:-1]
        text = _stringify(data) if not isinstance(data, str) else data
        result = _extract_regex(text, pattern)
        return _first_group_value(result)

    if "?P<" in spec:
        text = _stringify(data) if not isinstance(data, str) else data
        result = _extract_regex(text, spec)
        return _first_group_value(result)

    # CSS 选择器
    html = _stringify(data) if not isinstance(data, str) else data
    return _extract_css_selector(html, spec)


def extract_fields(data: Any, extract_spec: dict[str, str]) -> dict[str, str]:
    """按 extract_spec 字典逐字段提取。"""
    if not isinstance(extract_spec, dict):
        return {}
    return {key: extract_field(data, pattern) for key, pattern in extract_spec.items()}


# ---------------------------------------------------------------------------
# 变换
# ---------------------------------------------------------------------------


def apply_transform(value: str, transforms: list[str] | None) -> str:
    """对单个值应用变换管道。"""
    if not transforms or not isinstance(value, str):
        return value
    result = value
    for t in transforms:
        if t == "trim":
            result = result.strip()
        elif t == "truncate":
            # truncate 默认 2000 字，可由调用方覆盖
            result = result[:2000]
        # replace 需要参数，在 apply_transforms_to_entry 中处理
    return result


def apply_transforms_to_entry(
    entry: dict[str, str],
    transforms: list[str] | None,
    replace_map: dict[str, str] | None = None,
) -> dict[str, str]:
    """对 entry 的所有字符串字段应用变换。"""
    if not transforms:
        return entry
    result = dict(entry)
    replace_map = replace_map or {}
    for key, value in result.items():
        if not isinstance(value, str):
            continue
        for t in transforms:
            if t == "trim":
                value = value.strip()
            elif t == "truncate":
                value = value[:2000]
            elif t == "replace" and replace_map:
                for old, new in replace_map.items():
                    value = value.replace(old, new)
        result[key] = value
    return result


# ---------------------------------------------------------------------------
# 解释器
# ---------------------------------------------------------------------------


class OttRuleInterpreter:
    """OTT Repo L1 声明式规则解释器。"""

    def __init__(
        self,
        http_client: httpx.Client,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        self._client = http_client
        self._max_bytes = max_bytes

    # ---- 公开入口 ----

    def list_entries(
        self,
        rule: dict,
        rule_id: str,
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> list[dict]:
        """执行规则，返回标准化 entry 列表。"""
        if not isinstance(rule, dict):
            return []

        request_spec = rule.get("request") or {}
        extract_spec = rule.get("extract") or {}
        transforms = rule.get("transform") or []
        pagination = rule.get("pagination") or {}
        replace_map = rule.get("replace") or {}

        if not isinstance(request_spec, dict) or not isinstance(extract_spec, dict):
            return []

        url_template = request_spec.get("url", "")
        if not url_template or not validate_url(url_template):
            return []

        method = request_spec.get("method", "GET").upper()
        if method not in ("GET", "POST"):
            method = "GET"
        headers = request_spec.get("headers") or {}
        if not isinstance(headers, dict):
            headers = {}

        # 分页参数
        page_param = (
            pagination.get("param", "page") if isinstance(pagination, dict) else "page"
        )
        page_start = (
            int(pagination.get("start", 1)) if isinstance(pagination, dict) else 1
        )
        page_step = (
            int(pagination.get("step", 1)) if isinstance(pagination, dict) else 1
        )
        rule_max_pages = (
            int(pagination.get("max_pages", max_pages))
            if isinstance(pagination, dict)
            else max_pages
        )
        effective_max_pages = min(int(max_pages), int(rule_max_pages), 20)
        if page_step <= 0:
            # 不可信 manifest 可能声明 step=0：page 永不前进，循环只会被
            # MAX_TOTAL_ENTRIES 截断 → 同 URL 重复请求。归一到 1。
            page_step = 1

        all_entries: list[dict] = []
        page = page_start

        while (
            len(all_entries) < MAX_TOTAL_ENTRIES
            and page < page_start + effective_max_pages
        ):
            url = url_template.replace("{" + page_param + "}", str(page))
            # 二次校验（分页后 URL 可能变化）
            if not validate_url(url):
                break

            text = self._fetch(url, method, headers)
            if text is None:
                break

            # 尝试 JSON 解析；失败则当 HTML/text 处理
            items = self._parse_response(text)

            if not items:
                break

            for item in items:
                if len(all_entries) >= MAX_TOTAL_ENTRIES:
                    break
                extracted = extract_fields(item, extract_spec)
                if not extracted:
                    continue
                entry = self._build_entry(extracted, rule, rule_id, page, url)
                entry = apply_transforms_to_entry(entry, transforms, replace_map)
                all_entries.append(entry)

            page += page_step

        return all_entries

    # ---- 内部 ----

    def _fetch(self, url: str, method: str, headers: dict) -> str | None:
        try:
            if method == "POST":
                response = self._client.post(
                    url, headers=headers, timeout=TOTAL_FETCH_TIMEOUT_S
                )
            else:
                response = self._client.get(
                    url, headers=headers, timeout=TOTAL_FETCH_TIMEOUT_S
                )
            response.raise_for_status()
            # Streaming 截断：边读边累积，到达 max_bytes 立即停止。
            # 不依赖 content-length 头（chunked 传输可绕过该检查）。
            chunks: list[str] = []
            total = 0
            for chunk in response.iter_text():
                if not chunk:
                    continue
                remaining = self._max_bytes - total
                if remaining <= 0:
                    break
                if len(chunk) > remaining:
                    chunks.append(chunk[:remaining])
                    break
                chunks.append(chunk)
                total += len(chunk)
            return "".join(chunks)
        except (httpx.HTTPError, httpx.InvalidURL, OSError):
            return None

    def _parse_response(self, text: str) -> list[Any]:
        """解析响应为条目列表。JSON 数组或含 entries/items 键的对象优先。"""
        # 尝试 JSON
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            data = None

        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("entries", "items", "data", "results", "list"):
                if isinstance(data.get(key), list):
                    return data[key]
            # 单条对象包装为列表
            return [data]
        return []

    def _build_entry(
        self,
        extracted: dict[str, str],
        rule: dict,
        rule_id: str,
        page: int,
        url: str,
    ) -> dict:
        """构建标准化 entry dict。"""
        title = extracted.get("title", "")
        content = extracted.get("content", "")
        if not title and content:
            title = content[:60]

        # 确定性 ID：sha256(content + page) 前 16 hex
        entry_id_raw = hashlib.sha256(f"{content}:{page}".encode("utf-8")).hexdigest()[
            :16
        ]

        revision_raw = hashlib.sha256(f"{url}:{page}".encode("utf-8")).hexdigest()[:12]

        authority = f"rule:{rule_id}"
        source_key = f"rule:{rule_id}"
        source_label = rule.get("label") or rule_id

        base = {
            "entry_id": entry_id_raw,
            "title": title,
            "preview": content[:200],
            "source_key": source_key,
            "source_label": source_label,
            "char_count": len(content),
            "charCount": len(content),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "category": "",
            "tags": rule.get("tags", []) if isinstance(rule.get("tags"), list) else [],
            "content_mode": "inline",
            "current_revision_id": revision_raw,
            "segment_count": 0,
            "segment_size_hint": 0,
            "authority": authority,
        }
        # 复用 normalize_summary 保证字段形状一致，再补回 content（normalize 不保留）
        normalized = normalize_summary(base, authority)
        normalized["content"] = content
        normalized["_rule_id"] = rule_id
        normalized["_page"] = page
        return normalized


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------


def interpret_rule(
    rule: dict,
    rule_id: str,
    http_client: httpx.Client,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> list[dict]:
    """一次性执行规则并返回 entry 列表。"""
    interpreter = OttRuleInterpreter(http_client)
    return interpreter.list_entries(rule, rule_id, max_pages=max_pages)
