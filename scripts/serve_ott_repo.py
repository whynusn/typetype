#!/usr/bin/env python3
"""serve_ott_repo.py - 本地 OTT Repo 测试服务器。

启动后，typetype 可以通过 http://127.0.0.1:18888/ott-repo.json 订阅本地 repo。

用法：
    uv run python scripts/serve_ott_repo.py
    uv run python scripts/serve_ott_repo.py --port 19999
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 让脚本能从项目根导入 src 包
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PUBLIC_DIR = ROOT.parent / "typetype-default-ott-repo"


def create_app():
    """创建 WSGI 应用（不依赖第三方库）。"""
    import mimetypes
    from urllib.parse import unquote

    def app(environ, start_response):
        path = unquote(environ.get("PATH_INFO", "/"))
        if path == "/":
            path = "/ott-repo.json"

        # 安全路径检查
        file_path = (PUBLIC_DIR / path.lstrip("/")).resolve()
        try:
            file_path.relative_to(PUBLIC_DIR.resolve())
        except ValueError:
            start_response("403 Forbidden", [("Content-Type", "text/plain")])
            return [b"Forbidden"]

        if not file_path.exists() or not file_path.is_file():
            start_response("404 Not Found", [("Content-Type", "text/plain")])
            return [b"Not Found"]

        content_type, _ = mimetypes.guess_type(str(file_path))
        if content_type is None:
            content_type = "application/octet-stream"

        # 文本文件用 UTF-8
        if content_type.startswith(
            ("text/", "application/json", "application/javascript")
        ):
            content_type += "; charset=utf-8"
            data = file_path.read_bytes()
        else:
            data = file_path.read_bytes()

        start_response(
            "200 OK",
            [
                ("Content-Type", content_type),
                ("Content-Length", str(len(data))),
                ("Cache-Control", "no-cache"),
                ("Access-Control-Allow-Origin", "*"),
            ],
        )
        return [data]

    return app


def main():
    parser = argparse.ArgumentParser(description="OTT Repo 本地测试服务器")
    parser.add_argument("--port", type=int, default=18888, help="端口（默认 18888）")
    parser.add_argument(
        "--host", default="127.0.0.1", help="绑定地址（默认 127.0.0.1）"
    )
    args = parser.parse_args()

    if not PUBLIC_DIR.exists():
        print(f"错误：{PUBLIC_DIR} 不存在", file=sys.stderr)
        sys.exit(1)

    from wsgiref.simple_server import make_server

    app = create_app()
    server = make_server(args.host, args.port, app)
    print(f"OTT Repo 服务器启动: http://{args.host}:{args.port}/")
    print(f"Manifest URL: http://{args.host}:{args.port}/ott-repo.json")
    print(f"本地文件目录: {PUBLIC_DIR}")
    print("按 Ctrl+C 停止")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务器已停止")


if __name__ == "__main__":
    main()
