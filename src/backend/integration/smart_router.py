"""智能路由选择器：按实时延迟与连通性在候选路径（原始/CDN/镜像/代理前缀）间选路。

背景：OTT 拉取链路（manifest / instance 条目 / 脚本下载）此前是固定顺序
failover——主地址失败才依次尝试 jsDelivr / mirrors，且每个候选走 10s 超时
串行等待。国内网络下主地址（raw.githubusercontent.com 等）常不可达，一次
刷新在不可达候选上浪费大量时间，触发 45s 刷新硬超时。

本模块将「固定顺序」升级为「智能选路」：
- 候选派生（纯动态，不硬编码）：原始 URL → jsDelivr 转换 → 配置的前缀镜像
  （`ott.route_mirrors`，前缀 + 完整 URL，如 ghproxy 形态）→ 调用方显式镜像
  （manifest mirrors / instance mirror_url）
- 按 host 统计：延迟 EWMA + 连续失败次数 + 探测时间戳 + 冷却截止
- 探测：短超时（默认 2s）并发 HEAD（任意 HTTP 状态码即视为可达，405 也算
  连通）→ HEAD 网络错误再 GET；结果缓存 TTL（默认 300s），TTL 内不重复探测
- 失败冷却：探测/请求失败 → 指数退避冷却（30s → 60s → 120s → 240s → 封顶
  300s），冷却中排到候选末尾且不探测
- 真实请求回写（record）：成功更新 EWMA，失败累计冷却——被动观测与主动
  探测共用同一统计表
- 排序：已知成功按延迟升序 → 未知按派生顺序 → 冷却/失败最后。调用方按序
  尝试、第一个成功即止，排序只优化顺序，不改变容错语义

线程安全：统计表加锁；探测用独立短生命周期 httpx.Client 并发（共享 client
跨线程并发不安全，见 AGENTS.md「联邦载文同步镜像本地链路」）；真实请求由
调用方在自身线程串行执行，路由层只读统计。
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable
from urllib.parse import urlparse

import httpx

from ..utils.logger import log_info, log_warning
from .ott_normalization import redact_url, to_jsdelivr_url

if TYPE_CHECKING:
    from ..config.runtime_config import OttConfig

# 冷却封顶与探测默认参数（策略常量，不随候选路径硬编码）
_COOLDOWN_CAP_S = 300.0
_COOLDOWN_BASE_S = 30.0
_EWMA_ALPHA = 0.3  # 新观测权重（越小越平滑）
_DEFAULT_PROBE_TIMEOUT_S = 2.0
_DEFAULT_PROBE_WORKERS = 4


def _host_of(url: str) -> str:
    try:
        host = urlparse(url).hostname
    except (ValueError, OSError):
        return ""
    return host or ""


@dataclass
class _HostStat:
    """单个 host 的连通性统计（延迟 EWMA + 失败冷却）。"""

    latency_ewma: float | None = None
    consecutive_failures: int = 0
    last_probe: float = 0.0
    cooldown_until: float = 0.0
    last_success: float = 0.0
    last_error: str = field(default="")


class SmartRouteSelector:
    """候选路径选路器（integration 层，无 UI/状态依赖）。

    用法：
        router = SmartRouteSelector(config)
        for url in router.ordered_candidates(primary, mirrors=[mirror_url]):
            data = fetch(url)
            router.record(url, ok=data is not None, latency=elapsed)
            if data is not None:
                break
    """

    def __init__(
        self,
        config: "OttConfig | None" = None,
        probe_timeout: float = _DEFAULT_PROBE_TIMEOUT_S,
        probe_workers: int = _DEFAULT_PROBE_WORKERS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if config is None:
            from ..config.runtime_config import OttConfig

            config = OttConfig()
        self._prefix_mirrors = [
            str(m)
            for m in (config.route_mirrors or [])
            if m and str(m).startswith(("http://", "https://"))
        ]
        self._probe_ttl = max(1.0, float(config.route_probe_ttl_seconds))
        self._probe_timeout = max(0.2, float(probe_timeout))
        self._probe_workers = max(1, int(probe_workers))
        self._clock = clock
        self._lock = threading.Lock()
        self._stats: dict[str, _HostStat] = {}

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def ordered_candidates(
        self, url: str, mirrors: list[str] | None = None
    ) -> list[str]:
        """返回按实时连通性/延迟排序的候选 URL 列表。

        调用方按序尝试、第一个成功即止。file:// 直接返回原值（本地文件
        不走网络路由）。探测失败/无统计时静默退化为派生顺序（原始 →
        jsDelivr → 前缀镜像 → 显式镜像），永不抛异常。
        """
        if url.startswith("file://"):
            return [url]
        candidates = self._derive(url, mirrors)
        if len(candidates) <= 1:
            return candidates
        self._probe_if_stale(candidates)
        with self._lock:
            snapshot = {c: self._stats.get(_host_of(c)) for c in candidates}
        now = self._clock()
        return sorted(
            candidates,
            key=lambda c: self._sort_key(c, snapshot[c], candidates.index(c), now),
        )

    def record(self, url: str, ok: bool, latency: float = 0.0) -> None:
        """真实请求结果回写（成功更新延迟 EWMA；失败累计冷却）。

        与探测共用同一统计表：被动观测与主动探测互相增强。
        """
        host = _host_of(url)
        if not host:
            return
        with self._lock:
            stat = self._stats.setdefault(host, _HostStat())
            if ok:
                stat.latency_ewma = (
                    latency
                    if stat.latency_ewma is None
                    else (1 - _EWMA_ALPHA) * stat.latency_ewma + _EWMA_ALPHA * latency
                )
                stat.consecutive_failures = 0
                stat.cooldown_until = 0.0
                stat.last_success = self._clock()
            else:
                stat.consecutive_failures += 1
                stat.cooldown_until = self._clock() + self._backoff(
                    stat.consecutive_failures
                )

    # ------------------------------------------------------------------
    # 候选派生（纯动态，不硬编码）
    # ------------------------------------------------------------------

    def _derive(self, url: str, mirrors: list[str] | None) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []

        def add(candidate: str | None) -> None:
            if candidate and candidate not in seen:
                seen.add(candidate)
                out.append(candidate)

        add(url)
        add(to_jsdelivr_url(url))  # raw.githubusercontent.com → cdn.jsdelivr.net
        for prefix in self._prefix_mirrors:
            # 通用镜像/代理前缀（前缀 + 完整 URL，如 ghproxy 形态）
            add(prefix.rstrip("/") + "/" + url)
        for mirror in mirrors or []:
            add(mirror)  # 调用方显式镜像（manifest mirrors / instance mirror_url）
        return out

    # ------------------------------------------------------------------
    # 探测
    # ------------------------------------------------------------------

    def _probe_if_stale(self, candidates: list[str]) -> None:
        now = self._clock()
        with self._lock:
            due = [c for c in candidates if self._probe_due_locked(_host_of(c), now)]
        if not due:
            return
        try:
            with ThreadPoolExecutor(
                max_workers=min(self._probe_workers, len(due))
            ) as executor:
                results = list(executor.map(self._probe_url, due))
        except Exception:  # 探测绝不外抛：静默退化为派生顺序
            return
        for url, (ok, latency) in zip(due, results):
            self._record_probe(url, ok, latency)

    def _record_probe(self, url: str, ok: bool, latency: float) -> None:
        """探测结果回写：更新 last_probe（TTL 复用依据）+ 统计（与真实请求同表）。"""
        host = _host_of(url)
        if not host:
            return
        with self._lock:
            stat = self._stats.setdefault(host, _HostStat())
            stat.last_probe = self._clock()
        self.record(url, ok=ok, latency=latency)

    def _probe_due_locked(self, host: str, now: float) -> bool:
        if not host:
            return False
        stat = self._stats.get(host)
        if stat is None:
            return True
        if stat.cooldown_until > now:
            return False  # 冷却中：不探测，排末尾
        if stat.last_probe <= 0:
            return True  # 从未探测过（monotonic 时间戳为 0 的初值）
        return (now - stat.last_probe) >= self._probe_ttl

    def _probe_url(self, url: str) -> tuple[bool, float]:
        """单候选探测：HEAD 优先（任意 HTTP 状态码=可达，405 也算连通），
        HEAD 网络错误再 GET。仅网络层错误视为失败。"""
        for method in ("HEAD", "GET"):
            try:
                with httpx.Client(
                    timeout=self._probe_timeout,
                    trust_env=False,
                    follow_redirects=False,
                ) as client:
                    t0 = self._clock()
                    with client.stream(method, url):
                        return True, self._clock() - t0
            except httpx.HTTPError as e:
                if method == "GET":
                    log_warning(f"[SmartRouter] 探测失败 {redact_url(url)} — {e}")
            except OSError as e:
                log_warning(f"[SmartRouter] 探测失败 {redact_url(url)} — {e}")
        return False, 0.0

    # ------------------------------------------------------------------
    # 排序
    # ------------------------------------------------------------------

    def _sort_key(
        self, url: str, stat: _HostStat | None, index: int, now: float
    ) -> tuple[int, float, int]:
        """排序键：(优先级组, 组内数值, 派生序号)。

        组 0 = 已知成功（按延迟 EWMA 升序）；组 1 = 未知（按派生顺序）；
        组 2 = 冷却/失败（按剩余冷却时间）。
        """
        if stat is None:
            return (1, float(index), index)
        if stat.cooldown_until > now:
            return (2, stat.cooldown_until - now, index)
        if stat.latency_ewma is None:
            return (2, 0.0, index)
        return (0, stat.latency_ewma, index)

    @staticmethod
    def _backoff(failures: int) -> float:
        return min(_COOLDOWN_CAP_S, _COOLDOWN_BASE_S * (2 ** min(failures - 1, 4)))


def log_route_choice(url: str, candidates: list[str]) -> None:
    """日志辅助：输出最终选路顺序（供刷新排查）。"""
    if len(candidates) > 1:
        log_info(
            "[SmartRouter] 选路: "
            + " → ".join(redact_url(c) for c in candidates[:3])
            + (" …" if len(candidates) > 3 else "")
            + f" （{url}）"
        )
