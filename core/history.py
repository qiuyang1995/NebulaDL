"""
NebulaDL - Download History Module

持久化记录下载历史，支持搜索和一键重下。
"""

import os
import json
import uuid
from typing import Optional, Any
from datetime import datetime


class DownloadHistory:
    """下载历史管理器"""

    HISTORY_FILE = os.path.join(os.path.expanduser('~'), '.nebuladl_history.json')
    MAX_RECORDS = 500  # 最多保存的记录数

    def __init__(self):
        self._records: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        """从文件加载历史记录"""
        try:
            if os.path.exists(self.HISTORY_FILE):
                with open(self.HISTORY_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self._records = data
        except Exception:
            self._records = []

    def _save(self) -> None:
        """保存历史记录到文件"""
        try:
            with open(self.HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._records, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add_record(
        self,
        url: str,
        title: str,
        format_id: str,
        output_path: str,
        status: str,
        error: Optional[str] = None
    ) -> str:
        """
        添加一条下载记录

        Args:
            url: 视频链接
            title: 视频标题
            format_id: 下载格式
            output_path: 保存路径
            status: 状态 ('completed', 'error', 'cancelled')
            error: 错误信息（可选）

        Returns:
            记录 ID
        """
        record_id = uuid.uuid4().hex[:12]
        record = {
            'id': record_id,
            'url': url,
            'title': title,
            'format_id': format_id,
            'output_path': output_path,
            'status': status,
            'error': error,
            'timestamp': datetime.now().isoformat(),
        }
        self._records.insert(0, record)

        # 限制记录数量
        if len(self._records) > self.MAX_RECORDS:
            self._records = self._records[:self.MAX_RECORDS]

        self._save()
        return record_id

    def get_records(self, query: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        """
        获取历史记录

        Args:
            query: 搜索关键词（可选，搜索标题和 URL）
            limit: 返回数量限制

        Returns:
            记录列表
        """
        if not query:
            return self._records[:limit]

        query_lower = query.lower()
        results = []
        for r in self._records:
            title = str(r.get('title') or '').lower()
            url = str(r.get('url') or '').lower()
            if query_lower in title or query_lower in url:
                results.append(r)
                if len(results) >= limit:
                    break
        return results

    def get_record_by_id(self, record_id: str) -> Optional[dict[str, Any]]:
        """根据 ID 获取单条记录"""
        for r in self._records:
            if r.get('id') == record_id:
                return r
        return None

    def delete_record(self, record_id: str) -> bool:
        """删除单条记录"""
        for i, r in enumerate(self._records):
            if r.get('id') == record_id:
                self._records.pop(i)
                self._save()
                return True
        return False

    def clear_all(self) -> None:
        """清空所有历史记录"""
        self._records = []
        self._save()


# 全局单例
download_history = DownloadHistory()
