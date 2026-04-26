from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..models.dto.wenlai_dto import (
    WenlaiCategory,
    WenlaiDifficulty,
    WenlaiLoginResult,
    WenlaiText,
)
from ..ports.wenlai_provider import WenlaiAuthRequiredError, WenlaiServiceError

if TYPE_CHECKING:
    from ..infrastructure.api_client import ApiClient


class WenlaiProvider:
    """晴发文 HTTP API 适配。"""

    _LABEL_TO_LEVEL = {"淼": 1, "水": 2, "易": 3, "普": 4, "难": 5, "虐": 6}

    def __init__(
        self,
        api_client: "ApiClient",
        base_url: str,
        token_provider: Callable[[], str],
    ) -> None:
        self._api_client = api_client
        self._base_url = base_url.rstrip("/")
        self._token_provider = token_provider

    def update_base_url(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{self._base_url}{path}"

    def _auth_headers(self) -> dict[str, str]:
        token = self._token_provider()
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        url = self._url(path)
        return self._api_client.request(
            method,
            url,
            params=params,
            json=json,
            headers=headers,
        )

    def _data(self, response: dict[str, Any] | None) -> Any:
        if response is None:
            if self._api_client.last_error:
                raise self._api_client.last_error
            raise WenlaiServiceError("晴发文服务请求失败")
        code = response.get("code")
        if code == 401:
            raise WenlaiAuthRequiredError("请先在设置页登录晴发文")
        if code is not None and code != 200:
            message = (
                response.get("msg") or response.get("message") or "晴发文服务请求失败"
            )
            raise WenlaiServiceError(str(message))
        return response.get("data", response)

    @staticmethod
    def _safe_int(data: dict[str, Any], *keys: str) -> int:
        for key in keys:
            value = data.get(key)
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0
        return 0

    @staticmethod
    def _safe_float(data: dict[str, Any], key: str) -> float:
        value = data.get(key)
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _safe_str(data: dict[str, Any], key: str) -> str:
        value = data.get(key)
        return value if isinstance(value, str) else ""

    def login(self, username: str, password: str) -> WenlaiLoginResult:
        response = self._request(
            "POST",
            "/api/auth/login",
            json={"username": username, "password": password},
        )
        data = self._data(response)
        if not isinstance(data, dict):
            raise WenlaiServiceError("晴发文登录响应格式错误")
        token = self._safe_str(data, "token") or self._safe_str(data, "accessToken")
        if not token:
            raise WenlaiServiceError("晴发文登录响应缺少 token")
        parsed_username = self._safe_str(data, "username") or username
        display_name = self._safe_str(data, "displayName")
        return WenlaiLoginResult(
            token=token,
            user_id=self._safe_int(data, "userId", "id"),
            username=parsed_username,
            display_name=display_name,
        )

    def fetch_random_text(
        self,
        *,
        difficulty_level: int,
        length: int,
        strict_length: bool,
        category: str,
    ) -> WenlaiText:
        params: dict[str, Any] = {}
        if difficulty_level > 0:
            params["difficultyLevel"] = difficulty_level
        if length > 0:
            params["length"] = length
            params["strictLength"] = str(strict_length).lower()
        if category:
            params["category"] = category

        response = self._request(
            "GET",
            "/api/texts/random",
            params=params,
            headers=self._auth_headers(),
        )
        return self._parse_text(self._data(response))

    def fetch_adjacent_text(
        self,
        *,
        book_id: int,
        sort_num: int,
        direction: str,
        category: str,
        end_sort_num: int,
        end_chars: str,
        start_chars: str,
        length: int,
        strict_length: bool,
    ) -> WenlaiText:
        params: dict[str, Any] = {
            "bookId": book_id,
            "sortNum": sort_num,
            "direction": direction,
            "category": category or "wangwen",
        }
        if end_sort_num > 0:
            params["endSortNum"] = end_sort_num
        if end_chars:
            params["endChars"] = end_chars
        if start_chars:
            params["startChars"] = start_chars
        if length > 0:
            params["length"] = length
            params["strictLength"] = str(strict_length).lower()

        response = self._request(
            "GET",
            "/api/texts/adjacent",
            params=params,
            headers=self._auth_headers(),
        )
        return self._parse_text(self._data(response))

    def get_difficulties(self) -> list[WenlaiDifficulty]:
        response = self._request(
            "GET",
            "/api/segments/stats",
            headers=self._auth_headers(),
        )
        data = self._data(response)
        if isinstance(data, list):
            return self._parse_difficulty_list(data)
        if not isinstance(data, dict):
            return []

        level_stats = data.get("levelStats")
        if isinstance(level_stats, dict):
            result = [
                WenlaiDifficulty(
                    id=self._LABEL_TO_LEVEL.get(label, 0),
                    name=label,
                    count=int(count or 0),
                )
                for label, count in level_stats.items()
                if self._LABEL_TO_LEVEL.get(label, 0) > 0
            ]
            return sorted(result, key=lambda item: item.id)

        return []

    def _parse_difficulty_list(self, items: list[Any]) -> list[WenlaiDifficulty]:
        result = []
        for item in items:
            if not isinstance(item, dict):
                continue
            result.append(
                WenlaiDifficulty(
                    id=self._safe_int(item, "id"),
                    name=self._safe_str(item, "name"),
                    count=self._safe_int(item, "count"),
                )
            )
        return sorted(result, key=lambda item: item.id)

    def get_categories(self) -> list[WenlaiCategory]:
        response = self._request(
            "GET",
            "/api/categories",
            headers=self._auth_headers(),
        )
        data = self._data(response)
        if not isinstance(data, list):
            return []
        result = []
        for item in data:
            if not isinstance(item, dict):
                continue
            if item.get("isActive", True) is False:
                continue
            code = self._safe_str(item, "code")
            name = self._safe_str(item, "name")
            if code:
                result.append(WenlaiCategory(code=code, name=name or code))
        return result

    def _parse_text(self, data: Any) -> WenlaiText:
        if not isinstance(data, dict):
            raise WenlaiServiceError("晴发文返回的数据格式错误")

        title = self._safe_str(data, "bookName") or self._safe_str(data, "name")
        if not title:
            title = "未知标题"
        title = title.split("#", 1)[0]

        content = self._safe_str(data, "content")
        if not content:
            raise WenlaiServiceError("晴发文返回的文章内容为空")

        return WenlaiText(
            title=title,
            content=content,
            mark=self._safe_str(data, "mark"),
            book_id=self._safe_int(data, "bookId", "book_id"),
            sort_num=self._safe_int(data, "sortNum", "sort_num"),
            end_sort_num=self._safe_int(data, "endSortNum"),
            end_chars=self._safe_str(data, "endChars"),
            start_chars=self._safe_str(data, "startChars"),
            category=self._safe_str(data, "category"),
            difficulty_level=self._safe_int(data, "difficultyLevel"),
            difficulty_label=self._safe_str(data, "difficultyLabel"),
            difficulty_score=self._safe_float(data, "difficultyScore"),
        )
