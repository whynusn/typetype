from typing import Protocol

from ..models.dto.ziti import ZitiScheme, ZitiSchemeData


class ZitiRepository(Protocol):
    """字提示方案仓储端口。"""

    def list_schemes(self) -> list[ZitiScheme]: ...

    def load_scheme(self, name: str) -> ZitiSchemeData: ...
