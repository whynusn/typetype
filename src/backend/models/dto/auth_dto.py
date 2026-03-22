from dataclasses import dataclass, field
from typing import Any


@dataclass
class AuthResult:
    """认证操作结果。"""

    success: bool
    access_token: str = ""
    refresh_token: str = ""
    user_info: dict[str, Any] = field(default_factory=dict)
    error_message: str = ""
