"""
NebulaDL - yt-dlp Download Wrapper Module
"""

import threading
import os
import uuid
import platform
import subprocess
from typing import Optional, Callable, Any, cast

import yt_dlp

try:
    from yt_dlp.utils import DownloadError as YtDlpDownloadError
except Exception:  # pragma: no cover
    YtDlpDownloadError = Exception


class VideoAnalyzer:
    """视频信息解析器"""
    
    @staticmethod
    def analyze(url: str, proxy: Optional[str] = None, cookiefile: Optional[str] = None) -> dict:
        """
        解析视频信息
        
        Args:
            url: 视频链接（任何 yt-dlp 支持的网站）
            
        Returns:
            dict: 包含视频标题、缩略图、时长、来源站点、可用格式等信息
        """
        ydl_opts: dict[str, Any] = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            # Keep individual network operations bounded.
            # Overall timeout is enforced by JsApi.analyze_video.
            'socket_timeout': 30,
        }

        if proxy:
            ydl_opts['proxy'] = proxy

        if cookiefile:
            ydl_opts['cookiefile'] = cookiefile
        
        try:
            ydl_opts_any: Any = ydl_opts
            with yt_dlp.YoutubeDL(ydl_opts_any) as ydl:
                info = ydl.extract_info(url, download=False)
                
                # 解析可用格式
                formats = []
                all_formats = list(info.get('formats') or [])
                available_heights: set[int] = set()
                has_audio = False
                
                for f in all_formats:
                    height = f.get('height')
                    if height:
                        try:
                            available_heights.add(int(height))
                        except Exception:
                            pass
                    if f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                        has_audio = True
                
                duration = int(info.get('duration') or 0)

                # 构建格式列表：展示实际识别到的分辨率（<=1080 也全部展示）
                afmt = _pick_best_audio_format(all_formats)

                def add_height_option(h: int) -> None:
                    vfmt = _pick_best_video_format(all_formats, max_height=h)

                    total_bytes = _estimate_merged_filesize_bytes(vfmt, afmt, duration)
                    size_str = _format_bytes(total_bytes) if total_bytes else '未知'

                    formats.append({
                        'id': f'{h}p',
                        'label': f'{h}P',
                        'ext': 'MP4' if h <= 1080 else 'MKV',
                        'size': size_str,
                        'is_pro': False,
                    })

                heights_sorted = sorted(available_heights, reverse=True)
                for h in heights_sorted:
                    if h < 360:
                        continue
                    add_height_option(h)

                if has_audio:
                    bytes_audio = _estimate_filesize_bytes(afmt, duration)
                    formats.append({
                        'id': 'audio',
                        'label': 'Audio Only',
                        'ext': 'FLAC',
                        'size': _format_bytes(bytes_audio) if bytes_audio else '未知',
                        'is_pro': False,
                    })
                
                # 如果没有解析到格式，添加默认选项
                if not formats:
                    formats.append({
                        'id': 'best',
                        'label': '最佳画质',
                        'ext': 'MP4',
                        'size': '未知',
                        'is_pro': False
                    })
                
                view_count = int(info.get('view_count') or 0)

                site = (
                    info.get('extractor_key')
                    or info.get('extractor')
                    or info.get('ie_key')
                    or info.get('webpage_url_domain')
                    or ''
                )
                site = str(site or '').strip()

                return {
                    'success': True,
                    'data': {
                        'title': info.get('title', '未知标题'),
                        'thumbnail': info.get('thumbnail', ''),
                        'duration': duration,
                        'duration_str': _format_duration(duration),
                        'view_count': _format_views(view_count),
                        'uploader': info.get('uploader', '未知频道'),
                        'site': site,
                        'formats': formats,
                        'url': url
                    }
                }
                 
        except YtDlpDownloadError as e:
            friendly = _friendly_yt_dlp_error('解析', str(e))
            return {
                'success': False,
                'error': friendly,
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'发生未知错误: {str(e)}'
            }


def _friendly_yt_dlp_error(action: str, raw_error: str) -> str:
    msg = (raw_error or '').strip()
    low = msg.lower()

    # yt-dlp often prefixes errors with 'ERROR: '
    if low.startswith('error:'):
        msg = msg[6:].strip()
        low = msg.lower()

    # Unsupported website / extractor.
    if 'unsupported url' in low:
        return f'{action}失败：该链接暂不支持（yt-dlp 不支持此网站/链接）。请更换为 yt-dlp 支持的网站链接。'

    # Common auth/permission-related errors (cookies often required).
    if 'fresh cookies' in low and ('needed' in low or 'are needed' in low):
        return (
            f'{action}失败：该站点需要“新鲜”的 cookies.txt（可能已过期/风控）。'
            '请重新从浏览器导出 cookies.txt（确保刚导出、未过期），'
            '然后在【设置】中为 douyin.com 覆盖导入后重试。'
            '若仍失败，请先升级 yt-dlp 到最新版本后再试。'
        )

    if (
        'http error 403' in low
        or '403 forbidden' in low
        or 'status code: 403' in low
        or ('403' in low and 'forbidden' in low)
    ):
        return f'{action}失败：站点返回 403（无权限/需要登录）。请在【设置】中为该域名导入 cookies.txt 后重试。'

    if (
        'http error 401' in low
        or '401 unauthorized' in low
        or 'status code: 401' in low
        or ('401' in low and 'unauthorized' in low)
    ):
        return f'{action}失败：站点返回 401（需要登录/授权）。请在【设置】中为该域名导入 cookies.txt 后重试。'

    if 'login required' in low or 'sign in' in low or 'account' in low and 'required' in low:
        return f'{action}失败：该内容需要登录/权限。请在【设置】中为该域名导入 cookies.txt 后重试。'

    # Fallback: keep details for other cases.
    if msg:
        return f'{action}失败：{msg}'
    return f'{action}失败'


def _format_bytes(value: int) -> str:
    if not value:
        return '0 B'
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    v = float(value)
    i = 0
    while v >= 1024.0 and i < len(units) - 1:
        v /= 1024.0
        i += 1
    if i == 0:
        return f'{int(v)} {units[i]}'
    return f'{v:.1f} {units[i]}'


def _estimate_filesize_bytes(fmt: Optional[dict], duration: int) -> int:
    if not fmt:
        return 0
    size = fmt.get('filesize') or fmt.get('filesize_approx')
    try:
        if size:
            return int(size)
    except Exception:
        pass

    # Fallback: bitrate (tbr is in Kbps)
    try:
        tbr = fmt.get('tbr')
        if tbr and duration:
            return int(float(tbr) * 1000.0 / 8.0 * float(duration))
    except Exception:
        pass
    return 0


def _estimate_merged_filesize_bytes(vfmt: Optional[dict], afmt: Optional[dict], duration: int) -> int:
    v = _estimate_filesize_bytes(vfmt, duration)
    a = _estimate_filesize_bytes(afmt, duration)
    if v and a:
        return v + a
    return v or a


def _pick_best_video_format(formats: list[dict], max_height: int) -> Optional[dict]:
    candidates = []
    for f in formats:
        if (f.get('vcodec') or 'none') == 'none':
            continue
        h = f.get('height')
        if not h:
            continue
        try:
            h_int = int(h)
        except Exception:
            continue
        if h_int > max_height:
            continue
        candidates.append(f)

    def score(f: dict) -> tuple:
        h = int(f.get('height') or 0)
        ext = (f.get('ext') or '').lower()
        ext_pref = 1 if ext == 'mp4' else 0
        tbr = float(f.get('tbr') or 0.0)
        size = int(f.get('filesize') or f.get('filesize_approx') or 0)
        return (h, ext_pref, tbr, size)

    if not candidates:
        return None
    return max(candidates, key=score)


def _pick_best_audio_format(formats: list[dict]) -> Optional[dict]:
    candidates = []
    for f in formats:
        if (f.get('acodec') or 'none') == 'none':
            continue
        if (f.get('vcodec') or 'none') != 'none':
            continue
        candidates.append(f)

    def score(f: dict) -> tuple:
        ext = (f.get('ext') or '').lower()
        ext_pref = 1 if ext in ('m4a', 'mp4') else 0
        abr = float(f.get('abr') or 0.0)
        tbr = float(f.get('tbr') or 0.0)
        size = int(f.get('filesize') or f.get('filesize_approx') or 0)
        return (ext_pref, abr, tbr, size)

    if not candidates:
        return None
    return max(candidates, key=score)


class DownloadTask(threading.Thread):
    """下载任务线程"""
    
    def __init__(
        self,
        task_id: Optional[str],
        url: str,
        format_id: str,
        output_dir: str,
        proxy: Optional[str] = None,
        create_folder: bool = False,
        convert_mp4: bool = False,
        write_thumbnail: bool = True,
        cookiefile: Optional[str] = None,
        fragment_downloads: int = 1,
        progress_callback: Optional[Callable] = None,
        complete_callback: Optional[Callable] = None,
        error_callback: Optional[Callable] = None
    ):
        super().__init__(daemon=True)
        self.task_id = task_id or uuid.uuid4().hex
        self.url = url
        self.format_id = format_id
        self.output_dir = output_dir
        self.proxy = proxy
        self.create_folder = create_folder
        self.convert_mp4 = bool(convert_mp4)
        self.write_thumbnail = bool(write_thumbnail)
        self.cookiefile = cookiefile
        self.fragment_downloads = max(1, int(fragment_downloads or 1))
        self.progress_callback = progress_callback
        self.complete_callback = complete_callback
        self.error_callback = error_callback
        self._stop_event = threading.Event()
        self._stop_reason = 'cancel'
        self._final_filepath: Optional[str] = None

    class DownloadStopped(Exception):
        """User initiated stop (cancel/pause)."""

        def __init__(self, reason: str):
            super().__init__(reason)
            self.reason = reason

    class _CancellationLogger:
        """Check stop flag during yt-dlp logging"""

        def __init__(self, stop_event: threading.Event, stop_reason_getter: Callable[[], str]):
            self._stop_event = stop_event
            self._stop_reason_getter = stop_reason_getter

        def debug(self, msg):
            if self._stop_event.is_set():
                raise DownloadTask.DownloadStopped(self._stop_reason_getter())

        def warning(self, msg):
            if self._stop_event.is_set():
                raise DownloadTask.DownloadStopped(self._stop_reason_getter())

        def error(self, msg):
            if self._stop_event.is_set():
                raise DownloadTask.DownloadStopped(self._stop_reason_getter())
    
    def stop(self, reason: str = 'cancel'):
        """请求停止下载。

        Args:
            reason: 'cancel' or 'pause'
        """
        r = (reason or '').strip().lower()
        if r not in ('cancel', 'pause'):
            r = 'cancel'
        self._stop_reason = r
        self._stop_event.set()
    
    def run(self):
        """执行下载任务"""
        try:
            # 根据格式选择 yt-dlp 选项
            requested_h: Optional[int] = None
            if self.format_id == '4k':
                requested_h = 2160
            else:
                try:
                    if self.format_id.endswith('p'):
                        requested_h = int(self.format_id[:-1])
                except Exception:
                    requested_h = None

            # Ensure output filenames are unique per resolution.
            if self.format_id == 'audio':
                name_tag = 'audio'
            elif requested_h:
                name_tag = f'{requested_h}p'
            else:
                name_tag = (self.format_id or 'best').strip().lower() or 'best'

            if self.format_id == 'audio':
                format_spec = 'bestaudio/best'
            elif requested_h:
                # Fallback chain (must use '/'): exact height -> <= height -> best <= height
                format_spec = (
                    f'bestvideo[height={requested_h}]+bestaudio'
                    f'/bestvideo[height<={requested_h}]+bestaudio'
                    f'/best[height<={requested_h}]'
                )
            else:
                format_spec = 'best'
            
            if self.create_folder:
                outtmpl = os.path.join(self.output_dir, '%(title)s', f'%(title)s [{name_tag}].%(ext)s')
            else:
                outtmpl = os.path.join(self.output_dir, f'%(title)s [{name_tag}].%(ext)s')

            ydl_opts: dict[str, Any] = {
                'format': format_spec,
                'outtmpl': outtmpl,
                'progress_hooks': [self._progress_hook],
                'postprocessor_hooks': [self._postprocessor_hook],
                'logger': self._CancellationLogger(self._stop_event, lambda: self._stop_reason),
                'quiet': True,
                'no_warnings': True,
                'windowsfilenames': True,
                'restrictfilenames': False,
                'writethumbnail': self.write_thumbnail,
            }

            # Ensure cover thumbnails are saved as JPG when possible.
            # Uses FFmpeg (same dependency as audio extraction).
            if self.write_thumbnail:
                ydl_opts['postprocessors'] = [
                    {
                        'key': 'FFmpegThumbnailsConvertor',
                        'format': 'jpg',
                    }
                ]

            if self.fragment_downloads > 1:
                # Enable multi-connection fragment downloads for DASH/HLS streams.
                ydl_opts['concurrent_fragment_downloads'] = int(self.fragment_downloads)

            if self.proxy:
                ydl_opts['proxy'] = self.proxy

            if self.cookiefile:
                ydl_opts['cookiefile'] = self.cookiefile
            
            # 音频格式特殊处理
            if self.format_id == 'audio':
                pp = [
                    {
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'flac',
                    }
                ]
                if self.write_thumbnail:
                    pp.append({'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg'})
                ydl_opts['postprocessors'] = pp
            
            ydl_opts_any: Any = ydl_opts
            with yt_dlp.YoutubeDL(ydl_opts_any) as ydl:
                ydl.download([self.url])

            if self.convert_mp4 and self.format_id != 'audio':
                if self._stop_event.is_set():
                    raise DownloadTask.DownloadStopped(self._stop_reason)

                src = (self._final_filepath or '').strip()
                if not src or not os.path.isfile(src):
                    raise RuntimeError('下载完成，但无法定位输出文件路径，无法转为 MP4')

                if not src.lower().endswith('.mp4'):
                    if self.progress_callback:
                        self.progress_callback(self.task_id, 100, '下载完成，转为 MP4 中...')
                    try:
                        dst = self._convert_to_mp4(src)
                        self._final_filepath = dst
                    except Exception as e:
                        if self.error_callback:
                            self.error_callback(self.task_id, f'下载完成，但转为 MP4 失败：{e}')
                        return
            
            if self.complete_callback:
                self.complete_callback(self.task_id, self._final_filepath)
                 
        except DownloadTask.DownloadStopped as e:
            if self.error_callback:
                if getattr(e, 'reason', 'cancel') == 'pause':
                    self.error_callback(self.task_id, '暂停')
                else:
                    self.error_callback(self.task_id, '已取消')
        except Exception as e:
            if self.error_callback:
                self.error_callback(self.task_id, _friendly_yt_dlp_error('下载', str(e)))
    
    def _progress_hook(self, d: dict):
        """进度回调钩子"""
        if self._stop_event.is_set():
            raise DownloadTask.DownloadStopped(self._stop_reason)
        
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded = d.get('downloaded_bytes', 0)
            
            if total > 0:
                percent = int(downloaded / total * 100)
                speed = d.get('speed', 0)
                speed_str = _format_speed(speed) if speed else '计算中...'

                eta_str = ''
                try:
                    if speed and downloaded is not None and total and total > downloaded:
                        remaining = float(total - downloaded)
                        eta_seconds = int(remaining / float(speed)) if float(speed) > 0 else 0
                        if eta_seconds > 0:
                            eta_str = _format_duration(eta_seconds)
                except Exception:
                    eta_str = ''

                status = f'下载中 {speed_str}'
                if eta_str:
                    status = f'{status} 剩余 {eta_str}'
                 
                if self.progress_callback:
                    self.progress_callback(self.task_id, percent, status)
        
        elif d['status'] == 'finished':
            try:
                fn = d.get('filename')
                if isinstance(fn, str) and fn.strip():
                    self._final_filepath = fn
            except Exception:
                pass
            if self.progress_callback:
                self.progress_callback(self.task_id, 100, '下载完成')

    def _postprocessor_hook(self, d: dict):
        """后处理阶段钩子"""
        if self._stop_event.is_set():
            raise DownloadTask.DownloadStopped(self._stop_reason)

        try:
            if d.get('status') == 'finished':
                info = d.get('info_dict')
                if isinstance(info, dict):
                    fp = info.get('filepath') or info.get('_filename')
                    if isinstance(fp, str) and fp.strip():
                        self._final_filepath = fp
        except Exception:
            pass

    def _convert_to_mp4(self, src_path: str) -> str:
        src = (src_path or '').strip()
        if not src or not os.path.isfile(src):
            raise RuntimeError('源文件不存在')

        root, _ext = os.path.splitext(src)
        dst = root + '.mp4'

        if os.path.normcase(os.path.abspath(dst)) == os.path.normcase(os.path.abspath(src)):
            return src

        # Avoid overwriting an existing file.
        if os.path.exists(dst):
            i = 1
            while True:
                cand = f"{root}-{i}.mp4"
                if not os.path.exists(cand):
                    dst = cand
                    break
                i += 1

        creationflags = subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0

        def run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess[str]:
            try:
                return subprocess.run(
                    args,
                    capture_output=True,
                    text=True,
                    timeout=None,
                    creationflags=creationflags,
                )
            except FileNotFoundError:
                raise RuntimeError('未检测到 FFmpeg，请先安装并加入 PATH')

        # 1) Prefer lossless remux (stream copy).
        remux_cmd = [
            'ffmpeg',
            '-y',
            '-i', src,
            '-map', '0:v:0',
            '-map', '0:a?',
            '-c', 'copy',
            '-sn',
            '-dn',
            '-movflags', '+faststart',
            dst,
        ]
        proc = run_ffmpeg(remux_cmd)

        # 2) Fallback: transcode to H.264/AAC for broad MP4 compatibility.
        if proc.returncode != 0:
            if os.path.exists(dst):
                try:
                    os.remove(dst)
                except Exception:
                    pass

            transcode_cmd = [
                'ffmpeg',
                '-y',
                '-i', src,
                '-map', '0:v:0',
                '-map', '0:a?',
                '-c:v', 'libx264',
                '-preset', 'veryfast',
                '-crf', '20',
                '-c:a', 'aac',
                '-b:a', '192k',
                '-sn',
                '-dn',
                '-movflags', '+faststart',
                dst,
            ]
            proc = run_ffmpeg(transcode_cmd)

        if proc.returncode != 0 or not os.path.isfile(dst):
            err = (proc.stderr or proc.stdout or '').strip()
            err_tail = '\n'.join(err.splitlines()[-12:]) if err else '未知错误'
            raise RuntimeError(f'FFmpeg 转换失败:\n{err_tail}')

        # Success: remove the original container file.
        try:
            os.remove(src)
        except Exception:
            pass

        return dst


def _format_duration(seconds: int) -> str:
    """格式化时长"""
    if not seconds:
        return '00:00'
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f'{hours}:{minutes:02d}:{secs:02d}'
    return f'{minutes:02d}:{secs:02d}'


def _format_views(count: int) -> str:
    """格式化观看次数"""
    if not count:
        return '0 观看'
    if count >= 1_000_000:
        return f'{count / 1_000_000:.1f}M 观看'
    if count >= 1_000:
        return f'{count / 1_000:.1f}K 观看'
    return f'{count} 观看'


def _format_speed(speed: float) -> str:
    """格式化下载速度"""
    if not speed:
        return '0 B/s'
    if speed >= 1_000_000:
        return f'{speed / 1_000_000:.1f} MB/s'
    if speed >= 1_000:
        return f'{speed / 1_000:.1f} KB/s'
    return f'{speed:.0f} B/s'
