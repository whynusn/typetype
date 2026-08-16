"""上传文本适配层。"""

import os
import re

from PySide6.QtCore import QObject, Signal

from ...config.app_paths import user_texts_dir
from ...config.runtime_config import RuntimeConfig
from ...utils.logger import log_info

# 本地文本写入路径与配置文件路径
LOCAL_TEXTS_DIR = str(user_texts_dir())


class UploadTextAdapter(QObject):
    """上传文本 Qt 适配层。

    职责：
    - 本地写入文本文件并通过 RuntimeConfig 更新 text_sources 配置
    - 信号通知上传结果

    云端上传（TextUploader）已随 typetype-server 耦合移除（ADR-013）。
    """

    uploadFinished = Signal(bool, str, int)  # (success, message, server_text_id)
    configUpdated = Signal()

    def __init__(
        self,
        runtime_config: RuntimeConfig,
        texts_dir: str | None = None,
    ):
        super().__init__()
        self._runtime_config = runtime_config
        self._texts_dir = os.path.abspath(texts_dir or LOCAL_TEXTS_DIR)

    def upload(
        self, title: str, content: str, source_key: str, to_local: bool, to_cloud: bool
    ) -> None:
        """保存文本到本地并更新配置（兼容旧签名，to_cloud 不再使用）。"""
        if to_local:
            try:
                self._do_upload_local(title, content, source_key)
            except Exception as e:
                self.uploadFinished.emit(False, f"本地上传失败: {e}", 0)
                return
        self.uploadFinished.emit(True, "上传成功", 0)

    def upload_from_file(
        self,
        title: str,
        file_path: str,
        source_key: str,
        to_local: bool,
        to_cloud: bool,
    ) -> None:
        """从文件路径保存文本到本地（兼容旧签名，to_cloud 不再使用）。"""
        if to_local:
            try:
                self._do_upload_local_from_file(title, file_path, source_key)
            except Exception as e:
                self.uploadFinished.emit(False, f"本地上传失败: {e}", 0)
                return
        self.uploadFinished.emit(True, "上传成功", 0)

    def _do_upload_local(self, title: str, content: str, source_key: str) -> None:
        """写文件到本地并更新 config.json 的 text_sources 配置。"""
        os.makedirs(self._texts_dir, exist_ok=True)
        safe_source_key = self._safe_filename_part(source_key, "custom")
        safe_title = self._safe_filename_part(title, "untitled")
        filename = f"{safe_source_key}_{safe_title}.txt"
        file_path = os.path.join(self._texts_dir, filename)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        config_key = f"{safe_source_key}_{safe_title}"
        self._runtime_config.update_text_source(config_key, title, file_path)
        self.configUpdated.emit()
        log_info(f"[UploadTextAdapter] 本地保存成功: {file_path}")

    @staticmethod
    def _safe_filename_part(value: str, fallback: str) -> str:
        cleaned = value.strip().replace("/", "_").replace("\\", "_")
        cleaned = cleaned.replace("..", "_")
        cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", cleaned)
        cleaned = re.sub(r"_+", "_", cleaned).strip("._-")
        return cleaned or fallback

    def _do_upload_local_from_file(
        self, title: str, file_path: str, source_key: str
    ) -> None:
        """从文件路径复制到本地并更新配置。"""
        import shutil

        os.makedirs(self._texts_dir, exist_ok=True)
        safe_source_key = self._safe_filename_part(source_key, "custom")
        safe_title = self._safe_filename_part(title, "untitled")
        filename = f"{safe_source_key}_{safe_title}.txt"
        dest_path = os.path.join(self._texts_dir, filename)

        # 直接复制文件，不加载到内存
        shutil.copy2(file_path, dest_path)

        config_key = f"{safe_source_key}_{safe_title}"
        self._runtime_config.update_text_source(config_key, title, dest_path)
        self.configUpdated.emit()
        log_info(f"[UploadTextAdapter] 本地保存成功（从文件复制）: {dest_path}")
