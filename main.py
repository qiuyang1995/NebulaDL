"""
NebulaDL - YouTube Video Downloader
Application Entry Point
"""

import os
import sys
import ctypes
from typing import Any
import webview

# 确保可以导入 core 模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.api import JsApi


def get_html_path() -> str:
    """获取 HTML 文件路径"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(base_dir, 'templates', 'index.html')
    return html_path


def get_icon_path() -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, 'assets', 'icon.png')


def get_splash_html() -> str:
    # Keep it self-contained (no external assets) for fastest paint.
    return """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Loading</title>
  <style>
    :root { --bg: #0f172a; --fg: #e2e8f0; --muted: #94a3b8; }
    html, body { height: 100%; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--fg);
      font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .wrap { display: flex; align-items: center; gap: 14px; }
    .spinner {
      width: 22px;
      height: 22px;
      border-radius: 999px;
      border: 3px solid rgba(226,232,240,.25);
      border-top-color: rgba(250,204,21,.95);
      animation: spin 0.9s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    .title { font-weight: 650; letter-spacing: .2px; }
    .sub { font-size: 12px; color: var(--muted); margin-top: 2px; }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"spinner\"></div>
    <div>
      <div class=\"title\">NebulaDL</div>
      <div class=\"sub\">Loading UI...</div>
    </div>
  </div>
</body>
</html>"""


def _maybe_hide_windows_console() -> None:
    """Hide console window when we own it.

    On Windows, running `python main.py` from Explorer creates a dedicated
    console window. When launched from an existing terminal, the console is
    shared; hiding it would hide the user's terminal, so we avoid that.
    """

    if os.name != 'nt':
        return

    try:
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32

        hwnd = kernel32.GetConsoleWindow()
        if not hwnd:
            return

        # If more than 1 process is attached, the console is shared.
        arr = (ctypes.c_uint * 1)()
        n = int(kernel32.GetConsoleProcessList(arr, 1))
        if n <= 1:
            user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:
        # Best effort only.
        return


def main():
    """应用程序入口"""
    _maybe_hide_windows_console()

    # 创建 API 实例
    api = JsApi()
    
    # 获取 HTML 路径
    html_path = get_html_path()
    
    if not os.path.exists(html_path):
        print(f"错误: 找不到 HTML 文件: {html_path}")
        sys.exit(1)
    
    icon_path = get_icon_path()
    if not os.path.exists(icon_path):
        icon_path = ''

    # Splash window: shown immediately to avoid black screen.
    splash: Any = webview.create_window(
        title='NebulaDL',
        html=get_splash_html(),
        width=420,
        height=320,
        resizable=False,
        frameless=True,
        easy_drag=True,
        on_top=True,
        background_color='#0f172a',
        text_select=False,
    )

    # Main window: start hidden until content is loaded.
    main_window: Any = webview.create_window(
        title='NebulaDL',
        url=html_path,
        width=1200,
        height=800,
        min_size=(900, 600),
        background_color='#0f172a',  # Slate 900，防止启动白屏
        js_api=api,
        # Allow users to select/copy text (e.g., error dialogs).
        text_select=True,
        hidden=True,
    )

    # 设置窗口引用到 API
    api.set_window(main_window)

    def _on_main_loaded():
        try:
            main_window.show()
        except Exception:
            pass
        try:
            splash.destroy()
        except Exception:
            pass

    try:
        main_window.events.loaded += _on_main_loaded
    except Exception:
        # If events API is unavailable, fall back to showing immediately.
        try:
            main_window.show()
        except Exception:
            pass
    
    # 启动应用
    start_kwargs: dict[str, Any] = {
        'debug': bool(os.environ.get('NEBULADL_DEBUG')),
        'http_server': True,
    }
    if icon_path:
        # On GTK/QT this sets the app icon.
        start_kwargs['icon'] = icon_path

    webview.start(**start_kwargs)


if __name__ == '__main__':
    main()
