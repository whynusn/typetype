"""基于 ApiClient 的成绩提交实现（异步队列模式）。

为什么需要这个组件：
- 成绩提交涉及网络 I/O，同步提交会阻塞 UI 线程
- 异步队列模式将提交请求放入队列，立即返回，后台线程处理实际提交
- 指数退避重试保证网络抖动时的可靠性

💡 设计决策：
- submit() 方法签名不变，内部改为异步：对调用方透明，无需修改 Adapter 层
- 入队而非直接 HTTP POST：提交操作从 O(阻塞时间) 变为 O(1)
- 通过 logging 通知结果：桌面应用场景下不需要复杂的信号机制

🎓 异步提交的接口兼容策略：
- submit() 返回 True 表示"成功入队"，而非"提交成功"
- 实际提交结果通过日志和 SQLite 持久化记录
- 如果需要精确的成功/失败通知，可以扩展为回调模式
"""

from collections.abc import Callable
from typing import Any

from ..infrastructure.api_client import ApiClient
from ..models.entity.session_stat import SessionStat
from ..utils.logger import log_warning
from ..workers.score_submit_worker import ScoreSubmitQueue


class ApiClientScoreSubmitter:
    """通过 HTTP API 提交成绩到 Spring Boot 后端（异步队列模式）。

    只有服务端存在的文本才能提交成绩，因此只需传入 text_id。

    用法（与旧接口完全兼容）：
        submitter = ApiClientScoreSubmitter(
            api_client=api_client,
            submit_url="http://localhost:8080/api/v1/scores",
            token_provider=lambda: "jwt_token",
        )
        submitter.start()  # 启动后台队列

        # 异步提交（非阻塞）
        success = submitter.submit(score_data, text_id=1)

        submitter.stop()  # 关闭时等待队列清空
    """

    def __init__(
        self,
        api_client: ApiClient,
        submit_url: str,
        token_provider: Callable[[], str] = lambda: "",
        retry_store: Any | None = None,
    ):
        self._api_client = api_client
        self._submit_url = submit_url
        self._token_provider = token_provider

        # 💡 创建异步队列，submit_fn 是实际的 HTTP 提交逻辑
        self._queue = ScoreSubmitQueue(
            submit_fn=self._do_http_submit,
            retry_store=retry_store,
        )
        self._started = False

    def start(self) -> None:
        """启动后台提交队列。应在应用初始化时调用。"""
        if not self._started:
            self._queue.start()
            self._started = True

    def stop(self, timeout: float = 5.0) -> None:
        """停止后台队列，等待剩余任务完成。应在应用退出时调用。"""
        if self._started:
            self._queue.stop(timeout=timeout)
            self._started = False

    def update_base_url(self, new_base_url: str) -> None:
        """更新 base_url 及其派生的提交 URL。"""
        new_base_url = new_base_url.rstrip("/")
        self._submit_url = f"{new_base_url}/api/v1/scores"

    def submit(
        self,
        score_data: SessionStat,
        text_id: int,
    ) -> bool:
        """异步提交成绩到服务器（非阻塞）。

        🎓 接口兼容性保证：
        - 方法签名与旧版完全一致
        - 返回值语义从"HTTP 请求成功"变为"成功入队"
        - 对 TypingAdapter 透明，无需修改调用代码

        Args:
            score_data: 会话统计数据
            text_id: 服务端文本ID（必须是已存在的文本）

        Returns:
            bool: 是否成功入队（True 不代表提交成功）
        """
        token = self._token_provider()
        if not token:
            log_warning("[ScoreSubmitter] 无法提交成绩：未登录")
            return False

        # 🎓 入队操作是 O(1)，立即返回
        # 实际 HTTP POST 在后台线程中执行
        return self._queue.enqueue(score_data, text_id)

    def _do_http_submit(self, payload: dict[str, Any]) -> bool:
        """实际的 HTTP 提交逻辑（在后台线程中执行）。

        ⚠️ 这个方法会被 ScoreSubmitQueue 的工作线程调用，
        不要在其中访问 Qt 对象或发射信号。
        """
        token = self._token_provider()
        if not token:
            log_warning("[ScoreSubmitter] HTTP 提交时 token 已失效")
            return False

        headers = {"Authorization": f"Bearer {token}"}

        data = self._api_client.request(
            "POST",
            self._submit_url,
            json=payload,
            headers=headers,
        )

        return self._parse_response(data)

    def _parse_response(
        self,
        data: dict[str, Any] | None,
    ) -> bool:
        """解析响应。"""
        if data is None:
            log_warning(
                f"[ScoreSubmitter] 提交失败: {self._api_client.last_error or '网络错误'}"
            )
            return False

        code = data.get("code")
        if code == 200:
            return True

        log_warning(f"[ScoreSubmitter] 提交失败: {data.get('message', '未知错误')}")
        return False

    @property
    def queue_stats(self) -> dict[str, int]:
        """返回队列统计信息。"""
        return self._queue.stats


class NoopScoreSubmitter:
    """空实现，用于未登录或禁用提交场景。"""

    def submit(
        self,
        score_data: SessionStat,
        text_id: int,
    ) -> bool:
        return False

    def start(self) -> None:
        pass

    def stop(self, timeout: float = 5.0) -> None:
        pass
