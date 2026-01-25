# -*- mode: python ; coding: utf-8 -*-
"""
NebulaDL PyInstaller Spec File
Build command: pyinstaller NebulaDL.spec
"""

import os
import sys
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs

block_cipher = None

# 项目根目录
ROOT_DIR = os.path.dirname(os.path.abspath(SPEC))

# 收集 clr_loader 和 pythonnet 的所有文件（DLL、数据等）
clr_datas, clr_binaries, clr_hiddenimports = collect_all('clr_loader')
pnet_datas, pnet_binaries, pnet_hiddenimports = collect_all('pythonnet')
webview_datas, webview_binaries, webview_hiddenimports = collect_all('webview')

a = Analysis(
    ['main.py'],
    pathex=[ROOT_DIR],
    binaries=clr_binaries + pnet_binaries + webview_binaries,
    datas=[
        # 包含 templates 目录 (HTML/JS)
        ('templates', 'templates'),
        # 包含 assets 目录 (图标等)
        ('assets', 'assets'),
    ] + clr_datas + pnet_datas + webview_datas,
    hiddenimports=[
        'webview',
        'webview.platforms',
        'webview.platforms.winforms',
        'webview.platforms.edgechromium',
        'clr_loader',
        'clr_loader.ffi',
        'clr_loader.util',
        'pythonnet',
        'yt_dlp',
        'yt_dlp.extractor',
        'yt_dlp.downloader',
        'yt_dlp.postprocessor',
    ] + clr_hiddenimports + pnet_hiddenimports + webview_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='NebulaDL',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 无控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',  # 需要 .ico 格式图标
)
