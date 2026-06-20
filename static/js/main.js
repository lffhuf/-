// 分享文件功能
function shareFile(fileId, displayName) {
    // 弹出分享弹窗
    const modal = document.getElementById('share-modal');
    modal.style.display = 'flex';
    document.getElementById('share-url').value = '';
    document.getElementById('share-password').value = '';
    
    // 设置默认文件名
    const renameInput = document.getElementById('share-rename');
    renameInput.value = displayName || '';
    renameInput.dataset.fileId = fileId;
}

function closeModal() {
    document.getElementById('share-modal').style.display = 'none';
}

function doShare() {
    const renameInput = document.getElementById('share-rename');
    const fileId = renameInput.dataset.fileId;
    const passwordInput = document.getElementById('share-password');
    const urlInput = document.getElementById('share-url');
    
    if (!fileId) {
        alert('❌ 文件ID错误');
        return;
    }
    
    // 生成中提示
    urlInput.placeholder = '⏳ 生成中...';
    urlInput.value = '';
    
    const data = {
        rename: renameInput.value.trim(),
        password: passwordInput.value.trim()
    };
    
    fetch(`/api/share/${fileId}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    })
    .then(res => res.json())
    .then(result => {
        if (result.share_url) {
            urlInput.value = result.share_url;
            alert('✅ 分享链接已生成！');
        } else {
            alert('❌ ' + (result.error || '分享失败'));
            urlInput.placeholder = '点击生成链接按钮';
        }
    })
    .catch(err => {
        console.error('Share error:', err);
        alert('❌ 分享失败：' + err.message);
        urlInput.placeholder = '点击生成链接按钮';
    });
}

function copyShareUrl() {
    const urlInput = document.getElementById('share-url');
    if (!urlInput.value) {
        alert('⚠️ 请先点击"生成分享链接"');
        return;
    }
    
    // 尝试使用现代Clipboard API
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(urlInput.value).then(() => {
            alert('✅ 链接已复制到剪贴板');
        }).catch(() => {
            fallbackCopy(urlInput);
        });
    } else {
        fallbackCopy(urlInput);
    }
}

function fallbackCopy(input) {
    input.select();
    input.setSelectionRange(0, 99999); // 兼容移动端
    try {
        document.execCommand('copy');
        alert('✅ 链接已复制到剪贴板');
    } catch (err) {
        alert('❌ 复制失败，请手动复制');
    }
}
