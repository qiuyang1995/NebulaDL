let pywebviewReady = false;
let currentVideo = null;

function _parseUrlsFromInput(raw) {
    const text = String(raw || '');
    const lines = text.split(/\r?\n/);
    const out = [];
    const seen = new Set();
    for (const line of lines) {
        const v = String(line || '').trim();
        if (!v) continue;
        if (seen.has(v)) continue;
        seen.add(v);
        out.push(v);
    }
    return out;
}

function _getAnalyzeButton() {
    return document.querySelector('button[onclick="analyzeVideo()"]');
}

function _setAnalyzeButtonText(text) {
    const btn = _getAnalyzeButton();
    if (!btn) return;
    if (!btn.dataset.originalHtml) return;
    btn.innerHTML = String(text || '').trim() || btn.dataset.originalHtml;
}
let currentQueueItem = null;
let cookieMappings = [];

const taskButtons = {};

function openImagePreview(src) {
    const modal = document.getElementById('imagePreviewModal');
    const img = document.getElementById('imagePreviewImg');
    if (!modal || !img) return;
    const s = String(src || '').trim();
    if (!s) return;

    img.src = s;
    modal.classList.remove('hidden');
    modal.classList.add('flex');
    void modal.offsetWidth;
    modal.classList.remove('opacity-0');
}

function closeImagePreview() {
    const modal = document.getElementById('imagePreviewModal');
    const img = document.getElementById('imagePreviewImg');
    if (!modal) return;

    modal.classList.add('opacity-0');
    setTimeout(() => {
        modal.classList.add('hidden');
        modal.classList.remove('flex');
        if (img) img.src = '';
    }, 200);
}

document.addEventListener('keydown', (e) => {
    if (e && e.key === 'Escape') closeImagePreview();
});

// --- Image Preview Logic ---
// --- App Dialog Logic ---
function showAppDialog(optionsOrMsg) {
    const el = document.getElementById('appDialog');
    const content = document.getElementById('appDialogContent');
    const iconContainer = document.getElementById('appDialogIcon');
    const titleEl = document.getElementById('appDialogTitle');
    const msgEl = document.getElementById('appDialogMessage');

    if (!el || !content) return;

    let msg = '';
    let title = '提示';
    let type = 'info';

    if (typeof optionsOrMsg === 'object' && optionsOrMsg !== null) {
        msg = optionsOrMsg.message || '';
        title = optionsOrMsg.title || '提示';
        type = optionsOrMsg.type || 'info';
    } else {
        msg = String(optionsOrMsg);
    }

    if (titleEl) titleEl.textContent = title;
    if (msgEl) msgEl.textContent = msg;

    // Icon logic
    let iconHtml = '<i class="fa-solid fa-circle-info text-2xl text-blue-400"></i>';
    if (type === 'error' || title.includes('错误') || title.includes('失败')) {
        iconHtml = '<i class="fa-solid fa-triangle-exclamation text-2xl text-red-500"></i>';
    } else if (type === 'success' || title.includes('成功') || title.includes('完成')) {
        iconHtml = '<i class="fa-solid fa-circle-check text-2xl text-green-500"></i>';
    }
    if (iconContainer) iconContainer.innerHTML = iconHtml;

    el.classList.remove('hidden');
    void el.offsetWidth; // trigger reflow
    el.classList.remove('opacity-0');
    content.classList.remove('scale-95');
    content.classList.add('scale-100');
}

function closeAppDialog() {
    const el = document.getElementById('appDialog');
    const content = document.getElementById('appDialogContent');
    if (!el) return;

    el.classList.add('opacity-0');
    if (content) {
        content.classList.remove('scale-100');
        content.classList.add('scale-95');
    }
    setTimeout(() => el.classList.add('hidden'), 300);
}

function copyAppDialogText() {
    const msgEl = document.getElementById('appDialogMessage');
    if (!msgEl) return;
    const text = msgEl.textContent;
    navigator.clipboard.writeText(text).then(() => {
        const btn = document.querySelector('button[onclick="copyAppDialogText()"]');
        if (btn) {
            const original = btn.innerHTML;
            btn.innerHTML = '<i class="fa-solid fa-check mr-1"></i> 已复制';
            setTimeout(() => btn.innerHTML = original, 2000);
        }
    }).catch(err => console.error(err));
}

async function copyDiagnosticInfo() {
    if (!pywebviewReady || !_hasApi()) {
        showAppDialog({ title: '提示', message: '应用尚未就绪，请稍后再试', type: 'info' });
        return;
    }

    try {
        const raw = await window.pywebview.api.get_diagnostic_info();
        const res = _parseMaybeJson(raw);
        if (res && res.success && res.text) {
            await navigator.clipboard.writeText(res.text);
            const btn = document.querySelector('button[onclick="copyDiagnosticInfo()"]');
            if (btn) {
                const original = btn.innerHTML;
                btn.innerHTML = '<i class="fa-solid fa-check"></i> 已复制';
                setTimeout(() => btn.innerHTML = original, 2000);
            }
        } else {
            showAppDialog({ title: '获取失败', message: '无法获取诊断信息', type: 'error' });
        }
    } catch (e) {
        showAppDialog({ title: '错误', message: String(e), type: 'error' });
    }
}

// --- 下载历史相关 ---
let historySearchTimer = null;

async function showHistoryModal() {
    const modal = document.getElementById('historyModal');
    const content = modal?.querySelector('div');
    if (!modal) return;

    modal.classList.remove('hidden');
    void modal.offsetWidth;
    modal.classList.remove('opacity-0');
    if (content) {
        content.classList.remove('scale-95');
        content.classList.add('scale-100');
    }

    await loadHistoryRecords();
}

function closeHistoryModal() {
    const modal = document.getElementById('historyModal');
    const content = modal?.querySelector('div');
    if (!modal) return;

    modal.classList.add('opacity-0');
    if (content) {
        content.classList.remove('scale-100');
        content.classList.add('scale-95');
    }
    setTimeout(() => modal.classList.add('hidden'), 300);
}

function debounceHistorySearch() {
    if (historySearchTimer) clearTimeout(historySearchTimer);
    historySearchTimer = setTimeout(() => loadHistoryRecords(), 300);
}

async function loadHistoryRecords() {
    if (!pywebviewReady || !_hasApi()) return;

    const searchInput = document.getElementById('historySearchInput');
    const query = searchInput ? searchInput.value.trim() : '';

    try {
        const raw = await window.pywebview.api.get_history(query || null);
        const res = _parseMaybeJson(raw);
        if (res && res.success) {
            renderHistoryList(res.records || []);
        }
    } catch (e) {
        console.error('加载历史失败:', e);
    }
}

function renderHistoryList(records) {
    const container = document.getElementById('historyListContainer');
    if (!container) return;

    if (!records || records.length === 0) {
        container.innerHTML = `
            <div class="text-sm text-slate-500 text-center py-8">
                <i class="fa-solid fa-inbox text-3xl mb-2 block text-slate-600"></i>
                暂无下载记录
            </div>`;
        return;
    }

    container.innerHTML = records.map(r => {
        const title = _escapeHtml(r.title || r.url || '未知');
        const statusIcon = r.status === 'completed'
            ? '<i class="fa-solid fa-circle-check text-green-500"></i>'
            : r.status === 'cancelled'
                ? '<i class="fa-solid fa-ban text-slate-500"></i>'
                : '<i class="fa-solid fa-circle-xmark text-red-500"></i>';
        const timeStr = r.timestamp ? new Date(r.timestamp).toLocaleString() : '';
        const formatBadge = r.format_id ? `<span class="text-[10px] bg-slate-700 px-1.5 py-0.5 rounded">${_escapeHtml(r.format_id)}</span>` : '';
        const showFolderBtn = r.status === 'completed' && r.output_path;
        // 使用 Base64 编码路径避免转义问题
        const encodedPath = r.output_path ? btoa(unescape(encodeURIComponent(r.output_path))) : '';

        return `
            <div class="bg-slate-800/50 rounded-lg p-3 border border-slate-700/50 hover:border-slate-600 transition-colors">
                <div class="flex items-start justify-between gap-2">
                    <div class="flex-1 min-w-0">
                        <div class="flex items-center gap-2 mb-1">
                            ${statusIcon}
                            <span class="text-sm font-medium text-white truncate">${title}</span>
                        </div>
                        <div class="flex items-center gap-2 text-xs text-slate-500">
                            ${formatBadge}
                            <span>${timeStr}</span>
                        </div>
                    </div>
                    <div class="flex items-center gap-1 flex-shrink-0">
                        ${showFolderBtn ? `
                        <button onclick="openHistoryFolder('${encodedPath}')" title="打开文件夹"
                            class="w-7 h-7 rounded-lg bg-slate-700/50 hover:bg-green-600/50 text-slate-400 hover:text-green-300 flex items-center justify-center transition-colors">
                            <i class="fa-solid fa-folder-open text-xs"></i>
                        </button>` : ''}
                        <button onclick="redownloadRecord('${r.id}', '${_escapeHtml(r.title || '')}', '${_escapeHtml(r.format_id || 'best')}')" title="重新下载"
                            class="w-7 h-7 rounded-lg bg-slate-700/50 hover:bg-blue-600/50 text-slate-400 hover:text-blue-300 flex items-center justify-center transition-colors">
                            <i class="fa-solid fa-rotate-right text-xs"></i>
                        </button>
                        <button onclick="deleteHistoryRecord('${r.id}')" title="删除记录"
                            class="w-7 h-7 rounded-lg bg-slate-700/50 hover:bg-red-600/50 text-slate-400 hover:text-red-300 flex items-center justify-center transition-colors">
                            <i class="fa-solid fa-trash text-xs"></i>
                        </button>
                    </div>
                </div>
            </div>`;
    }).join('');
}

async function openHistoryFolder(encodedPath) {
    if (!pywebviewReady || !_hasApi()) return;
    try {
        // 解码 Base64 路径
        const path = decodeURIComponent(escape(atob(encodedPath)));
        console.log('打开文件夹:', path);
        await window.pywebview.api.open_folder(path);
    } catch (e) {
        console.error('打开文件夹失败:', e);
    }
}

async function redownloadRecord(recordId, title, formatId) {
    if (!pywebviewReady || !_hasApi()) return;

    try {
        const raw = await window.pywebview.api.redownload_from_history(recordId);
        const res = _parseMaybeJson(raw);
        if (res && res.success) {
            closeHistoryModal();
            // 在队列中创建项
            createQueueItem(title || '重新下载', formatId || 'best', 'mp4', res.task_id);
        } else {
            showAppDialog({ title: '失败', message: res?.error || '重新下载失败', type: 'error' });
        }
    } catch (e) {
        showAppDialog({ title: '错误', message: String(e), type: 'error' });
    }
}

async function deleteHistoryRecord(recordId) {
    if (!pywebviewReady || !_hasApi()) return;

    try {
        const raw = await window.pywebview.api.delete_history_record(recordId);
        const res = _parseMaybeJson(raw);
        if (res && res.success) {
            await loadHistoryRecords();
        }
    } catch (e) {
        console.error('删除记录失败:', e);
    }
}

async function clearAllHistory() {
    if (!pywebviewReady || !_hasApi()) return;

    try {
        const raw = await window.pywebview.api.clear_history();
        const res = _parseMaybeJson(raw);
        if (res && res.success) {
            await loadHistoryRecords();
        }
    } catch (e) {
        console.error('清空历史失败:', e);
    }
}

function _hasApi() {
    return typeof window !== 'undefined' && window.pywebview && window.pywebview.api;
}

function _parseMaybeJson(value) {
    if (typeof value === 'string') {
        try {
            return JSON.parse(value);
        } catch {
            return value;
        }
    }
    return value;
}

function _escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function _scrollToQueue() {
    const section = document.getElementById('downloadQueueSection') || document.getElementById('downloadQueue');
    if (!section) return;

    const scroller = section.closest('.overflow-y-auto') || document.querySelector('main .overflow-y-auto');
    if (scroller && typeof scroller.scrollTo === 'function') {
        const rect = section.getBoundingClientRect();
        const srect = scroller.getBoundingClientRect();
        const top = scroller.scrollTop + (rect.top - srect.top) - 24;
        scroller.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
        return;
    }

    section.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

window.addEventListener('pywebviewready', async function () {
    pywebviewReady = true;
});

function _syncUrlClearButton() {
    const input = document.getElementById('urlInput');
    const btn = document.getElementById('clearUrlBtn');
    if (!input || !btn) return;
    const hasValue = String(input.value || '').trim().length > 0;
    btn.classList.toggle('hidden', !hasValue);
    if (hasValue) btn.classList.add('flex');
    else btn.classList.remove('flex');
}

function clearUrlInput() {
    const input = document.getElementById('urlInput');
    if (!input) return;
    input.value = '';
    input.focus();
    _syncUrlClearButton();
}

(function _initUrlClearButton() {
    const input = document.getElementById('urlInput');
    if (!input) return;
    input.addEventListener('input', _syncUrlClearButton);
    _syncUrlClearButton();
})();

function _setAnalyzeLoading(loading) {
    const btn = _getAnalyzeButton();
    if (!btn) return;

    if (loading) {
        btn.dataset.originalHtml = btn.innerHTML;
        btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> 解析中...';
        btn.disabled = true;
    } else {
        if (btn.dataset.originalHtml) {
            btn.innerHTML = btn.dataset.originalHtml;
            delete btn.dataset.originalHtml;
        }
        btn.disabled = false;
    }
}

async function analyzeVideo() {
    const input = document.getElementById('urlInput');
    const emptyState = document.getElementById('emptyState');
    const resultsList = document.getElementById('resultsList');
    const template = document.getElementById('resultCardTemplate');

    const urls = _parseUrlsFromInput(input && typeof input.value !== 'undefined' ? input.value : '');
    if (!input || urls.length === 0) {
        if (input) {
            input.focus();
            input.classList.add('ring-2', 'ring-red-500');
            setTimeout(() => input.classList.remove('ring-2', 'ring-red-500'), 500);
        }
        return;
    }

    if (!pywebviewReady || !_hasApi()) {
        showAppDialog({ title: '系统提示', message: '应用 API 尚未就绪，请稍后再试', type: 'warning' });
        return;
    }

    _setAnalyzeLoading(true);

    try {
        if (resultsList) {
            // 不再清空，追加新卡片
            // resultsList.innerHTML = '';
            // resultsList.classList.add('hidden');
        }

        let okCount = 0;
        for (let i = 0; i < urls.length; i++) {
            const url = urls[i];
            _setAnalyzeButtonText(`<i class="fa-solid fa-circle-notch fa-spin"></i> 解析中 (${i + 1}/${urls.length})...`);

            const timeoutMs = 180000;
            const timeoutPromise = new Promise((_, reject) => {
                setTimeout(() => reject(new Error('__NEBULADL_ANALYZE_TIMEOUT__')), timeoutMs);
            });
            const raw = await Promise.race([
                window.pywebview.api.analyze_video(url),
                timeoutPromise
            ]);
            const res = _parseMaybeJson(raw);

            if (!res || !res.success) {
                const errMsg = (res && res.error) ? String(res.error) : '视频解析失败';
                if (urls.length === 1) {
                    if (errMsg.includes('网络异常') || errMsg.includes('超时')) {
                        showAppDialog({ title: '网络异常', message: errMsg, type: 'error' });
                    } else {
                        showAppDialog({ title: '解析失败', message: errMsg, type: 'error' });
                    }
                    return;
                }
                // multi-url mode: skip failures, continue
                continue;
            }

            const data = res.data;
            currentVideo = data;

            if (!resultsList || !template) {
                okCount += 1;
                continue;
            }

            const frag = template.content.cloneNode(true);
            const card = frag.querySelector('.result-card');
            if (!card) {
                okCount += 1;
                continue;
            }

            card.dataset.url = String(data && data.url ? data.url : url);
            card.dataset.title = String(data && data.title ? data.title : '');

            resultsList.appendChild(card);
            renderVideo(data, card);
            okCount += 1;
        }

        if (okCount > 0) {
            if (emptyState) emptyState.classList.add('hidden');
            if (resultsList) {
                resultsList.classList.remove('hidden');
                resultsList.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        } else {
            // 如果解析失败，且当前没有任何卡片，才显示空状态
            if (resultsList && resultsList.children.length === 0) {
                resultsList.classList.add('hidden');
                if (emptyState) emptyState.classList.remove('hidden');
            }
            showAppDialog({ title: '解析失败', message: '没有解析出可用的视频信息，请检查链接或网络后重试', type: 'error' });
        }
    } catch (e) {
        const msg = (e && e.message ? String(e.message) : String(e));
        if (msg.includes('__NEBULADL_ANALYZE_TIMEOUT__')) {
            showAppDialog({ title: '网络异常', message: '网络异常，解析超时，请检查网络连接或稍后再试', type: 'error' });
        } else {
            showAppDialog({ title: '系统错误', message: msg, type: 'error' });
        }
    } finally {
        _setAnalyzeLoading(false);
    }
}

function renderVideo(data, root) {
    if (!data || !root) return;

    const thumbImg = root.querySelector('.thumb-img');
    if (thumbImg) {
        if (data.thumbnail) thumbImg.src = data.thumbnail;
        thumbImg.onclick = () => openImagePreview(thumbImg.src);
        thumbImg.onkeydown = (e) => {
            const key = e && e.key ? String(e.key) : '';
            if (key === 'Enter' || key === ' ') {
                e.preventDefault();
                openImagePreview(thumbImg.src);
            }
        };
    }

    const durationBadge = root.querySelector('.duration-badge');
    if (durationBadge) durationBadge.textContent = data.duration_str || '00:00';

    const titleEl = root.querySelector('.video-title');
    if (titleEl) titleEl.textContent = data.title || '未知标题';

    const viewCountEl = root.querySelector('.view-count');
    if (viewCountEl) {
        const icon = viewCountEl.querySelector('i');
        viewCountEl.textContent = ' ' + (data.view_count || '0 观看');
        if (icon) viewCountEl.prepend(icon);
    }

    const uploaderEl = root.querySelector('.uploader-name');
    if (uploaderEl) {
        const icon = uploaderEl.querySelector('i');
        uploaderEl.textContent = ' ' + (data.uploader || '未知频道');
        if (icon) uploaderEl.prepend(icon);
    }

    const siteContainer = root.querySelector('.site-name-container');
    const siteText = root.querySelector('.site-name-text');
    if (siteContainer && siteText) {
        if (data.site) {
            siteText.textContent = data.site;
            siteContainer.classList.remove('hidden');
            siteContainer.classList.add('flex');
        } else {
            siteContainer.classList.add('hidden');
            siteContainer.classList.remove('flex');
        }
    }

    renderFormats(Array.isArray(data.formats) ? data.formats : [], root, data);

    // 添加关闭按钮到卡片右上角
    if (!root.querySelector('.card-close-btn')) {
        const closeBtn = document.createElement('button');
        closeBtn.className = 'card-close-btn absolute top-3 right-3 w-8 h-8 rounded-full bg-slate-800/80 hover:bg-red-600 text-slate-400 hover:text-white transition-all flex items-center justify-center z-10';
        closeBtn.title = '移除此卡片';
        closeBtn.innerHTML = '<i class="fa-solid fa-xmark text-sm"></i>';
        closeBtn.onclick = (e) => {
            e.stopPropagation();
            root.remove();
            // 如果没有卡片了，显示空状态
            const resultsList = document.getElementById('resultsList');
            const emptyState = document.getElementById('emptyState');
            if (resultsList && resultsList.children.length === 0) {
                resultsList.classList.add('hidden');
                if (emptyState) emptyState.classList.remove('hidden');
            }
        };
        root.style.position = 'relative';
        root.appendChild(closeBtn);
    }
}

function renderFormats(formats, root, videoData) {
    const table = root ? root.querySelector('.format-table') : null;
    if (!table) return;

    table.innerHTML = '';

    const header = document.createElement('div');
    header.className = 'grid grid-cols-4 px-4 py-2 bg-slate-800/80 text-xs font-semibold text-slate-400 uppercase';
    header.innerHTML = '<div>格式</div><div>分辨率</div><div>大小</div><div class="text-right">操作</div>';
    table.appendChild(header);

    if (!formats.length) {
        const row = document.createElement('div');
        row.className = 'px-4 py-4 text-sm text-slate-400';
        row.textContent = '未找到可用格式';
        table.appendChild(row);
        return;
    }

    for (const fmt of formats) {
        const row = document.createElement('div');
        row.className = 'grid grid-cols-4 px-4 py-3 border-b border-slate-800/50 items-center hover:bg-slate-800/30 transition-colors';

        const ext = (fmt.ext || '').toUpperCase();
        const label = fmt.label || fmt.id || '-';
        const size = fmt.size || '未知';
        const formatId = fmt.id || 'best';

        const extEsc = _escapeHtml(ext || 'N/A');
        const labelEsc = _escapeHtml(label);
        const sizeEsc = _escapeHtml(size);

        const badgeColor = 'bg-blue-900/30 text-blue-400 border-blue-900/50';
        row.innerHTML = `
            <div class="flex items-center gap-2">
                <span class="${badgeColor} text-xs px-2 py-0.5 rounded border">${extEsc}</span>
            </div>
            <div class="text-sm text-slate-300">${labelEsc}</div>
            <div class="text-sm text-slate-400">${sizeEsc}</div>
            <div class="text-right"></div>
        `;

        const actionCell = row.lastElementChild;
        const btn = document.createElement('button');
        btn.className = 'bg-slate-700 hover:bg-green-600 text-white text-xs px-3 py-1.5 rounded-md transition-all';
        btn.innerHTML = '<i class="fa-solid fa-download mr-1"></i> 下载';
        btn.dataset.mode = 'download';
        btn.dataset.formatId = formatId;
        btn.dataset.label = label;
        btn.dataset.ext = ext;
        btn.dataset.url = String((videoData && videoData.url) ? videoData.url : '');
        btn.dataset.title = String((videoData && videoData.title) ? videoData.title : '');
        btn.dataset.size = size;
        btn.onclick = (e) => handleFormatAction(e.currentTarget);
        actionCell.appendChild(btn);

        table.appendChild(row);
    }

    const rows = table.querySelectorAll('div.grid.grid-cols-4');
    if (rows.length > 1) {
        const last = rows[rows.length - 1];
        last.classList.remove('border-b');
    }
}

function _setFormatButtonUi(btn, mode) {
    if (!btn) return;
    const m = String(mode || '').toLowerCase();
    if (m === 'pause') {
        btn.innerHTML = '<i class="fa-solid fa-pause mr-1"></i> 暂停';
        btn.dataset.mode = 'pause';
        return;
    }
    if (m === 'resume') {
        btn.innerHTML = '<i class="fa-solid fa-download mr-1"></i> 下载';
        btn.dataset.mode = 'resume';
        return;
    }
    btn.innerHTML = '<i class="fa-solid fa-download mr-1"></i> 下载';
    btn.dataset.mode = 'download';
}

async function handleFormatAction(btn) {
    if (!btn) return;
    const mode = String(btn.dataset.mode || 'download').toLowerCase();

    if (mode === 'pause') {
        const taskId = String(btn.dataset.taskId || '').trim();
        if (!taskId) return;
        try {
            const raw = await window.pywebview.api.pause_download(taskId);
            const res = _parseMaybeJson(raw);
            if (res && res.success) {
                _setFormatButtonUi(btn, 'resume');
            }
        } catch {
            // ignore
        }
        return;
    }

    if (mode === 'resume') {
        const taskId = String(btn.dataset.taskId || '').trim();
        if (!taskId) return;
        try {
            const raw = await window.pywebview.api.resume_download(taskId);
            const res = _parseMaybeJson(raw);
            if (res && res.success) {
                _setFormatButtonUi(btn, 'pause');
            }
        } catch {
            // ignore
        }
        return;
    }

    const formatId = String(btn.dataset.formatId || 'best');
    const label = String(btn.dataset.label || '');
    const ext = String(btn.dataset.ext || '');
    const url = String(btn.dataset.url || '').trim();
    const title = String(btn.dataset.title || '');
    const size = String(btn.dataset.size || '');
    await startDownload(url, title, formatId, label, ext, size, btn);
}

async function startDownload(videoUrl, videoTitle, formatId, label, ext, fileSize, btnElement = null) {
    // 1. Disable button immediately
    if (btnElement) {
        btnElement.disabled = true;
        btnElement.classList.add('opacity-50', 'cursor-not-allowed');
    }

    const url = String(videoUrl || '').trim();
    if (!url) {
        showAppDialog({ title: '操作提示', message: '请先解析视频', type: 'warning' });
        if (btnElement) {
            btnElement.disabled = false;
            btnElement.classList.remove('opacity-50', 'cursor-not-allowed');
        }
        return;
    }

    if (!pywebviewReady || !_hasApi()) {
        showAppDialog({ title: '系统提示', message: '应用 API 尚未就绪', type: 'warning' });
        if (btnElement) {
            btnElement.disabled = false;
            btnElement.classList.remove('opacity-50', 'cursor-not-allowed');
        }
        return;
    }

    try {
        const raw = await window.pywebview.api.start_download(url, formatId);
        const res = _parseMaybeJson(raw);

        if (!res || !res.success) {
            // Re-enable on failure
            if (btnElement) {
                btnElement.disabled = false;
                btnElement.classList.remove('opacity-50', 'cursor-not-allowed');
            }

            showAppDialog({ title: '下载失败', message: (res && res.error) ? res.error : '下载启动失败', type: 'error' });
            return;
        }

        // Updated: Pass task_id and file size
        createQueueItem(videoTitle || '下载任务', label, ext, res.task_id, fileSize);

        if (btnElement) {
            btnElement.disabled = false;
            btnElement.classList.remove('opacity-50', 'cursor-not-allowed');
            btnElement.dataset.taskId = res.task_id;
            taskButtons[String(res.task_id)] = btnElement;
            _setFormatButtonUi(btnElement, 'pause');
        }

        // Scroll after we actually added the queue item.
        _scrollToQueue();
    } catch (e) {
        // Re-enable on error
        if (btnElement) {
            btnElement.disabled = false;
            btnElement.classList.remove('opacity-50', 'cursor-not-allowed');
        }
        showAppDialog({ title: '系统错误', message: (e && e.message ? e.message : String(e)), type: 'error' });
    }
}

function createQueueItem(title, label, ext, taskId, fileSize) {
    const queue = document.getElementById('downloadQueue');
    if (!queue) return;

    const item = document.createElement('div');
    // Use ID for updates
    item.id = 'task-' + taskId;
    item.className = 'bg-slate-800/50 border border-slate-700 rounded-xl p-4 flex items-center gap-4 fade-in';

    const filename = `${title} [${label}].${(ext || 'mp4').toLowerCase()}`;
    const filenameEsc = _escapeHtml(filename);
    const labelEsc = _escapeHtml(label);
    const sizeEsc = _escapeHtml(fileSize || '未知大小');

    // Safe fallback if taskId is undefined (shouldn't happen with new API)
    const safeTaskId = taskId || 'unknown';

    item.innerHTML = `
        <div class="w-10 h-10 bg-blue-900/30 text-blue-400 rounded-lg flex items-center justify-center flex-shrink-0">
            <i class="fa-solid fa-video"></i>
        </div>
        <div class="flex-1 min-w-0 overflow-hidden">
            <div class="mb-1">
                <div class="text-sm font-medium text-white break-words line-clamp-2" title="${filenameEsc}">${filenameEsc}</div>
            </div>
            <div class="flex justify-between items-center mb-1">
                <span class="text-xs text-slate-400 status-text truncate">${labelEsc} · 等待中...</span>
                <span class="text-xs text-slate-500 file-size-text">${sizeEsc}</span>
            </div>
            <div class="w-full bg-slate-700 h-1.5 rounded-full overflow-hidden">
                <div class="bg-blue-500 h-full rounded-full progress-bar" style="width: 0%"></div>
            </div>
        </div>
        <div class="flex items-center gap-1">
            <button id="btn-retry-${safeTaskId}" onclick="retryTask('${safeTaskId}')"
                class="hidden w-8 h-8 rounded-full hover:bg-slate-700 text-slate-500 hover:text-yellow-400 transition-colors flex items-center justify-center"
                title="重试">
                <i class="fa-solid fa-rotate-right text-xs"></i>
            </button>
            <button id="btn-pause-${safeTaskId}" onclick="togglePause('${safeTaskId}')"
                class="w-8 h-8 rounded-full hover:bg-slate-700 text-slate-500 hover:text-white transition-colors flex items-center justify-center"
                title="暂停/继续">
                <i class="fa-solid fa-pause text-xs"></i>
            </button>
            <button onclick="cancelOrCloseQueueItem('${safeTaskId}')"
                class="w-8 h-8 rounded-full hover:bg-slate-700 text-slate-500 hover:text-red-400 transition-colors flex items-center justify-center"
                title="取消下载">
                <i class="fa-solid fa-xmark text-xs"></i>
            </button>
        </div>
    `;

    // Removed manual onclick binding since we use inline onclick for clarity and closure capture


    queue.prepend(item);
    // currentQueueItem = item; // No longer used for single tracking
}

function cancelOrCloseQueueItem(taskId) {
    const item = document.getElementById('task-' + taskId);
    if (!item) return;

    const statusEl = item.querySelector('.status-text');
    const status = (statusEl && statusEl.textContent) ? statusEl.textContent.trim() : '';
    // If task is already finished/cancelled/failed, close immediately.
    if (status.includes('下载完成') || status.includes('已取消') || status.includes('下载失败')) {
        item.remove();
        return;
    }

    // Second click after cancellation closes/removes the queue card.
    if (item.dataset.cancelled === '1') {
        item.remove();
        return;
    }

    item.dataset.cancelled = '1';
    cancelDownload(taskId);
}

function updateProgress(taskId, percent, status) {
    // Support both old signature (percent, status) and new (taskId, percent, status)
    // If taskId is number or string looking like ID, use it. If it looks like percent (number), shift args.
    // Actually, safest is to check if element exists.

    let id = taskId;
    let p = percent;
    let s = status;

    // Handle legacy calls if any
    if (typeof taskId === 'number' && typeof percent === 'string') {
        // Old signature: updateProgress(percent, status)
        // We can't identify the task easily unless we kept currentQueueItem.
        // But prompt implies Python sends taskId now.
        // Assuming new signature is strictly followed by Python.
    }

    const item = document.getElementById('task-' + id);
    if (!item) return;

    const bar = item.querySelector('.progress-bar');
    const statusEl = item.querySelector('.status-text');
    const pauseBtn = item.querySelector(`#btn-pause-${id}`);
    const pauseIcon = pauseBtn ? pauseBtn.querySelector('i') : null;

    const pNum = Number(p);
    if (bar && !Number.isNaN(pNum) && pNum >= 0) {
        bar.style.width = `${Math.max(0, Math.min(100, pNum))}%`;
    }
    if (statusEl) statusEl.textContent = s || '';

    // Handle Pause/Resume UI state
    if (s && (s.includes('Paused') || s.includes('暂停'))) {
        if (pauseIcon) pauseIcon.className = 'fa-solid fa-play text-xs ml-0.5';
        if (bar) {
            bar.classList.remove('bg-blue-500', 'bg-green-500', 'bg-red-500');
            bar.classList.add('bg-yellow-500');
        }
    } else {
        // Default running state
        if (pauseIcon) pauseIcon.className = 'fa-solid fa-pause text-xs';
        if (bar && !bar.classList.contains('bg-green-500') && !bar.classList.contains('bg-red-500')) {
            bar.classList.remove('bg-yellow-500');
            bar.classList.add('bg-blue-500');
        }
    }
}

function _resetFormatButtonForTask(taskId) {
    const id = String(taskId || '').trim();
    if (!id) return;
    const btn = taskButtons[id];
    if (!btn) return;

    delete taskButtons[id];
    delete btn.dataset.taskId;
    btn.disabled = false;
    btn.classList.remove('opacity-50', 'cursor-not-allowed');
    _setFormatButtonUi(btn, 'download');
}

function onDownloadComplete(taskId) {
    updateProgress(taskId, 100, '下载完成');
    _resetFormatButtonForTask(taskId);
    const item = document.getElementById('task-' + taskId);
    if (item) {
        const bar = item.querySelector('.progress-bar');
        if (bar) {
            bar.classList.remove('bg-blue-500');
            bar.classList.add('bg-green-500');
        }
        // 隐藏暂停按钮
        const pauseBtn = item.querySelector(`#btn-pause-${taskId}`);
        if (pauseBtn) pauseBtn.classList.add('hidden');
    }
}

function onDownloadError(taskId, message) {
    updateProgress(taskId, 0, '下载失败');
    _resetFormatButtonForTask(taskId);
    const item = document.getElementById('task-' + taskId);
    if (item) {
        const retryBtn = item.querySelector(`#btn-retry-${taskId}`);
        if (retryBtn) retryBtn.classList.remove('hidden');

        const pauseBtn = item.querySelector(`#btn-pause-${taskId}`);
        if (pauseBtn) {
            pauseBtn.disabled = true;
            pauseBtn.classList.add('opacity-50', 'cursor-not-allowed');
        }

        const statusEl = item.querySelector('.status-text');
        if (statusEl) {
            statusEl.textContent = message || '下载失败';
            statusEl.classList.add('text-red-400');
        }
        const bar = item.querySelector('.progress-bar');
        if (bar) {
            bar.classList.remove('bg-blue-500');
            bar.classList.add('bg-red-500');
            bar.style.width = '100%';
        }
    }
}

async function retryTask(taskId) {
    const tid = String(taskId || '').trim();
    if (!tid) return;
    if (!pywebviewReady || !_hasApi()) return;

    const item = document.getElementById('task-' + tid);
    if (!item) return;

    const retryBtn = item.querySelector(`#btn - retry - ${tid} `);
    const pauseBtn = item.querySelector(`#btn - pause - ${tid} `);
    const statusEl = item.querySelector('.status-text');
    const bar = item.querySelector('.progress-bar');

    if (retryBtn) {
        retryBtn.disabled = true;
        retryBtn.classList.add('opacity-50', 'cursor-not-allowed');
    }

    try {
        const raw = await window.pywebview.api.retry_download(tid);
        const res = _parseMaybeJson(raw);
        if (!res || !res.success) {
            if (retryBtn) {
                retryBtn.disabled = false;
                retryBtn.classList.remove('opacity-50', 'cursor-not-allowed');
            }
            return;
        }

        if (retryBtn) {
            retryBtn.classList.add('hidden');
            retryBtn.disabled = false;
            retryBtn.classList.remove('opacity-50', 'cursor-not-allowed');
        }

        if (statusEl) {
            statusEl.classList.remove('text-red-400');
            statusEl.textContent = '等待中...';
        }

        if (bar) {
            bar.classList.remove('bg-red-500', 'bg-green-500');
            bar.classList.add('bg-blue-500');
            bar.style.width = '0%';
        }

        if (pauseBtn) {
            pauseBtn.disabled = false;
            pauseBtn.classList.remove('opacity-50', 'cursor-not-allowed');
        }
    } catch {
        if (retryBtn) {
            retryBtn.disabled = false;
            retryBtn.classList.remove('opacity-50', 'cursor-not-allowed');
        }
    }
}

async function cancelDownload(taskId) {
    if (!pywebviewReady || !_hasApi()) return;
    try {
        // Pass taskId if available
        await window.pywebview.api.cancel_download(taskId);
        updateProgress(taskId, 0, '已取消');
        _resetFormatButtonForTask(taskId);
    } catch {
        // ignore
    }
}

async function togglePause(taskId) {
    const tid = String(taskId || '').trim();
    if (!tid) return;
    if (!pywebviewReady || !_hasApi()) return;

    const item = document.getElementById('task-' + tid);
    const statusEl = item ? item.querySelector('.status-text') : null;
    const status = statusEl ? String(statusEl.textContent || '') : '';
    const pauseBtn = item ? item.querySelector(`#btn-pause-${tid}`) : null;
    const pauseIcon = pauseBtn ? pauseBtn.querySelector('i') : null;

    const btn = taskButtons[tid];

    // If currently paused -> resume.
    if (status.includes('暂停')) {
        // 立即更新图标
        if (pauseIcon) pauseIcon.className = 'fa-solid fa-pause text-xs';
        try {
            const raw = await window.pywebview.api.resume_download(tid);
            const res = _parseMaybeJson(raw);
            if (res && res.success) {
                if (btn) _setFormatButtonUi(btn, 'pause');
                updateProgress(tid, -1, '等待中...');
            }
        } catch {
            // ignore
        }
        return;
    }

    // Otherwise pause - 立即更新图标
    if (pauseIcon) pauseIcon.className = 'fa-solid fa-play text-xs';
    try {
        const raw = await window.pywebview.api.pause_download(tid);
        const res = _parseMaybeJson(raw);
        if (res && res.success) {
            if (btn) _setFormatButtonUi(btn, 'resume');
            updateProgress(tid, -1, '暂停');
        } else {
            // 如果失败，恢复图标
            if (pauseIcon) pauseIcon.className = 'fa-solid fa-pause text-xs';
        }
    } catch {
        // 如果出错，恢复图标
        if (pauseIcon) pauseIcon.className = 'fa-solid fa-pause text-xs';
    }
}

// --- Cookie Logic ---
function renderCookieList() {
    const container = document.getElementById('cookieListContainer');
    if (!container) return;

    container.innerHTML = '';

    if (!cookieMappings || cookieMappings.length === 0) {
        container.innerHTML = '<div class="text-xs text-slate-500 text-center py-2 italic" id="noCookieText">暂无配置 Cookie，部分站点可能无法解析/下载。</div>';
        return;
    }

    for (const item of cookieMappings) {
        const domain = (item && item.domain) ? String(item.domain) : '';
        const path = (item && item.path) ? String(item.path) : '';
        const fileName = path ? path.split(/[/\\]/).pop() : '';

        const row = document.createElement('div');
        row.className = 'flex items-center justify-between bg-slate-900/50 rounded-lg p-2 border border-slate-700/50 text-xs';

        const domainEsc = _escapeHtml(domain);
        const fileNameEsc = _escapeHtml(fileName);
        const pathEsc = _escapeHtml(path);

        row.innerHTML = `
        < div class="flex items-center gap-2 overflow-hidden" >
                <i class="fa-solid fa-cookie-bite text-yellow-500 w-4 text-center"></i>
                <span class="font-medium text-slate-300 font-mono truncate max-w-[160px]" title="${domainEsc}">${domainEsc}</span>
                <span class="text-slate-500 truncate max-w-[120px] ml-1" title="${pathEsc}">${fileNameEsc}</span>
            </div >
        <button onclick="removeCookieMapping('${domainEsc}')" class="text-slate-500 hover:text-red-400 transition-colors px-1">
            <i class="fa-solid fa-trash"></i>
        </button>
    `;

        container.appendChild(row);
    }
}

async function refreshCookieMappings() {
    if (!pywebviewReady || !_hasApi()) {
        cookieMappings = [];
        renderCookieList();
        return;
    }

    try {
        const raw = await window.pywebview.api.get_cookie_mappings();
        const res = _parseMaybeJson(raw);
        if (res && res.success && Array.isArray(res.items)) {
            cookieMappings = res.items;
        } else {
            cookieMappings = [];
        }
    } catch {
        cookieMappings = [];
    }

    renderCookieList();
}

async function importCookieForDomain() {
    const input = document.getElementById('cookieDomainInput');
    const domainOrUrl = input ? String(input.value || '').trim() : '';
    if (!domainOrUrl) {
        showAppDialog({ title: '提示', message: '请输入域名或链接', type: 'warning' });
        return;
    }
    if (!pywebviewReady || !_hasApi()) {
        showAppDialog({ title: '系统提示', message: '应用 API 尚未就绪', type: 'warning' });
        return;
    }

    try {
        const pickRaw = await window.pywebview.api.choose_cookie_file();
        const pick = _parseMaybeJson(pickRaw);
        if (!pick || !pick.success || !pick.path) {
            showAppDialog({ title: '导入失败', message: (pick && pick.error) ? pick.error : '未选择文件', type: 'error' });
            return;
        }

        const setRaw = await window.pywebview.api.set_cookie_mapping(domainOrUrl, pick.path);
        const setRes = _parseMaybeJson(setRaw);
        if (!setRes || !setRes.success) {
            showAppDialog({ title: '保存失败', message: (setRes && setRes.error) ? setRes.error : '保存失败', type: 'error' });
            return;
        }

        if (input) input.value = '';
        await refreshCookieMappings();
        showAppDialog({ title: '成功', message: 'Cookie 已保存', type: 'success' });
    } catch (e) {
        showAppDialog({ title: '保存失败', message: (e && e.message ? e.message : String(e)), type: 'error' });
    }
}

async function removeCookieMapping(domain) {
    const d = String(domain || '').trim();
    if (!d) return;
    if (!pywebviewReady || !_hasApi()) return;
    try {
        await window.pywebview.api.remove_cookie_mapping(d);
    } catch {
        // ignore
    }
    await refreshCookieMappings();
}

// --- Cookie Guide Modal Logic ---
const cookieGuideModal = document.getElementById('cookieGuideModal');

function showCookieGuideModal() {
    if (!cookieGuideModal) return;
    cookieGuideModal.classList.remove('hidden');
    void cookieGuideModal.offsetWidth;
    cookieGuideModal.classList.remove('opacity-0');
    const child = cookieGuideModal.querySelector('div');
    if (child) {
        child.classList.remove('scale-95');
        child.classList.add('scale-100');
    }
}

function closeCookieGuideModal() {
    if (!cookieGuideModal) return;
    cookieGuideModal.classList.add('opacity-0');
    const child = cookieGuideModal.querySelector('div');
    if (child) {
        child.classList.remove('scale-100');
        child.classList.add('scale-95');
    }
    setTimeout(() => {
        cookieGuideModal.classList.add('hidden');
    }, 300);
}

// --- Batch Download Logic ---

const batchModal = document.getElementById('batchModal');
const batchContent = batchModal ? batchModal.querySelector('div') : null;

function handleBatchClick() {
    showBatchModal();
}

function showBatchModal() {
    if (!batchModal || !batchContent) return;
    batchModal.classList.remove('hidden');
    void batchModal.offsetWidth;
    batchModal.classList.remove('opacity-0');
    batchContent.classList.remove('scale-95');
    batchContent.classList.add('scale-100');
}

function closeBatchModal() {
    if (!batchModal || !batchContent) return;
    batchModal.classList.add('opacity-0');
    batchContent.classList.remove('scale-100');
    batchContent.classList.add('scale-95');
    setTimeout(() => batchModal.classList.add('hidden'), 300);
}

async function startBatchDownload() {
    const urlsArea = document.getElementById('batchUrls');
    const formatSelect = document.getElementById('batchFormat');

    if (!urlsArea || !formatSelect) return;

    const text = urlsArea.value;
    if (!text.trim()) {
        showAppDialog({ title: '提示', message: '请粘贴视频链接', type: 'warning' });
        return;
    }

    const urls = text.split('\n').map(u => u.trim()).filter(u => u.length > 0);
    if (urls.length === 0) {
        showAppDialog({ title: '提示', message: '未检测到有效链接', type: 'warning' });
        return;
    }

    if (!pywebviewReady || !_hasApi()) {
        showAppDialog({ title: '系统提示', message: 'API 未就绪', type: 'warning' });
        return;
    }

    const formatId = formatSelect.value;
    // Map simple format ID to label/ext for UI if needed, 
    // but we mostly rely on task info returned by backend.

    try {
        const raw = await window.pywebview.api.start_batch_download(urls, formatId);
        const res = _parseMaybeJson(raw);

        if (res && res.success && Array.isArray(res.tasks)) {
            closeBatchModal();
            // Clear input
            urlsArea.value = '';

            // Create tasks
            // Reverse to keep order or just append? 
            // createQueueItem prepends, so if we want 1st URL at bottom, loop normally.
            // If we want 1st URL at top, loop in reverse.
            // Let's loop reverse so the first one ends up at the top of the list.
            for (let i = res.tasks.length - 1; i >= 0; i--) {
                const task = res.tasks[i];
                const label = (formatId === 'audio' ? 'Audio Only' : (formatId === 'best' ? 'Best Quality' : formatId));
                createQueueItem(task.title || task.url, label, 'mp4', task.task_id);
            }
        } else {
            showAppDialog({ title: '启动失败', message: (res && res.error) ? res.error : '批量任务启动失败', type: 'error' });
        }
    } catch (e) {
        showAppDialog({ title: '错误', message: '批量下载错误: ' + e, type: 'error' });
    }
}

// --- Settings Modal Logic (新增) ---
const settingsModal = document.getElementById('settingsModal');
const settingsContent = settingsModal ? settingsModal.querySelector('div') : null;

async function showSettingsModal() {
    if (!settingsModal || !settingsContent) return;

    // 尝试从后端加载设置
    if (pywebviewReady && _hasApi()) {
        try {
            const raw = await window.pywebview.api.get_settings();
            const settings = _parseMaybeJson(raw);
            if (settings) {
                if (settings.download_path) document.getElementById('settingDownloadPath').value = settings.download_path;
                if (settings.proxy) document.getElementById('settingProxy').value = settings.proxy;

                // New setting: create_folder
                const createFolderEl = document.getElementById('settingCreateFolder');
                if (createFolderEl) {
                    createFolderEl.checked = !!settings.create_folder;
                }

                // New setting: convert_mp4
                const convertMp4El = document.getElementById('settingConvertMp4');
                if (convertMp4El) {
                    convertMp4El.checked = !!settings.convert_mp4;
                }


                if (settings.threads) {
                    document.getElementById('settingThreads').value = settings.threads;
                    document.getElementById('threadVal').innerText = settings.threads;
                }
            }
        } catch (e) {
            console.error("Load settings failed", e);
        }
    }

    await refreshCookieMappings();
    await loadVersionInfo();

    settingsModal.classList.remove('hidden');
    void settingsModal.offsetWidth;
    settingsModal.classList.remove('opacity-0');
    settingsContent.classList.remove('scale-95');
    settingsContent.classList.add('scale-100');
}

function closeSettingsModal() {
    if (!settingsModal || !settingsContent) return;
    settingsModal.classList.add('opacity-0');
    settingsContent.classList.remove('scale-100');
    settingsContent.classList.add('scale-95');
    setTimeout(() => settingsModal.classList.add('hidden'), 300);
}

async function selectDownloadFolder() {
    if (!pywebviewReady || !_hasApi()) return;
    try {
        const path = await window.pywebview.api.choose_directory();
        if (path) {
            document.getElementById('settingDownloadPath').value = path;
        }
    } catch (e) {
        console.error(e);
    }
}

async function saveSettings() {
    const path = document.getElementById('settingDownloadPath').value;
    const proxy = document.getElementById('settingProxy').value;
    const threads = document.getElementById('settingThreads').value;
    const createFolder = document.getElementById('settingCreateFolder').checked;
    const convertMp4 = document.getElementById('settingConvertMp4').checked;

    if (!pywebviewReady || !_hasApi()) {
        // 本地模拟保存
        closeSettingsModal();
        return;
    }

    try {
        const data = {
            download_path: path,
            proxy: proxy,
            threads: parseInt(threads),
            create_folder: createFolder,
            convert_mp4: convertMp4,
        };
        await window.pywebview.api.save_settings(data);
        closeSettingsModal();
        showAppDialog({ title: '成功', message: '设置已保存', type: 'success' });
    } catch (e) {
        showAppDialog({ title: '保存失败', message: String(e), type: 'error' });
    }
}

// --- 版本检查相关 ---
async function loadVersionInfo() {
    if (!pywebviewReady || !_hasApi()) return;

    try {
        const raw = await window.pywebview.api.get_version_info();
        const res = _parseMaybeJson(raw);
        if (res && res.success) {
            const ytdlpEl = document.getElementById('ytdlpVersionText');
            const ffmpegEl = document.getElementById('ffmpegVersionText');
            if (ytdlpEl) ytdlpEl.textContent = res.ytdlp_version || '未安装';
            if (ffmpegEl) ffmpegEl.textContent = res.ffmpeg_version || '未安装';
        }
    } catch (e) {
        console.error('加载版本信息失败:', e);
    }
}

async function checkForUpdates() {
    if (!pywebviewReady || !_hasApi()) return;

    const btn = document.getElementById('checkUpdateBtn');
    if (btn) {
        const original = btn.innerHTML;
        btn.innerHTML = '检查中...';
        btn.disabled = true;

        try {
            const raw = await window.pywebview.api.check_ytdlp_update();
            const res = _parseMaybeJson(raw);

            const container = document.getElementById('updateHintContainer');
            const hintText = document.getElementById('updateHintText');

            if (res && res.success) {
                if (res.update_available) {
                    if (container) container.classList.remove('hidden');
                    if (hintText) hintText.textContent = `发现新版本: ${res.latest_version} (当前: ${res.current_version})`;
                } else {
                    if (container) container.classList.add('hidden');
                    showAppDialog({ title: '已是最新', message: `yt - dlp 已是最新版本(${res.current_version})`, type: 'success' });
                }
            } else {
                showAppDialog({ title: '检查失败', message: res?.check_error || '无法检查更新', type: 'error' });
            }
        } catch (e) {
            showAppDialog({ title: '错误', message: String(e), type: 'error' });
        } finally {
            btn.innerHTML = original;
            btn.disabled = false;
        }
    }
}

async function openUpdatePage() {
    if (!pywebviewReady || !_hasApi()) return;
    try {
        await window.pywebview.api.open_ytdlp_release_page();
    } catch (e) {
        console.error('打开更新页面失败:', e);
    }
}
