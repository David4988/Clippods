import React, { useState, useRef, useEffect } from "react";
import { formatTime } from "../utils/format";

/**
 * Renders a single heuristic check with expandable actual-vs-threshold info
 */
export function HeuristicRow({ heuristic, points, maxPoints, passed, actual, threshold, detail }) {
  const [expanded, setExpanded] = useState(false);

  const getStatusColor = () => {
    if (passed) return "var(--success)";
    if (points > 0) return "var(--warning, #eab308)";
    return "var(--danger)";
  };

  const getStatusIcon = () => {
    if (passed) return "✓";
    return "✗";
  };

  return (
    <div className="heuristic-row" style={{ borderLeft: `4px solid ${getStatusColor()}` }}>
      <div className="heuristic-header" onClick={() => setExpanded(!expanded)}>
        <span className="heuristic-status" style={{ color: getStatusColor() }}>
          {getStatusIcon()}
        </span>
        <span className="heuristic-name">{heuristic}</span>
        <span className="heuristic-score">
          {points} / {maxPoints || 2} pts
        </span>
        <span className="heuristic-expand-icon">{expanded ? "▲" : "▼"}</span>
      </div>
      
      {expanded && (
        <div className="heuristic-details">
          <div className="heuristic-detail-item"><strong>Detail:</strong> {detail}</div>
          {actual !== undefined && (
            <div className="heuristic-detail-item"><strong>Actual:</strong> {String(actual)}</div>
          )}
          {threshold !== undefined && (
            <div className="heuristic-detail-item"><strong>Threshold:</strong> {String(threshold)}</div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Container for multiple HeuristicRows
 */
export function HeuristicBreakdown({ scoreBreakdown, totalScore }) {
  return (
    <div className="heuristic-breakdown-container">
      <div className="heuristic-breakdown-header">
        <h4>Heuristic Score Breakdown</h4>
        <div className="total-score-badge">
          Total Score: <strong>{totalScore} / 8</strong>
        </div>
      </div>
      <div className="heuristic-rows-list">
        {scoreBreakdown && scoreBreakdown.length > 0 ? (
          scoreBreakdown.map((hb, idx) => (
            <HeuristicRow
              key={idx}
              heuristic={hb.heuristic}
              points={hb.points}
              maxPoints={hb.max_points}
              passed={hb.passed}
              actual={hb.actual_seconds !== undefined ? `${hb.actual_seconds}s` : hb.actual}
              threshold={hb.threshold_seconds !== undefined ? `${hb.threshold_seconds}s` : hb.threshold}
              detail={hb.detail}
            />
          ))
        ) : (
          <div className="empty-message">No detailed heuristic breakdown available.</div>
        )}
      </div>
    </div>
  );
}

/**
 * Step-by-step trace of candidate decisions
 */
export function ExecutionTrace({ trace }) {
  return (
    <div className="execution-trace-container">
      <h4>Pipeline Execution Trace</h4>
      <div className="trace-timeline">
        {trace && trace.map((t, idx) => {
          const isFailure = t.result === "failed" || t.result === "rejected";
          const isSuccess = t.result === "passed" || t.result === "selected" || t.result === "kept";
          let badgeClass = "trace-badge-neutral";
          if (isSuccess) badgeClass = "trace-badge-success";
          if (isFailure) badgeClass = "trace-badge-danger";

          return (
            <div key={idx} className="trace-item">
              <div className="trace-marker"></div>
              <div className="trace-content">
                <div className="trace-header">
                  <span className="trace-step-name">{t.step.replace(/_/g, " ")}</span>
                  {t.result && (
                    <span className={`trace-badge ${badgeClass}`}>{t.result.toUpperCase()}</span>
                  )}
                </div>
                <div className="trace-detail">{t.detail}</div>
                {t.inspection && (
                  <div className="trace-inspection">
                    <strong>Inspection:</strong> {JSON.stringify(t.inspection)}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/**
 * Shared HTML5 video player with seek markers and custom controls
 */
export function VideoSeekPlayer({ src, start, end, runUuid, className = "" }) {
  const videoRef = useRef(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [videoError, setVideoError] = useState(false);

  useEffect(() => {
    // Reset state on source or range change
    setVideoError(false);
    if (videoRef.current) {
      videoRef.current.load();
      // Seek to 5 seconds before start to provide context
      const initialTime = Math.max(0, start - 5);
      videoRef.current.currentTime = initialTime;
      setCurrentTime(initialTime);
    }
  }, [src, start, end]);

  const handlePlayPause = () => {
    if (videoRef.current) {
      if (isPlaying) {
        videoRef.current.pause();
      } else {
        videoRef.current.play().catch(err => {
          console.error("Video playback error:", err);
          setVideoError(true);
        });
      }
    }
  };

  const seekTo = (time) => {
    if (videoRef.current) {
      videoRef.current.currentTime = time;
      setCurrentTime(time);
    }
  };

  const handleTimeUpdate = () => {
    if (videoRef.current) {
      setCurrentTime(videoRef.current.currentTime);
      // Auto pause at the end of the clip if playing original video for context
      if (end && videoRef.current.currentTime >= end + 2) {
        videoRef.current.pause();
      }
    }
  };

  const handleLoadedMetadata = () => {
    if (videoRef.current) {
      setDuration(videoRef.current.duration);
    }
  };

  const getTimelineProgress = () => {
    if (!duration) return 0;
    return (currentTime / duration) * 100;
  };

  return (
    <div className={`video-seek-player ${className}`}>
      {videoError ? (
        <div className="video-error-state">
          <p>Unable to load original video file.</p>
          <small>Make sure KEEP_ORIGINAL_FOR_DEBUG=true was set during processing, or that the video file exists in the outputs folder.</small>
        </div>
      ) : (
        <>
          <video
            ref={videoRef}
            src={src}
            onTimeUpdate={handleTimeUpdate}
            onLoadedMetadata={handleLoadedMetadata}
            onPlay={() => setIsPlaying(true)}
            onPause={() => setIsPlaying(false)}
            onError={() => setVideoError(true)}
            controls
            style={{ width: "100%", borderRadius: "var(--radius-sm)", maxHeight: "360px", background: "#000" }}
          />
          <div className="player-seek-panel">
            <div className="seek-labels">
              <button className="btn btn-sm" onClick={() => seekTo(Math.max(0, start - 5))}>
                Seek Context (Start - 5s): {formatTime(Math.max(0, start - 5))}
              </button>
              <button className="btn btn-sm btn-outline" style={{ borderColor: "var(--success)" }} onClick={() => seekTo(start)}>
                Seek to Clip Start: {formatTime(start)}
              </button>
              {end && (
                <button className="btn btn-sm btn-outline" style={{ borderColor: "var(--danger)" }} onClick={() => seekTo(end)}>
                  Seek to Clip End: {formatTime(end)}
                </button>
              )}
            </div>
            <div className="playback-info">
              <span>Current Time: <strong>{formatTime(currentTime)}</strong></span>
              {start !== undefined && (
                <span>Active Region: <strong style={{ color: "var(--accent-2)" }}>{formatTime(start)} - {formatTime(end)}</strong></span>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
