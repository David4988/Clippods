'use client';
import { useMemo } from 'react';

interface Props {
  duration: number;
  startTime: number;
  endTime: number;
  onStartChange: (val: number) => void;
  onEndChange: (val: number) => void;
}

export default function TimelineEditor({ duration, startTime, endTime, onStartChange, onEndChange }: Props) {
  // Generate stable waveform bar heights (don't re-randomize on every render)
  const waveformBars = useMemo(() => {
    return Array.from({ length: 60 }, () => Math.random() * 70 + 20);
  }, []);

  const handleMinChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = Number(e.target.value);
    if (val < endTime - 0.1) onStartChange(val);
  };

  const handleMaxChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = Number(e.target.value);
    if (val > startTime + 0.1) onEndChange(val);
  };

  const selectionLeft = duration > 0 ? (startTime / duration) * 100 : 0;
  const selectionWidth = duration > 0 ? ((endTime - startTime) / duration) * 100 : 0;

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-muted">0:00</span>
        <span className="text-xs font-medium text-white/80">Timeline</span>
        <span className="text-xs text-muted">{formatTime(duration)}</span>
      </div>

      <div className="w-full relative h-12 sm:h-14">
        {/* Waveform background */}
        <div className="absolute inset-0 bg-black border border-border rounded-lg overflow-hidden">
          <div className="w-full h-full flex items-center justify-around px-1">
            {waveformBars.map((h, i) => (
              <div
                key={i}
                className="w-[2px] bg-white/15 rounded-full flex-shrink-0 transition-colors duration-200"
                style={{ height: `${h}%` }}
              />
            ))}
          </div>
        </div>

        {/* Selected region highlight */}
        {duration > 0 && (
          <div
            className="absolute top-0 bottom-0 bg-white/15 border-l-2 border-r-2 border-white rounded-sm pointer-events-none transition-all duration-100"
            style={{
              left: `${selectionLeft}%`,
              width: `${selectionWidth}%`,
            }}
          />
        )}

        {/* Start handle slider */}
        <input
          type="range"
          min={0}
          max={duration || 100}
          step={0.1}
          value={startTime}
          onChange={handleMinChange}
          className="absolute inset-0 w-full h-full timeline-range z-10 opacity-100"
        />

        {/* End handle slider */}
        <input
          type="range"
          min={0}
          max={duration || 100}
          step={0.1}
          value={endTime}
          onChange={handleMaxChange}
          className="absolute inset-0 w-full h-full timeline-range z-20 opacity-100"
        />
      </div>

      {/* Time labels under selection */}
      <div className="flex justify-between mt-2 text-xs text-muted">
        <span>Start: {formatTime(startTime)}</span>
        <span className="font-medium text-white">Duration: {formatTime(endTime - startTime)}</span>
        <span>End: {formatTime(endTime)}</span>
      </div>
    </div>
  );
}

function formatTime(seconds: number): string {
  if (!seconds || seconds < 0) return '0:00';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) {
    return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  }
  return `${m}:${s.toString().padStart(2, '0')}`;
}
