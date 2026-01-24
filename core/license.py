"""NebulaDL - Pro License Verification Module"""

import os
import sys


class LicenseManager:
    """Pro 许可证管理器"""
    
    # 硬编码测试密钥
    VALID_KEYS = [
        "NEBULA-2026-PRO",
        "NEBULA-DEV-KEY",
    ]
    
    def __init__(self):
        # Testing/dev convenience:
        # - Source runs (not frozen) default to Pro for easier QA.
        # - Packaged builds remain Free by default.
        # Override:
        # - Set NEBULADL_FORCE_FREE=1 to force Free
        # - Set NEBULADL_FORCE_PRO=1 to force Pro
        force_free = str(os.environ.get('NEBULADL_FORCE_FREE') or '').strip().lower() in ('1', 'true', 'yes', 'on')
        force_pro = str(os.environ.get('NEBULADL_FORCE_PRO') or '').strip().lower() in ('1', 'true', 'yes', 'on')

        default_pro = bool(force_pro) or (not force_free and not getattr(sys, 'frozen', False))
        self._is_pro = default_pro
        self._activated_key = None
    
    @property
    def is_pro(self) -> bool:
        """检查当前是否已激活 Pro"""
        return self._is_pro
    
    def verify(self, key: str) -> dict:
        """
        验证许可证密钥
        
        Args:
            key: 用户输入的许可证密钥
            
        Returns:
            dict: {'success': bool, 'message': str}
        """
        if not key or not key.strip():
            return {
                'success': False,
                'message': '请输入有效的许可证密钥'
            }
        
        key = key.strip().upper()
        
        if key in self.VALID_KEYS:
            self._is_pro = True
            self._activated_key = key
            return {
                'success': True,
                'message': 'Pro 版本激活成功！'
            }
        else:
            return {
                'success': False,
                'message': '无效的许可证密钥'
            }
    
    def deactivate(self) -> None:
        """停用 Pro 许可证"""
        self._is_pro = False
        self._activated_key = None


# 全局单例
license_manager = LicenseManager()
