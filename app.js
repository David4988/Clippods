/**
 * app.js – App dashboard (app.html) frontend logic
 * Handles file selection, upload, status polling, and clip display.
 */

const uploadBox    = document.getElementById('app-upload-box');
const uploadText   = document.getElementById('app-upload-text');
const fileInput    = document.getElementById('app-file-input');
const uploadBtn    = document.getElementById('app-upload-btn');
const statusPanel  = document.getElementById('app-status');
const statusMsg    = document.getElementById('app-status-msg');
const jobIdLabel   = document.getElementById('app-job-id');
const resultsPanel = document.getElementById('app-results');
const clipsGrid    = document.getElementById('app-clips-grid');

let selectedFile   = null;
let activeJobId    = null;
let pollingInterval= null;

const STATUS_MESSAGES = {
    queued:       'Job queued – waiting to start...',
    chunking:     'Splitting audio into chunks...',
    transcribing: 'Transcribing & translating regional audio...',
    segmenting:   'Segmenting transcript...',
    highlighting: 'Scoring highlights with AI...',
    rendering:    'Rendering clips with FFmpeg...',
    completed:    'Done! Clips are ready 🎉',
    failed:       '⚠️ Processing failed.',
};

// ── File selection ────────────────────────────────────────────────────────────
fileInput.addEventListener('change', () => {
    selectedFile = fileInput.files[0];
    if (selectedFile) {
        uploadText.innerText = `📄 ${selectedFile.name}`;
        uploadBtn.disabled = false;
    }
});

uploadBox.addEventListener('dragover', (e) => { e.preventDefault(); uploadBox.classList.add('drag-over'); });
uploadBox.addEventListener('dragleave', () => uploadBox.classList.remove('drag-over'));
uploadBox.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadBox.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) {
        const dt = new DataTransfer(); dt.items.add(file);
        fileInput.files = dt.files;
        selectedFile = file;
        uploadText.innerText = `📄 ${file.name}`;
        uploadBtn.disabled = false;
    }
});

// ── Upload & process ──────────────────────────────────────────────────────────
uploadBtn.addEventListener('click', async () => {
    if (!selectedFile) return;

    uploadBtn.disabled = true;
    statusPanel.style.display  = 'block';
    resultsPanel.style.display = 'none';
    statusMsg.innerText = 'Uploading file...';

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
        const res  = await fetch('/api/upload', { method: 'POST', body: formData });
        const data = await res.json();
        activeJobId = data.job_id;
        jobIdLabel.innerText = `Job ID: ${activeJobId}`;
        beginPolling();
    } catch (err) {
        console.error(err);
        alert('Upload failed. Is the backend server running?');
        uploadBtn.disabled = false;
        statusPanel.style.display = 'none';
    }
});

// ── Polling ───────────────────────────────────────────────────────────────────
function beginPolling() {
    pollingInterval = setInterval(async () => {
        if (!activeJobId) return;
        try {
            const res  = await fetch(`/api/status/${activeJobId}`);
            const data = await res.json();
            statusMsg.innerText = STATUS_MESSAGES[data.status] || `Status: ${data.status}`;

            if (data.status === 'completed') {
                clearInterval(pollingInterval);
                showResults(data.clips || []);
            } else if (data.status === 'failed') {
                clearInterval(pollingInterval);
                alert(`Error: ${data.error || 'Unknown pipeline failure'}`);
                uploadBtn.disabled = false;
            }
        } catch (err) {
            console.error('Poll error:', err);
        }
    }, 3000);
}

// ── Results ───────────────────────────────────────────────────────────────────
function showResults(clips) {
    statusPanel.style.display  = 'none';
    resultsPanel.style.display = 'block';
    clipsGrid.innerHTML = '';
    uploadBtn.disabled = false;

    if (!clips.length) {
        clipsGrid.innerHTML = `<p style="color:#a0aec0;grid-column:1/-1;">No clips generated.</p>`;
        return;
    }

    clips.forEach((clip, i) => {
        const card = document.createElement('div');
        card.className = 'clip-card';
        const filename = clip.file_path ? clip.file_path.split(/[\\/]/).pop() : `clip_${i}.mp4`;
        card.innerHTML = `
            <div class="clip-score">🔥 Score: ${typeof clip.score === 'number' ? clip.score.toFixed(2) : 'N/A'}</div>
            <h3 class="clip-title">Clip #${i + 1}</h3>
            <p class="clip-time">${fmt(clip.start_time)} – ${fmt(clip.end_time)}</p>
            <a href="/api/clips/${activeJobId}/${filename}" download="${filename}" class="download-btn">⬇ Download MP4</a>
        `;
        clipsGrid.appendChild(card);
    });
}

function fmt(s) {
    if (typeof s !== 'number') return '--:--';
    return `${String(Math.floor(s/60)).padStart(2,'0')}:${String(Math.floor(s%60)).padStart(2,'0')}`;
}
