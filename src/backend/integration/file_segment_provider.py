from __future__ import annotations

import hashlib
import json
import codecs
from bisect import bisect_right
from pathlib import Path

from ..config.app_paths import user_indexes_dir

_INDEX_INTERVAL = 10_000  # 每 10000 个字符记录一个索引点


class FileSegmentProvider:
    """基于磁盘文件的文本段提供者。

    小文件（< small_file_threshold）：首次访问时全量读入内存，后续等同于字符串切片。
    大文件（>= small_file_threshold）：构建稀疏字符索引，按需读取字符窗口。
    """

    def __init__(
        self, path: str | Path, small_file_threshold: int = 100_000
    ) -> None:
        self._path = Path(path)
        self._small_file_threshold = small_file_threshold
        self._encoding: str | None = None
        self._total_chars: int | None = None
        # 小文件：全量加载后的字符串
        self._text: str | None = None
        # 大文件：稀疏索引 [(char_offset, byte_offset), ...]
        self._index: list[tuple[int, int]] = []

    def get_total_chars(self) -> int:
        if self._total_chars is None:
            self._total_chars = self._count_chars()
        return self._total_chars

    def get_segment(self, start: int, length: int) -> str:
        if start < 0 or length <= 0:
            return ""
        self._ensure_loaded()
        if self._text is not None:
            if start >= len(self._text):
                return ""
            return self._text[start : start + length]
        return self._read_segment_from_file(start, length)

    def _ensure_loaded(self) -> None:
        if self._text is not None or self._index:
            return
        self._detect_encoding()
        total = self.get_total_chars()
        if total < self._small_file_threshold:
            self._text = self._read_all()
        else:
            self._build_index()

    def _detect_encoding(self) -> str:
        if self._encoding is not None:
            return self._encoding
        decoder = codecs.getincrementaldecoder("utf-8")()
        try:
            with self._path.open("rb") as f:
                while True:
                    chunk = f.read(64 * 1024)
                    if not chunk:
                        break
                    decoder.decode(chunk)
                decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            self._encoding = "gb18030"
        else:
            self._encoding = "utf-8"
        return self._encoding

    def _count_chars(self) -> int:
        encoding = self._detect_encoding()
        total = 0
        with self._path.open("r", encoding=encoding) as f:
            while True:
                chunk = f.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
        return total

    def _read_all(self) -> str:
        encoding = self._detect_encoding()
        return self._path.read_text(encoding=encoding)

    def _build_index(self) -> None:
        """扫描全文件，建立稀疏字符索引。"""
        encoding = self._detect_encoding()
        self._index = [(0, 0)]
        char_count = 0
        with self._path.open("rb") as f:
            decoder = codecs.getincrementaldecoder(encoding)()
            while True:
                raw = f.read(64 * 1024)
                if not raw:
                    break
                text = decoder.decode(raw)
                new_char_count = char_count + len(text)
                # 检查是否跨越了索引间隔边界
                prev_interval = char_count // _INDEX_INTERVAL
                new_interval = new_char_count // _INDEX_INTERVAL
                if new_interval > prev_interval:
                    byte_pos = f.tell() - len(raw)
                    # 为每个跨越的间隔记录索引
                    for i in range(prev_interval + 1, new_interval + 1):
                        # 估算该间隔对应的 byte offset
                        chars_at_interval = i * _INDEX_INTERVAL
                        ratio = (chars_at_interval - char_count) / max(1, len(text))
                        estimated_byte = byte_pos + int(ratio * len(raw))
                        self._index.append((chars_at_interval, estimated_byte))
                char_count = new_char_count
            decoder.decode(b"", final=True)

    def _read_segment_from_file(self, start: int, length: int) -> str:
        """通过稀疏索引从文件中读取指定字符范围。"""
        if not self._index:
            return ""

        # 二分查找最近的索引点
        idx = bisect_right(self._index, (start,)) - 1
        if idx < 0:
            idx = 0
        char_offset, byte_offset = self._index[idx]

        encoding = self._detect_encoding()
        remaining_skip = start - char_offset
        remaining_take = length
        parts: list[str] = []

        with self._path.open("rb") as f:
            f.seek(byte_offset)
            decoder = codecs.getincrementaldecoder(encoding)()
            while remaining_take > 0:
                raw = f.read(64 * 1024)
                if not raw:
                    break
                text = decoder.decode(raw)
                if remaining_skip >= len(text):
                    remaining_skip -= len(text)
                    continue
                if remaining_skip:
                    text = text[remaining_skip:]
                    remaining_skip = 0
                parts.append(text[:remaining_take])
                remaining_take -= len(parts[-1])
            decoder.decode(b"", final=True)

        return "".join(parts)

    def _get_index_hash(self) -> str:
        """生成索引文件名用的 hash。"""
        stat = self._path.stat()
        key = f"{self._path}:{stat.st_size}:{stat.st_mtime}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def _index_path(self) -> Path:
        return user_indexes_dir() / f"{self._get_index_hash()}.json"

    def save_index_cache(self) -> None:
        """将索引缓存写入磁盘。"""
        if not self._index:
            return
        index_path = self._index_path()
        index_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "path": str(self._path),
            "size": self._path.stat().st_size,
            "mtime": self._path.stat().st_mtime,
            "encoding": self._encoding,
            "total_chars": self._total_chars,
            "index": self._index,
        }
        tmp = index_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(index_path)

    def load_index_cache(self) -> bool:
        """尝试从磁盘加载索引缓存。返回是否成功。"""
        index_path = self._index_path()
        if not index_path.exists():
            return False
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        stat = self._path.stat()
        if data.get("size") != stat.st_size or data.get("mtime") != stat.st_mtime:
            return False
        self._encoding = data.get("encoding", "utf-8")
        self._total_chars = data.get("total_chars", 0)
        self._index = [tuple(pair) for pair in data.get("index", [])]
        return True
