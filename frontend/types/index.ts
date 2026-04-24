export interface VideoData {
  videoId: string;
  sourceType: 'upload' | 'youtube';
  originalPath: string;
  duration: number;
  width?: number;
  height?: number;
  suggestions?: any[];
}

export interface JobData {
  jobId: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number;
  outputPath?: string;
  errorMessage?: string;
  downloadUrl?: string;
}

export interface ApiResponse<T> {
  success: boolean;
  message?: string;
  data?: T;
}
