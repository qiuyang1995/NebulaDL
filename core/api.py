"""
NebulaDL - JavaScript Bridge API Module
"""

import os
import json
import uuid
import threading
import queue
from typing import Optional, Any
from urllib.parse import urlparse

import webview
from .downloader import VideoAnalyzer, DownloadTask


class JsApi:
    """暴露给 JavaScript 的 API 接口"""

    SETTINGS_FILE = os.path.join(os.path.expanduser('~'), '.nebuladl_settings.json')
    COOKIE_MAP_FILE = os.path.join(os.path.expanduser('~'), '.nebuladl_cookies.json')
    
    def __init__(self, window: Any = None):
        self._window = window
        self._js_lock = threading.Lock()

        self._settings: dict[str, Any] = self._load_settings()

        self._download_dir = self._settings.get(
            'download_path',
            os.path.join(os.path.expanduser('~'), 'Downloads'),
        )
        self._current_video_info = None

        self._tasks: dict[str, DownloadTask] = {}
        self._task_cancel: dict[str, threading.Event] = {}
        self._task_meta: dict[str, dict[str, Any]] = {}
        self._task_state: dict[str, str] = {}

        # Track whether we've downloaded the thumbnail for a given URL.
        # Used to avoid repeatedly downloading the same cover when user downloads
        # multiple resolutions of the same video.
        self._thumb_done: set[str] = set()

        self._pending: queue.Queue[str] = queue.Queue()
        self._cond = threading.Condition()
        self._active: set[str] = set()
        self._scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._scheduler_thread.start()

        self._cookie_map: dict[str, str] = self._load_cookie_map()

    def _load_cookie_map(self) -> dict[str, str]:
        try:
            if os.path.exists(self.COOKIE_MAP_FILE):
                with open(self.COOKIE_MAP_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        out: dict[str, str] = {}
                        for k, v in data.items():
                            if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip():
                                out[k.strip().lower()] = v
                        return out
        except Exception:
            pass
        return {}

    def _save_cookie_map(self) -> None:
        try:
            with open(self.COOKIE_MAP_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._cookie_map, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _extract_domain(self, url_or_domain: str) -> str:
        raw = (url_or_domain or '').strip()
        if not raw:
            return ''

        # If user passed a bare domain, urlparse won't populate hostname.
        if '://' not in raw:
            raw_url = 'https://' + raw
        else:
            raw_url = raw

        try:
            u = urlparse(raw_url)
            host = (u.hostname or '').strip().lower()
        except Exception:
            host = ''

        # Fallback: treat input as domain.
        if not host:
            host = raw.strip().lower()

        host = host.strip('.')
        if host.startswith('www.'):
            host = host[4:]
        return host

    def _cookiefile_for_url(self, url: str) -> Optional[str]:
        host = self._extract_domain(url)
        if not host:
            return None

        # Try exact host first, then fall back by stripping leading subdomains.
        cur = host
        while cur:
            path = self._cookie_map.get(cur)
            if path and os.path.isfile(path):
                return path
            if '.' not in cur:
                break
            cur = cur.split('.', 1)[1]
        return None

    def get_cookie_mappings(self) -> str:
        items = [{'domain': k, 'path': v} for k, v in sorted(self._cookie_map.items())]
        return json.dumps({'success': True, 'items': items}, ensure_ascii=False)

    def choose_cookie_file(self) -> str:
        if not self._window:
            return json.dumps({'success': False, 'error': '窗口未就绪'}, ensure_ascii=False)

        try:
            result = self._window.create_file_dialog(
                webview.FileDialog.OPEN,
                allow_multiple=False,
                # pywebview expects a sequence of strings:
                # ('Description (*.ext[;*.ext])', ...)
                file_types=(
                    'Cookies (*.txt)',
                    'All files (*.*)',
                ),
            )
            if result and len(result) > 0:
                return json.dumps({'success': True, 'path': result[0]}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False)

        return json.dumps({'success': False, 'error': '未选择文件'}, ensure_ascii=False)

    def set_cookie_mapping(self, domain_or_url: str, cookie_path: str) -> str:
        domain = self._extract_domain(domain_or_url)
        cookie_path = (cookie_path or '').strip()
        if not domain:
            return json.dumps({'success': False, 'error': '请输入有效的域名或链接'}, ensure_ascii=False)
        if not cookie_path or not os.path.isfile(cookie_path):
            return json.dumps({'success': False, 'error': 'Cookie 文件不存在'}, ensure_ascii=False)

        self._cookie_map[domain] = cookie_path
        self._save_cookie_map()
        return json.dumps({'success': True, 'domain': domain, 'path': cookie_path}, ensure_ascii=False)

    def remove_cookie_mapping(self, domain_or_url: str) -> str:
        domain = self._extract_domain(domain_or_url)
        if not domain:
            return json.dumps({'success': False, 'error': '请输入有效的域名或链接'}, ensure_ascii=False)
        self._cookie_map.pop(domain, None)
        self._save_cookie_map()
        return json.dumps({'success': True, 'domain': domain}, ensure_ascii=False)
    
    def set_window(self, window: Any):
        """设置 pywebview 窗口引用"""
        self._window = window

    def _load_settings(self) -> dict[str, Any]:
        """从用户目录加载设置"""
        try:
            if os.path.exists(self.SETTINGS_FILE):
                with open(self.SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
        except Exception:
            pass
        return {}

    def _save_settings(self) -> None:
        """保存设置到用户目录"""
        try:
            with open(self.SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._settings, f, ensure_ascii=False, indent=2)
        except Exception:
            # 设置保存失败不应影响主流程
            pass

    def _effective_threads(self) -> int:
        """获取实际并发数（1-16）"""
        try:
            v = int(self._settings.get('threads') or 1)
        except Exception:
            v = 1
        return max(1, min(16, v))

    def _emit_js(self, js: str) -> None:
        """线程安全调用 JS。不要在持有 _cond 时调用。"""
        if not self._window:
            return
        try:
            with self._js_lock:
                self._window.evaluate_js(js)
        except Exception:
            pass

    def _scheduler_loop(self) -> None:
        while True:
            task_id = self._pending.get()
            cancel_event = self._task_cancel.get(task_id)
            if cancel_event and cancel_event.is_set():
                # 任务还未开始即被取消
                tid_json = json.dumps(task_id, ensure_ascii=False)
                msg_json = json.dumps('已取消', ensure_ascii=False)
                self._emit_js(f"onDownloadError({tid_json}, {msg_json})")
                self._on_task_done(task_id)
                continue

            # If user paused the task before it started, skip starting it.
            if self._task_state.get(task_id) == 'paused':
                tid_json = json.dumps(task_id, ensure_ascii=False)
                msg_json = json.dumps('暂停', ensure_ascii=False)
                self._emit_js(f"updateProgress({tid_json}, -1, {msg_json})")
                continue

            with self._cond:
                while len(self._active) >= self._effective_threads():
                    self._cond.wait(timeout=0.5)
                self._active.add(task_id)

            # 启动任务线程
            task = self._tasks.get(task_id)
            if task is None:
                with self._cond:
                    self._active.discard(task_id)
                    self._cond.notify_all()
                continue

            # Re-check pause after waiting for slot.
            if self._task_state.get(task_id) == 'paused':
                with self._cond:
                    self._active.discard(task_id)
                    self._cond.notify_all()
                tid_json = json.dumps(task_id, ensure_ascii=False)
                msg_json = json.dumps('暂停', ensure_ascii=False)
                self._emit_js(f"updateProgress({tid_json}, -1, {msg_json})")
                continue

            tid_json = json.dumps(task_id, ensure_ascii=False)
            msg_json = json.dumps('正在启动...', ensure_ascii=False)
            self._emit_js(f"updateProgress({tid_json}, -1, {msg_json})")
            self._task_state[task_id] = 'downloading'
            task.start()
    
    def analyze_video(self, url: str) -> str:
        """
        解析视频信息
        
        Args:
            url: 视频链接
            
        Returns:
            JSON 字符串包含视频信息
        """
        if not url or not url.strip():
            return json.dumps({
                'success': False,
                'error': '请输入有效的链接'
            })
        
        url = url.strip()
        proxy = self._settings.get('proxy')
        cookiefile = self._cookiefile_for_url(url)
        result = VideoAnalyzer.analyze(url, proxy=proxy, cookiefile=cookiefile)
        
        if result['success']:
            self._current_video_info = result['data']
        
        return json.dumps(result, ensure_ascii=False)
    
    def start_download(self, url: str, format_id: str) -> str:
        """
        开始下载视频
        
        Args:
            url: 视频链接
            format_id: 格式标识 (1080p, 4k, audio 等)
            
        Returns:
            JSON 字符串表示操作结果
        """
        url = (url or '').strip()
        if not url:
            return json.dumps({'success': False, 'error': '请输入有效的链接'})

        cookiefile = self._cookiefile_for_url(url)

        write_thumbnail = url not in self._thumb_done
        if write_thumbnail:
            # Mark immediately to prevent duplicate thumbnail downloads when
            # multiple resolutions are queued quickly.
            self._thumb_done.add(url)

        task_id = uuid.uuid4().hex
        proxy = self._settings.get('proxy')
        create_folder = bool(self._settings.get('create_folder'))

        # Try to keep total parallel fragment connections around 8.
        # Can override via env: NEBULADL_FRAGMENT_THREADS
        try:
            env_v = int(os.environ.get('NEBULADL_FRAGMENT_THREADS') or 0)
        except Exception:
            env_v = 0

        if env_v > 0:
            fragment_downloads = max(1, min(16, env_v))
        else:
            max_tasks = self._effective_threads()
            fragment_downloads = max(1, min(16, 8 // max(1, max_tasks)))

        cancel_event = threading.Event()
        self._task_cancel[task_id] = cancel_event
        self._task_meta[task_id] = {
            'url': url,
            'format_id': format_id,
            'fragment_downloads': fragment_downloads,
            'write_thumbnail': write_thumbnail,
            'cookiefile': cookiefile,
        }

        self._task_state[task_id] = 'queued'

        def on_progress(tid: str, percent: int, status: str) -> None:
            tid_json = json.dumps(tid, ensure_ascii=False)
            status_json = json.dumps(status, ensure_ascii=False)
            self._emit_js(f"updateProgress({tid_json}, {int(percent)}, {status_json})")

        def on_complete(tid: str) -> None:
            tid_json = json.dumps(tid, ensure_ascii=False)
            self._emit_js(f"onDownloadComplete({tid_json})")
            self._task_state[tid] = 'completed'
            self._on_task_done(tid)

        def on_error(tid: str, error: str) -> None:
            err = str(error or '').strip()

            # Pause is a controlled stop: keep metadata for resume.
            if err == '暂停':
                self._task_state[tid] = 'paused'
                tid_json = json.dumps(tid, ensure_ascii=False)
                msg_json = json.dumps('暂停', ensure_ascii=False)
                self._emit_js(f"updateProgress({tid_json}, -1, {msg_json})")

                if write_thumbnail:
                    # Allow future tasks/resume to re-download cover if needed.
                    self._thumb_done.discard(url)

                self._on_task_done(tid, keep_meta=True)
                return

            if write_thumbnail:
                # If the first task fails/cancels, allow a later retry to
                # download the thumbnail.
                self._thumb_done.discard(url)

            self._task_state[tid] = 'error'
            tid_json = json.dumps(tid, ensure_ascii=False)
            error_json = json.dumps(error, ensure_ascii=False)
            self._emit_js(f"onDownloadError({tid_json}, {error_json})")
            self._on_task_done(tid, keep_meta=True)

        task = DownloadTask(
            task_id=task_id,
            url=url,
            format_id=format_id,
            output_dir=self._download_dir,
            proxy=proxy,
            create_folder=create_folder,
            write_thumbnail=write_thumbnail,
            cookiefile=cookiefile,
            fragment_downloads=fragment_downloads,
            progress_callback=on_progress,
            complete_callback=on_complete,
            error_callback=on_error,
        )
        self._tasks[task_id] = task
        self._pending.put(task_id)

        return json.dumps({'success': True, 'task_id': task_id, 'message': '下载已加入队列'})

    def retry_download(self, task_id: str) -> str:
        """重试失败的下载任务（复用同一个 task_id）。"""
        tid = (task_id or '').strip()
        meta = self._task_meta.get(tid)
        if not tid or not meta:
            return json.dumps({'success': False, 'error': '任务不存在'}, ensure_ascii=False)

        if self._task_state.get(tid) != 'error':
            return json.dumps({'success': False, 'error': '任务未处于失败状态'}, ensure_ascii=False)

        cancel_event = self._task_cancel.get(tid)
        if cancel_event:
            try:
                cancel_event.clear()
            except Exception:
                pass
        else:
            self._task_cancel[tid] = threading.Event()

        url = str(meta.get('url') or '').strip()
        format_id = str(meta.get('format_id') or '').strip()
        fragment_downloads = int(meta.get('fragment_downloads') or 1)
        write_thumbnail = bool(meta.get('write_thumbnail'))
        cookiefile = meta.get('cookiefile')

        proxy = self._settings.get('proxy')
        create_folder = bool(self._settings.get('create_folder'))

        def on_progress(tid2: str, percent: int, status: str) -> None:
            tid_json = json.dumps(tid2, ensure_ascii=False)
            status_json = json.dumps(status, ensure_ascii=False)
            self._emit_js(f"updateProgress({tid_json}, {int(percent)}, {status_json})")

        def on_complete(tid2: str) -> None:
            tid_json = json.dumps(tid2, ensure_ascii=False)
            self._emit_js(f"onDownloadComplete({tid_json})")
            self._task_state[tid2] = 'completed'
            self._on_task_done(tid2)

        def on_error(tid2: str, error: str) -> None:
            err = str(error or '').strip()
            if err == '暂停':
                self._task_state[tid2] = 'paused'
                tid_json = json.dumps(tid2, ensure_ascii=False)
                msg_json = json.dumps('暂停', ensure_ascii=False)
                self._emit_js(f"updateProgress({tid_json}, -1, {msg_json})")
                if write_thumbnail:
                    self._thumb_done.discard(url)
                self._on_task_done(tid2, keep_meta=True)
                return

            if write_thumbnail:
                self._thumb_done.discard(url)
            self._task_state[tid2] = 'error'
            tid_json = json.dumps(tid2, ensure_ascii=False)
            error_json = json.dumps(error, ensure_ascii=False)
            self._emit_js(f"onDownloadError({tid_json}, {error_json})")
            self._on_task_done(tid2, keep_meta=True)

        task = DownloadTask(
            task_id=tid,
            url=url,
            format_id=format_id,
            output_dir=self._download_dir,
            proxy=proxy,
            create_folder=create_folder,
            write_thumbnail=write_thumbnail,
            cookiefile=cookiefile,
            fragment_downloads=fragment_downloads,
            progress_callback=on_progress,
            complete_callback=on_complete,
            error_callback=on_error,
        )
        self._tasks[tid] = task
        self._task_state[tid] = 'queued'
        self._pending.put(tid)

        return json.dumps({'success': True, 'task_id': tid, 'message': '已加入队列'}, ensure_ascii=False)

    def _on_task_done(self, task_id: str, keep_meta: bool = False) -> None:
        # 清理任务
        self._tasks.pop(task_id, None)
        if not keep_meta:
            self._task_cancel.pop(task_id, None)
            self._task_meta.pop(task_id, None)
            self._task_state.pop(task_id, None)

        with self._cond:
            self._active.discard(task_id)
            self._cond.notify_all()

    def start_batch_download(self, urls: Any, format_id: str) -> str:
        """批量下载：urls 可为 list 或换行分隔字符串"""
        if isinstance(urls, str):
            items = [u.strip() for u in urls.splitlines()]
        elif isinstance(urls, list):
            items = [str(u).strip() for u in urls]
        else:
            items = []

        items = [u for u in items if u]
        if not items:
            return json.dumps({'success': False, 'error': '请输入至少一个有效链接'})

        tasks = []
        for u in items:
            raw = json.loads(self.start_download(u, format_id))
            if raw.get('success'):
                tasks.append({'task_id': raw.get('task_id'), 'url': u})

        return json.dumps({'success': True, 'tasks': tasks}, ensure_ascii=False)
    
    def cancel_download(self, task_id: str) -> str:
        """取消指定下载任务"""
        task = self._tasks.get(task_id)
        if not task:
            # 可能仍在队列中
            cancel_event = self._task_cancel.get(task_id)
            if cancel_event:
                cancel_event.set()
                # If task was paused (not in pending anymore), clean immediately.
                if self._task_state.get(task_id) == 'paused':
                    self._task_state[task_id] = 'cancelled'
                    self._on_task_done(task_id)
                return json.dumps({'success': True, 'message': '已取消'})
            return json.dumps({'success': False, 'error': '任务不存在'})

        cancel_event = self._task_cancel.get(task_id)
        if cancel_event:
            cancel_event.set()
        try:
            task.stop('cancel')
        except Exception:
            task.stop()
        self._task_state[task_id] = 'cancelled'
        return json.dumps({'success': True, 'message': '已取消'})

    def pause_download(self, task_id: str) -> str:
        """暂停指定下载任务（可继续）。"""
        tid = (task_id or '').strip()
        if not tid:
            return json.dumps({'success': False, 'error': '任务不存在'}, ensure_ascii=False)

        if tid not in self._task_meta:
            return json.dumps({'success': False, 'error': '任务不存在'}, ensure_ascii=False)

        self._task_state[tid] = 'paused'

        task = self._tasks.get(tid)
        if task:
            try:
                task.stop('pause')
            except Exception:
                pass

        tid_json = json.dumps(tid, ensure_ascii=False)
        msg_json = json.dumps('暂停', ensure_ascii=False)
        self._emit_js(f"updateProgress({tid_json}, -1, {msg_json})")
        return json.dumps({'success': True, 'message': '暂停'}, ensure_ascii=False)

    def resume_download(self, task_id: str) -> str:
        """继续已暂停的下载任务。"""
        tid = (task_id or '').strip()
        meta = self._task_meta.get(tid)
        if not tid or not meta:
            return json.dumps({'success': False, 'error': '任务不存在'}, ensure_ascii=False)

        # Only resume paused tasks.
        if self._task_state.get(tid) != 'paused':
            return json.dumps({'success': False, 'error': '任务未处于暂停状态'}, ensure_ascii=False)

        cancel_event = self._task_cancel.get(tid)
        if cancel_event:
            try:
                cancel_event.clear()
            except Exception:
                pass
        else:
            self._task_cancel[tid] = threading.Event()

        # Recreate DownloadTask thread for the same task_id.
        url = str(meta.get('url') or '').strip()
        format_id = str(meta.get('format_id') or '').strip()
        fragment_downloads = int(meta.get('fragment_downloads') or 1)
        write_thumbnail = bool(meta.get('write_thumbnail'))
        cookiefile = meta.get('cookiefile')

        proxy = self._settings.get('proxy')
        create_folder = bool(self._settings.get('create_folder'))

        def on_progress(tid2: str, percent: int, status: str) -> None:
            tid_json = json.dumps(tid2, ensure_ascii=False)
            status_json = json.dumps(status, ensure_ascii=False)
            self._emit_js(f"updateProgress({tid_json}, {int(percent)}, {status_json})")

        def on_complete(tid2: str) -> None:
            tid_json = json.dumps(tid2, ensure_ascii=False)
            self._emit_js(f"onDownloadComplete({tid_json})")
            self._task_state[tid2] = 'completed'
            self._on_task_done(tid2)

        def on_error(tid2: str, error: str) -> None:
            err = str(error or '').strip()
            if err == '暂停':
                self._task_state[tid2] = 'paused'
                tid_json = json.dumps(tid2, ensure_ascii=False)
                msg_json = json.dumps('暂停', ensure_ascii=False)
                self._emit_js(f"updateProgress({tid_json}, -1, {msg_json})")
                if write_thumbnail:
                    self._thumb_done.discard(url)
                self._on_task_done(tid2, keep_meta=True)
                return

            if write_thumbnail:
                self._thumb_done.discard(url)
            self._task_state[tid2] = 'error'
            tid_json = json.dumps(tid2, ensure_ascii=False)
            error_json = json.dumps(error, ensure_ascii=False)
            self._emit_js(f"onDownloadError({tid_json}, {error_json})")
            self._on_task_done(tid2)

        task = DownloadTask(
            task_id=tid,
            url=url,
            format_id=format_id,
            output_dir=self._download_dir,
            proxy=proxy,
            create_folder=create_folder,
            write_thumbnail=write_thumbnail,
            cookiefile=cookiefile,
            fragment_downloads=fragment_downloads,
            progress_callback=on_progress,
            complete_callback=on_complete,
            error_callback=on_error,
        )
        self._tasks[tid] = task
        self._task_state[tid] = 'queued'
        self._pending.put(tid)

        tid_json = json.dumps(tid, ensure_ascii=False)
        msg_json = json.dumps('等待中...', ensure_ascii=False)
        self._emit_js(f"updateProgress({tid_json}, -1, {msg_json})")
        return json.dumps({'success': True, 'task_id': tid, 'message': '已加入队列'}, ensure_ascii=False)
    
    def set_download_dir(self, path: str) -> str:
        """设置下载目录"""
        if os.path.isdir(path):
            self._download_dir = path
            return json.dumps({
                'success': True,
                'path': path
            })
        return json.dumps({
            'success': False,
            'error': '无效的目录路径'
        })
    
    def get_download_dir(self) -> str:
        """获取当前下载目录"""
        return json.dumps({
            'path': self._download_dir
        })
    
    def select_download_dir(self) -> str:
        """打开文件夹选择对话框"""
        if self._window:
            result = self._window.create_file_dialog(
                webview.FileDialog.FOLDER,
                directory=self._download_dir
            )
            if result and len(result) > 0:
                self._download_dir = result[0]
                return json.dumps({
                    'success': True,
                    'path': result[0]
                })
        return json.dumps({
            'success': False,
            'error': '未选择目录'
        })

    # --- Settings API used by templates/index.html ---
    def get_settings(self) -> str:
        data = dict(self._settings)
        data['download_path'] = self._download_dir
        data['threads'] = self._effective_threads()
        data['create_folder'] = bool(self._settings.get('create_folder'))
        return json.dumps(data, ensure_ascii=False)

    def save_settings(self, data: Any) -> str:
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                data = {}
        if not isinstance(data, dict):
            return json.dumps({'success': False, 'error': '无效设置数据'})

        download_path = data.get('download_path')
        if isinstance(download_path, str) and download_path and os.path.isdir(download_path):
            self._download_dir = download_path
            self._settings['download_path'] = download_path

        proxy = data.get('proxy')
        if isinstance(proxy, str):
            self._settings['proxy'] = proxy.strip()

        threads = data.get('threads')
        try:
            if threads is not None:
                self._settings['threads'] = int(threads)
        except Exception:
            pass

        create_folder = data.get('create_folder')
        if isinstance(create_folder, bool):
            self._settings['create_folder'] = create_folder
        elif create_folder is not None:
            # 兼容前端传 0/1 或 "true"/"false"
            self._settings['create_folder'] = str(create_folder).strip().lower() in ('1', 'true', 'yes', 'on')

        self._save_settings()

        with self._cond:
            self._cond.notify_all()

        return json.dumps({'success': True})

    def choose_directory(self) -> str:
        """打开文件夹选择对话框，返回路径字符串（供前端直接赋值）"""
        if not self._window:
            return ''
        try:
            result = self._window.create_file_dialog(
                webview.FileDialog.FOLDER,
                directory=self._download_dir,
            )
            if result and len(result) > 0:
                return result[0]
        except Exception:
            pass
        return ''
