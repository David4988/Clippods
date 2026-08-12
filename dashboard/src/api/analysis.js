const getApiBase = () => {
  if (typeof window !== "undefined") {
    // If running on Vite dev server, point to local backend
    if (window.location.port === "5173" || window.location.hostname === "localhost") {
      return "http://127.0.0.1:8000";
    }
    return window.location.origin;
  }
  return "";
};

export const API_BASE = getApiBase();

export async function fetchAnalysisJobs() {
  const response = await fetch(`${API_BASE}/dev/analysis/jobs`);
  if (!response.ok) {
    throw new Error("Failed to fetch jobs list");
  }
  return response.json();
}

export async function fetchAnalysisDetails(runUuid) {
  const response = await fetch(`${API_BASE}/dev/analysis/${runUuid}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch analysis details for run ${runUuid}`);
  }
  return response.json();
}

export async function fetchAnalysisSummary(runUuid) {
  const response = await fetch(`${API_BASE}/dev/analysis/${runUuid}/summary`);
  if (!response.ok) {
    throw new Error(`Failed to fetch analysis summary for run ${runUuid}`);
  }
  return response.json();
}

export function getVideoUrl(runUuid) {
  return `${API_BASE}/dev/video/${runUuid}`;
}

export function getClipUrl(filename) {
  return `${API_BASE}/clips/${filename}`;
}
