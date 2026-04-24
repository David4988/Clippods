import { ApiResponse, JobData, VideoData } from '@/types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:4000/api';

const DEFAULT_TIMEOUT_MS = 30_000;
const UPLOAD_TIMEOUT_MS = 600_000; // 10 minutes for uploads
const YOUTUBE_TIMEOUT_MS = 1800_000; // 30 minutes for YouTube imports

import { auth } from './firebase';
import { signInWithEmailAndPassword, createUserWithEmailAndPassword, signOut, GoogleAuthProvider, signInWithPopup } from 'firebase/auth';

export function setToken(token: string) {
  if (typeof window !== 'undefined') {
    localStorage.setItem('clippods_token', token);
  }
}

export function getToken() {
  if (typeof window !== 'undefined') {
    return localStorage.getItem('clippods_token');
  }
  return null;
}

export function logout() {
  if (typeof window !== 'undefined') {
    localStorage.removeItem('clippods_token');
    signOut(auth).catch(() => {});
  }
}

function getAuthHeaders(isFormData = false) {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;
  if (!isFormData) headers['Content-Type'] = 'application/json';
  return headers;
}

/**
 * Safe fetch wrapper with timeout and response validation.
 */
async function safeFetch(url: string, options: RequestInit & { timeoutMs?: number } = {}): Promise<Response> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...fetchOptions } = options;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(url, { ...fetchOptions, signal: controller.signal });
    return res;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Parse JSON response safely, returning error shape on failure.
 */
async function parseJsonResponse<T>(res: Response): Promise<ApiResponse<T>> {
  if (!res.ok && res.status >= 500) {
    return { success: false, message: `Server error (${res.status})` };
  }
  try {
    return await res.json();
  } catch {
    return { success: false, message: 'Invalid server response' };
  }
}

// ─── Auth ──────────────────────────────────────────────────
export async function loginApi(email: string, password: string): Promise<ApiResponse<any>> {
  try {
    const cred = await signInWithEmailAndPassword(auth, email, password);
    const token = await cred.user.getIdToken();
    return { success: true, message: 'Login successful', data: { token } };
  } catch (err: any) {
    return { success: false, message: err.message || 'Login failed' };
  }
}

export async function signupApi(email: string, password: string, workspaceName: string): Promise<ApiResponse<any>> {
  try {
    const cred = await createUserWithEmailAndPassword(auth, email, password);
    const token = await cred.user.getIdToken();
    
    await safeFetch(`${API_BASE}/auth/sync`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ workspaceName }),
    });

    return { success: true, message: 'Signup successful', data: { token } };
  } catch (err: any) {
    return { success: false, message: err.message || 'Signup failed' };
  }
}

export async function signInWithGoogleApi(): Promise<ApiResponse<any>> {
  try {
    const provider = new GoogleAuthProvider();
    const cred = await signInWithPopup(auth, provider);
    const token = await cred.user.getIdToken();
    
    await safeFetch(`${API_BASE}/auth/sync`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ workspaceName: cred.user.displayName || 'My Workspace' }),
    });

    return { success: true, message: 'Google Sign-In successful', data: { token } };
  } catch (err: any) {
    return { success: false, message: err.message || 'Google Sign-In failed' };
  }
}

export async function getCurrentUserApi(): Promise<ApiResponse<any>> {
  const res = await safeFetch(`${API_BASE}/auth/me`, {
    headers: getAuthHeaders(),
  });
  return parseJsonResponse(res);
}

// ─── Video Operations ──────────────────────────────────────
export async function uploadVideo(file: File): Promise<ApiResponse<VideoData>> {
  const formData = new FormData();
  formData.append('file', file);
  const res = await safeFetch(`${API_BASE}/upload`, {
    method: 'POST',
    headers: getAuthHeaders(true),
    body: formData,
    timeoutMs: UPLOAD_TIMEOUT_MS,
  });
  return parseJsonResponse(res);
}

export async function importYouTube(url: string): Promise<ApiResponse<VideoData>> {
  const res = await safeFetch(`${API_BASE}/youtube/import`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ url }),
    timeoutMs: YOUTUBE_TIMEOUT_MS,
  });
  return parseJsonResponse(res);
}

export async function createClipJob(payload: {
  videoId: string;
  startTime?: number;
  endTime?: number;
  mode: string;
  segments?: any[];
  quality?: string;
  ratio?: string;
  format?: string;
}): Promise<ApiResponse<{ jobIds: string[]; status: string }>> {
  const res = await safeFetch(`${API_BASE}/clip/create`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(payload),
  });
  return parseJsonResponse(res);
}

export async function getJobStatus(jobId: string): Promise<ApiResponse<JobData>> {
  const res = await safeFetch(`${API_BASE}/job/${jobId}/status`, {
    headers: getAuthHeaders(),
  });
  return parseJsonResponse(res);
}

export async function getVideoInfo(videoId: string): Promise<ApiResponse<VideoData & { suggestions?: any[] }>> {
  const res = await safeFetch(`${API_BASE}/video/${videoId}`, {
    method: 'GET',
    headers: getAuthHeaders(),
  });
  return parseJsonResponse(res);
}

export async function submitWaitlist(payload: { email: string; role: string; platform: string }): Promise<ApiResponse<any>> {
  const res = await safeFetch(`${API_BASE}/waitlist`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseJsonResponse(res);
}
