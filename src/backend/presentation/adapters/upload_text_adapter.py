"""上传文本适配层。"""

import json
import os
import re
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal, Slot

from ...config.app_paths import user_config_path, user_texts_dir
from ...utils.logger import log_info, log_warning

if TYPE_CHECKING:
    from ...ports.text_uploader import TextUploader

# 本地文本写入路径与配置文件路径
LOCAL_TEXTS_DIR = str(user_texts_dir())
CONFIG_PATH = str(user_config_path())


class UploadTextAdapter(QObject):
    """上传文本 Qt 适配层。

    职责：
    - 本地写入文本文件并更新 config.json 的 text_sources 配置
    - 调用 TextUploader 上传到云端
    - 信号通知上传结果
    """

    uploadFinished = Signal(bool, str, int)  # (success, message, server_text_id)

    def __init__(
        self,
        text_uploader: "TextUploader",
        texts_dir: str | None = None,
        config_path: str | None = None,
    ):
        super().__init__()
        self._text_uploader = text_uploader
        self._texts_dir = os.path.abspath(texts_dir or LOCAL_TEXTS_DIR)
        self._config_path = os.path.abspath(config_path or CONFIG_PATH)

    def upload(
        self, title: str, content: str, source_key: str, to_local: bool, to_cloud: bool
    ) -> None:
        """上传文本到指定目标，支持同时上传本地和云端。"""
        results: list[str] = []
        errors: list[str] = []
        server_text_id: int = 0

        if to_local:
            try:
                self._do_upload_local(title, content, source_key)
                results.append("本地")
            except Exception as e:
                errors.append(f"本地: {e}")

        if to_cloud:
            try:
                rid = self._do_upload_cloud(title, content, source_key)
                results.append("云端")
                if rid is not None:
                    server_text_id = rid
            except Exception as e:
                errors.append(f"云端: {e}")

        if errors:
            self.uploadFinished.emit(False, "；".join(errors), server_text_id)
        else:
            self.uploadFinished.emit(
                True, f"已上传到{'/'.join(results)}", server_text_id
            )

    def _do_upload_local(self, title: str, content: str, source_key: str) -> None:
        """写文件到本地并更新 config.json 的 text_sources 配置。"""
        os.makedirs(self._texts_dir, exist_ok=True)
        safe_source_key = self._safe_filename_part(source_key, "custom")
        safe_title = self._safe_filename_part(title, "untitled")
        filename = f"{safe_source_key}_{safe_title}.txt"
        file_path = os.path.join(self._texts_dir, filename)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        self._update_config(safe_source_key, title, file_path)
        log_info(f"[UploadTextAdapter] 本地保存成功: {file_path}")

    @staticmethod
    def _safe_filename_part(value: str, fallback: str) -> str:
        cleaned = value.strip().replace("/", "_").replace("\\", "_")
        cleaned = cleaned.replace("..", "_")
        cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", cleaned)
        cleaned = re.sub(r"_+", "_", cleaned).strip("._-")
        return cleaned or fallback

    def _do_upload_cloud(self, title: str, content: str, source_key: str) -> int | None:
        """调用 TextUploader 上传到云端，返回服务端文本 ID。"""
        result_id = self._text_uploader.upload(content, title, source_key)
        if result_id is None:
            raise RuntimeError("服务器未返回有效ID")
        log_info(f"[UploadTextAdapter] 云端上传成功: id={result_id}")
        return result_id

    @Slot(str, str, str)
    def upload_to_local(self, title: str, content: str, source_key: str) -> None:
        """兼容旧接口。"""
        self.upload(title, content, source_key, True, False)

    @Slot(str, str, str)
    def upload_to_cloud(self, title: str, content: str, source_key: str) -> None:
        """兼容旧接口。"""
        self.upload(title, content, source_key, False, True)

    def _update_config(self, source_key: str, title: str, file_path: str) -> None:
        """更新 config.json 的 text_sources 配置。"""
        config_data = self._load_config_data()

        text_sources = config_data.get("text_sources", {})
        text_sources[source_key] = {
            "label": title,
            "local_path": file_path,
        }
        config_data["text_sources"] = text_sources

        with open(self._config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)

        log_info(f"[UploadTextAdapter] config.json 已更新: source_key={source_key}")

    def _load_config_data(self) -> dict:
        """加载 config.json，若不存在则返回空字典。"""
        if os.path.exists(self._config_path):
            try:
                with open(self._config_path, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                log_warning("[UploadTextAdapter] config.json 读取失败，使用空配置")
        return {}
