// ===== ClipPods — App UI Script =====
// Handles: upload, polling, clip display

const API_BASE = 'http://localhost:8000';
const POLL_INTERVAL_MS = 3000;

// --- DOM Elements ---
const fileInput = document.getElementById('file-input');
const uploadBtn = document.getElementById('upload-btn');
const uploadStatus = document.getElementById('upload-status');
const uploadSection = document.getElementById('upload-section');
const statusSection = document.getElementById('status-section');
const progressBar = document.getElementById('progress-bar');
const statusText = document.getElementById('status-text');
const resultsSection = document.getElementById('results-section');
const clipsContainer = document.getElementById('clips-container');

// --- State ---
let currentJobId = null;
let pollTimer = null;

// --- Upload ---
fileInput.addEventListener('change', () => {
    uploadBtn.disabled = !fileInput.files.length;
});

uploadBtn.addEventListener('click', async () => {
    const file = fileInput.files[0];
    if (!file) return;

    uploadBtn.disabled = true;
    uploadStatus.textContent = 'Uploading...';

    try {
        const formData = new FormData();
        formData.append('file', file);

        const res = await fetch(`${API_BASE}/jobs`, {
            method: 'POST',
            body: formData,
        });
        const data = await res.json();
        currentJobId = data.job_id;

        uploadSection.style.display = 'none';
        statusSection.style.display = 'block';
        startPolling(currentJobId);
    } catch (err) {
        uploadStatus.textContent = `Upload failed: ${err.message}`;
        uploadBtn.disabled = false;
    }
});

// --- Polling ---
function startPolling(jobId) {
    pollTimer = setInterval(() => pollStatus(jobId), POLL_INTERVAL_MS);
}

async function pollStatus(jobId) {
    try {
        const res = await fetch(`${API_BASE}/jobs/${jobId}`);
        const data = await res.json();

        progressBar.style.width = `${data.progress || 0}%`;
        statusText.textContent = formatStatus(data.status);

        if (data.status === 'completed') {
            clearInterval(pollTimer);
            await loadClips(jobId);
        } else if (data.status === 'failed') {
            clearInterval(pollTimer);
            statusText.textContent = `Failed: ${data.error || 'Unknown error'}`;
        }
    } catch (err) {
        statusText.textContent = `Polling error: ${err.message}`;
    }
}

function formatStatus(status) {
    const map = {
        queued: 'Queued...',
        transcribing: 'Transcribing audio...',
        chunking: 'Finding highlight segments...',
        scoring: 'Scoring highlights...',
        extracting: 'Extracting clips...',
        completed: 'Done!',
        failed: 'Processing failed.',
    };
    return map[status] || status;
}

// --- Display Clips ---
async function loadClips(jobId) {
    try {
        const res = await fetch(`${API_BASE}/jobs/${jobId}/clips`);
        const data = await res.json();

        statusSection.style.display = 'none';
        resultsSection.style.display = 'block';
        clipsContainer.innerHTML = '';

        data.clips.forEach((clip) => {
            const card = document.createElement('div');
            card.className = 'clip-card';
            card.innerHTML = `
                <div class="clip-header">
                    <span class="clip-rank">#${clip.rank}</span>
                    <span class="clip-score">Score: ${(clip.score * 100).toFixed(0)}%</span>
                </div>
                <p class="clip-transcript">${clip.transcript}</p>
                <audio class="clip-audio" controls src="${API_BASE}${clip.audio_url}"></audio>
                <a class="clip-download" href="${API_BASE}${clip.audio_url}" download>Download</a>
            `;
            clipsContainer.appendChild(card);
        });
    } catch (err) {
        statusText.textContent = `Failed to load clips: ${err.message}`;
    }
}
