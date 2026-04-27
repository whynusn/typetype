from ...models.dto.ziti import ZitiScheme, ZitiSchemeData
from ...ports.ziti_repository import ZitiRepository


class ZitiGateway:
    """字提示方案应用网关。"""

    def __init__(self, repository: ZitiRepository) -> None:
        self._repository = repository

    def list_schemes(self) -> list[ZitiScheme]:
        return self._repository.list_schemes()

    def load_scheme(self, name: str) -> ZitiSchemeData:
        return self._repository.load_scheme(name)
