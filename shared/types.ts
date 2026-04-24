export interface VideoRecord {
  id: string;
  sourceType: 'upload' | 'youtube';
  originalName?: string;
  originalPath: string;
  duration: number;
  width?: number;
  height?: number;
  createdAt: string;
}

export interface ClipJobRecord {
  id: string;
  videoId: string;
  startTime: number;
  endTime: number;
  mode: 'fast' | 'accurate';
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number;
  inputPath: string;
  outputPath?: string;
  errorMessage?: string;
  createdAt: string;
  updatedAt: string;
}

export interface WaitlistRecord {
  id: number;
  email: string;
  role: string;
  platform: string;
  createdAt: string;
}
