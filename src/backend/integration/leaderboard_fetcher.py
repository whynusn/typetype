"""排行榜数据获取器。"""

from collections.abc import Callable
from typing import Any

from ..infrastructure.api_client import ApiClient
from ..utils.logger import log_warning


class LeaderboardFetcher:
    """排行榜数据获取器，从服务器获取排行榜数据。"""

    def __init__(
        self,
        api_client: ApiClient,
        base_url: str,
        token_provider: Callable[[], str] = lambda: "",
    ):
        self._api_client = api_client
        self._base_url = base_url
        self._token_provider = token_provider

    def update_base_url(self, new_base_url: str) -> None:
        """更新 base_url。"""
        self._base_url = new_base_url

    def _get_auth_headers(self) -> dict[str, str]:
        token = self._token_provider()
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}

    def _check_network_error(self) -> None:
        """检查 ApiClient 是否有未处理的网络错误，有则重新抛出。"""
        err = self._api_client.last_error
        if err is not None:
            raise err

    def get_catalog(self) -> list[dict[str, Any]] | None:
        """获取服务端文本来源目录。

        Returns:
            来源列表，每个元素包含 sourceKey, label 等字段，失败返回 None
        """
        url = f"{self._base_url}/api/v1/texts/catalog"
        response = self._api_client.request(
            "GET", url, headers=self._get_auth_headers()
        )
        if response is None:
            log_warning("[LeaderboardFetcher] 获取文本来源目录失败")
            self._check_network_error()
            return None
        if isinstance(response, dict):
            data = response.get("data")
            if isinstance(data, list):
                return data
        return None

    def get_latest_text_by_source(self, source_key: str) -> dict[str, Any] | None:
        """获取指定来源的最新文本。

        Args:
            source_key: 文本来源标识，如 "jisubei"

        Returns:
            包含 id, content, title 等字段的字典，失败返回 None
        """
        url = f"{self._base_url}/api/v1/texts/latest/{source_key}"
        response = self._api_client.request(
            "GET", url, headers=self._get_auth_headers()
        )
        if response is None:
            log_warning(f"[LeaderboardFetcher] 获取最新文本失败: {source_key}")
            self._check_network_error()
            return None
        if isinstance(response, dict):
            data = response.get("data")
            if isinstance(data, dict):
                return data
        return None

    def get_texts_by_source(self, source_key: str) -> list[dict[str, Any]] | None:
        """获取来源下所有文本的摘要列表。

        Args:
            source_key: 文本来源标识，如 "jisubei"

        Returns:
            文本摘要列表，每个元素包含 id, title 等字段，失败返回 None
        """
        url = f"{self._base_url}/api/v1/texts/by-source/{source_key}"
        response = self._api_client.request(
            "GET", url, headers=self._get_auth_headers()
        )
        if response is None:
            log_warning(f"[LeaderboardFetcher] 获取文本列表失败: {source_key}")
            self._check_network_error()
            return None
        if isinstance(response, dict):
            data = response.get("data")
            if isinstance(data, list):
                return data
        return None

    def get_text_by_id(self, text_id: int) -> dict[str, Any] | None:
        """通过文本 ID 获取文本详情。

        Args:
            text_id: 文本 ID

        Returns:
            包含 id, content, title 等字段的字典，失败返回 None
        """
        url = f"{self._base_url}/api/v1/texts/{text_id}"
        response = self._api_client.request(
            "GET", url, headers=self._get_auth_headers()
        )
        if response is None:
            log_warning(f"[LeaderboardFetcher] 获取文本详情失败: text_id={text_id}")
            self._check_network_error()
            return None
        if isinstance(response, dict):
            data = response.get("data")
            if isinstance(data, dict):
                return data
        return None

    def get_leaderboard(
        self, text_id: int, page: int = 1, size: int = 50
    ) -> dict[str, Any] | None:
        """获取指定文本的排行榜。

        Args:
            text_id: 文本ID
            page: 页码（从1开始）
            size: 每页大小

        Returns:
            包含 leaderboard, total, page, size 等字段的分页数据，失败返回 None
        """
        url = f"{self._base_url}/api/v1/texts/{text_id}/leaderboard"
        response = self._api_client.request(
            "GET",
            url,
            params={"page": page, "size": size},
            headers=self._get_auth_headers(),
        )
        if response is None:
            log_warning(f"[LeaderboardFetcher] 获取排行榜失败: text_id={text_id}")
            self._check_network_error()
            return None
        if isinstance(response, dict):
            data = response.get("data")
            if isinstance(data, dict):
                # 先做日期格式归一化（处理服务端返回的 records 中的日期）
                self._normalize_leaderboard_dates(data)
                # 转换字段名：服务端返回 records → 前端期望 leaderboard
                records = data.get("records", [])
                total = data.get("total", 0)
                return {
                    "leaderboard": records,
                    "total": total,
                    "text_info": None,  # TODO: 如需文本标题等信息可以后续添加
                }
        return None

    @staticmethod
    def _normalize_leaderboard_dates(data: dict) -> None:
        """将排行榜记录中的 createdAt 统一转为 ISO 字符串。

        Jackson 可能将 LocalDateTime 序列化为数组 [yyyy,MM,dd,HH,mm,ss]
        而非 ISO 字符串，此处做防御性转换。
        """
        # 数据可能在 records 中（服务端原始响应）或者已经转成 leaderboard
        records = data.get("records") or data.get("leaderboard")
        if not isinstance(records, list):
            # 这是正常情况，在 loadCatalog 等调用中不会有 records
            return
        from ..utils.logger import log_info

        log_info(
            f"[LeaderboardFetcher] Processing {len(records)} records, first record keys: {list(records[0].keys()) if records else 'none'}"
        )
        for record in records:
            # 防御：服务端可能返回 created_at（snake_case）
            if "created_at" in record and "createdAt" not in record:
                log_info(
                    f"[LeaderboardFetcher] Renaming created_at -> createdAt for record: {record}"
                )
                record["createdAt"] = record.pop("created_at")

            created_at = record.get("createdAt")
            log_info(
                f"[LeaderboardFetcher] Processing createdAt: type={type(created_at)}, value={created_at}"
            )
            if isinstance(created_at, list) and len(created_at) >= 5:
                # [yyyy, MM, dd, HH, mm] or [yyyy, MM, dd, HH, mm, ss]
                parts = [str(int(x)).zfill(2) for x in created_at[:6]]
                while len(parts) < 6:
                    parts.append("00")
                record["createdAt"] = (
                    f"{parts[0]}-{parts[1]}-{parts[2]}T{parts[3]}:{parts[4]}:{parts[5]}"
                )
            elif (
                isinstance(created_at, dict)
                and "year" in created_at
                and "month" in created_at
                and "day" in created_at
            ):
                # Jackson 可能将 LocalDateTime 序列化为对象格式 {year, month, day, hour, minute, second}
                year = created_at.get("year", 0)
                month = created_at.get("month", 1)
                day = created_at.get("day", 1)
                hour = created_at.get("hour", 0)
                minute = created_at.get("minute", 0)
                second = created_at.get("second", 0)
                record["createdAt"] = (
                    f"{year}-{int(month):02d}-{int(day):02d}T{int(hour):02d}:{int(minute):02d}:{int(second):02d}"
                )
            elif isinstance(created_at, (int, float)) and created_at > 0:
                # epoch 毫秒 → ISO 字符串
                from datetime import datetime, timezone

                dt = datetime.fromtimestamp(created_at / 1000, tz=timezone.utc)
                record["createdAt"] = dt.strftime("%Y-%m-%dT%H:%M:%S")
            elif isinstance(created_at, str) and created_at:
                # 处理字符串格式：确保符合 ISO 8601 格式
                import re

                # 尝试匹配各种日期格式
                # 格式1: yyyy-MM-ddTHH:mm:ss 或 yyyy-MM-ddTHH:mm
                match = re.match(
                    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?", created_at
                )
                if match:
                    # 已经是 ISO 格式，保持不变
                    continue
                # 格式2: yyyy-MM-dd HH:mm:ss 或 yyyy-MM-dd HH:mm
                match = re.match(
                    r"^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})(?::(\d{2}))?", created_at
                )
                if match:
                    # 转换为 ISO 格式
                    year, month, day, hour, minute, second = match.groups()
                    second = second or "00"
                    record["createdAt"] = (
                        f"{year}-{month}-{day}T{hour}:{minute}:{second}"
                    )
                # 格式3: yyyy-MM-dd（只有日期）
                match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", created_at)
                if match:
                    year, month, day = match.groups()
                    record["createdAt"] = f"{year}-{month}-{day}T00:00:00"
            # 如果 created_at 是 None 或空字符串，保持为 None，让 QML 显示 "-"
