from dataclasses import dataclass, field


@dataclass
class RuntimeConfig:
    """运行时配置。"""

    text_sources: dict[str, dict[str, str]] = field(
        default_factory=lambda: {
            "jisubei": {
                "label": "极速杯",
                "type": "network",
                "url": "https://www.jsxiaoshi.com/index.php/Api/Text/getContent",
            },
            "builtin_demo": {
                "label": "本地示例",
                "type": "local",
                "local_path": "qrc:/resources/texts/builtin_demo.txt",
            },
            "fst_500": {
                "label": "前五百",
                "type": "local",
                "local_path": "qrc:/resources/texts/前五百.txt",
            },
            "mid_500": {
                "label": "中五百",
                "type": "local",
                "local_path": "qrc:/resources/texts/中五百.txt",
            },
            "lst_500": {
                "label": "后五百",
                "type": "local",
                "local_path": "qrc:/resources/texts/后五百.txt",
            },
            "essential_single_char": {
                "label": "打词必备单字",
                "type": "local",
                "local_path": "qrc:/resources/texts/打词必备单字.txt",
            },
        }
    )
    default_text_source_key: str = "jisubei"
    api_timeout: float = 20.0

    def get_text_source(self, source_key: str | None = None) -> dict[str, str] | None:
        """按来源 key 获取来源配置。"""
        key = source_key or self.default_text_source_key
        return self.text_sources.get(key)

    def get_text_source_type(self, source_key: str | None = None) -> str | None:
        """按来源 key 获取来源类型。"""
        source = self.get_text_source(source_key)
        if source is None:
            return None
        return source.get("type")

    def get_text_source_url(self, source_key: str | None = None) -> str | None:
        """按来源 key 获取网络载文 URL。"""
        source = self.get_text_source(source_key)
        if source is None:
            return None
        return source.get("url")

    def get_local_path(self, source_key: str | None = None) -> str | None:
        """按来源 key 获取本地文章路径。"""
        source = self.get_text_source(source_key)
        if source is None:
            return None
        return source.get("local_path")

    def get_text_source_options(self) -> list[dict[str, str]]:
        """获取可供 UI 选择的载文来源列表。"""
        options: list[dict[str, str]] = []
        for key, source in self.text_sources.items():
            options.append(
                {
                    "key": key,
                    "label": source.get("label", key),
                }
            )
        return options
