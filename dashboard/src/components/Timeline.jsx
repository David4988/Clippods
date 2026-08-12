import React, { useState } from "react";
import { formatTime } from "../utils/format";
import { VideoSeekPlayer } from "./common";
import { getVideoUrl } from "../api/analysis";

export default function InteractiveTimeline({ analysisData, onCompareClick }) {
  const [selectedItem, setSelectedItem] = useState(null);

  if (!analysisData) {
    return <div className="empty-message">No timeline data available. Please select a job.</div>;
  }

  const { meta, candidates, filtered_windows, final_clips } = analysisData;
  const duration = meta.video_duration_seconds;

  // Compile timeline segments
  const selectedRegions = final_clips || [];
  const rejectedCandidates = (candidates || []).filter(c => !c.selected);
  const filteredWindows = filtered_windows || [];

  const handleSelectClip = (clip) => {
    setSelectedItem({
      type: "clip",
      data: clip,
      start: clip.start,
      end: clip.end,
      title: `Selected Clip #${clip.clip_index + 1}`,
      badge: "SELECTED",
      badgeClass: "badge-success"
    });
  };

  const handleSelectCandidate = (candidate) => {
    setSelectedItem({
      type: "candidate",
      data: candidate,
      start: candidate.window_start,
      end: candidate.window_end,
      title: `Candidate Window #${candidate.id} (${candidate.selected ? "Selected" : "Rejected"})`,
      badge: candidate.selected ? "SELECTED" : "REJECTED",
      badgeClass: candidate.selected ? "badge-success" : "badge-danger"
    });
  };

  const handleSelectFiltered = (fw) => {
    setSelectedItem({
      type: "filtered",
      data: fw,
      start: fw.window_start,
      end: fw.window_end || fw.window_start + 15.0, // default display size
      title: `Filtered Window (Reason: ${fw.reason})`,
      badge: "FILTERED",
      badgeClass: "badge-neutral"
    });
  };

  return (
    <div className="interactive-timeline-container">
      <div className="card">
        <div className="card-header">
          <h3>Interactive Algorithm Debugger Timeline</h3>
          <p className="subtitle">Visual trace of all heuristics decisions. Hover/Click elements to explain selections.</p>
        </div>
        <div className="card-body">
          <div className="timeline-legend">
            <div className="legend-item">
              <span className="legend-box legend-selected"></span>
              Selected Clips ({selectedRegions.length})
            </div>
            <div className="legend-item">
              <span className="legend-dot legend-rejected"></span>
              Rejected Candidates ({rejectedCandidates.length})
            </div>
            <div className="legend-item">
              <span className="legend-box legend-filtered"></span>
              Filtered Windows ({filteredWindows.length})
            </div>
          </div>

          {/* Interactive Timeline Bar */}
          <div className="timeline-bar-wrapper">
            <div className="timeline-time-labels">
              <span>0:00</span>
              <span>{formatTime(duration / 2)}</span>
              <span>{formatTime(duration)}</span>
            </div>
            <div className="timeline-bar">
              {/* Filtered windows blocks */}
              {filteredWindows.map((fw, idx) => {
                const startPercent = (fw.window_start / duration) * 100;
                const end = fw.window_end || fw.window_start + 15.0;
                const widthPercent = ((end - fw.window_start) / duration) * 100;

                return (
                  <div
                    key={`fw-${idx}`}
                    className="timeline-block filtered-block"
                    style={{ left: `${startPercent}%`, width: `${widthPercent}%` }}
                    onClick={() => handleSelectFiltered(fw)}
                    title={`Filtered: ${fw.reason}`}
                  />
                );
              })}

              {/* Selected clips blocks */}
              {selectedRegions.map((clip, idx) => {
                const startPercent = (clip.start / duration) * 100;
                const widthPercent = ((clip.end - clip.start) / duration) * 100;

                return (
                  <div
                    key={`clip-${idx}`}
                    className="timeline-block selected-block"
                    style={{ left: `${startPercent}%`, width: `${widthPercent}%` }}
                    onClick={() => handleSelectClip(clip)}
                    title={`Selected Clip ${idx + 1}`}
                  />
                );
              })}

              {/* Rejected candidates dots */}
              {rejectedCandidates.map((cand, idx) => {
                const positionPercent = (cand.window_start / duration) * 100;

                return (
                  <div
                    key={`cand-${idx}`}
                    className="timeline-dot rejected-dot"
                    style={{ left: `${positionPercent}%` }}
                    onClick={() => handleSelectCandidate(cand)}
                    title={`Candidate: Score ${cand.metrics.raw_score || "N/A"}`}
                  />
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Details & Playback Panel */}
      {selectedItem ? (
        <div className="card timeline-detail-card">
          <div className="card-header timeline-detail-header">
            <div className="header-title-wrapper">
              <span className={`badge ${selectedItem.badgeClass}`}>{selectedItem.badge}</span>
              <h3>{selectedItem.title}</h3>
            </div>
            <span className="timestamp-range">
              Range: {formatTime(selectedItem.start)} – {formatTime(selectedItem.end)} ({Math.round(selectedItem.end - selectedItem.start)}s)
            </span>
          </div>
          <div className="card-body grid-2col">
            <div className="detail-meta-panel">
              {selectedItem.type === "clip" && (
                <div className="explanation-section">
                  <h4>Why Selected?</h4>
                  <p>{selectedItem.data.selection_explanation.reason}</p>
                  <ul>
                    {selectedItem.data.selection_explanation.key_strengths.map((str, idx) => (
                      <li key={idx} className="success-bullet">{str}</li>
                    ))}
                  </ul>
                  {selectedItem.data.selection_explanation.next_best_alternative && (
                    <div className="next-alternative-alert">
                      <p>
                        This candidate beat <strong>Candidate #{selectedItem.data.selection_explanation.next_best_alternative.candidate_id}</strong> (Rank #2) by a margin of <strong>{Math.abs(selectedItem.data.selection_explanation.next_best_alternative.score_delta)}</strong>.
                      </p>
                      <button className="btn btn-sm btn-outline" onClick={() => onCompareClick(selectedItem.data.candidate_id, selectedItem.data.selection_explanation.next_best_alternative.candidate_id)}>
                        Compare Candidates Side-by-Side
                      </button>
                    </div>
                  )}
                </div>
              )}

              {selectedItem.type === "candidate" && (
                <div className="explanation-section">
                  <h4>Candidate Heuristics Summary</h4>
                  <div className="metrics-summary-grid">
                    <div className="metric-box">
                      <span className="metric-label">Score</span>
                      <span className="metric-val">{selectedItem.data.metrics?.raw_score || "N/A"}</span>
                    </div>
                    <div className="metric-box">
                      <span className="metric-label">Word Density</span>
                      <span className="metric-val">{selectedItem.data.metrics?.word_density || "N/A"}</span>
                    </div>
                    <div className="metric-box">
                      <span className="metric-label">Speech Ratio</span>
                      <span className="metric-val">{selectedItem.data.metrics?.speech_ratio || "N/A"}</span>
                    </div>
                    <div className="metric-box">
                      <span className="metric-label">Stop Score</span>
                      <span className="metric-val">{selectedItem.data.end_analysis?.total_score || "N/A"} / 8</span>
                    </div>
                  </div>
                  {selectedItem.data.rejection_reason && (
                    <div className="rejection-reason-box">
                      <strong>Rejection Reason:</strong> {selectedItem.data.rejection_reason.replace(/_/g, " ").toUpperCase()}
                      <p className="detail-para">
                        {selectedItem.data.trace[selectedItem.data.trace.length - 1]?.detail || ""}
                      </p>
                    </div>
                  )}
                  <button className="btn btn-sm btn-outline" onClick={() => {
                    // find a clip to compare with
                    const bestClipId = final_clips[0]?.candidate_id;
                    if (bestClipId !== undefined) {
                      onCompareClick(selectedItem.data.id, bestClipId);
                    }
                  }}>
                    Compare with Clip #1
                  </button>
                </div>
              )}

              {selectedItem.type === "filtered" && (
                <div className="explanation-section">
                  <h4>Filtered Out Prior to Candidacy</h4>
                  <div className="filter-detail-box">
                    <p><strong>Reason:</strong> <span className="text-danger">{selectedItem.data.reason.replace(/_/g, " ").toUpperCase()}</span></p>
                    <p className="detail-para">{selectedItem.data.detail}</p>
                    {selectedItem.data.inspection && (
                      <div className="trace-inspection">
                        <h5>Energy Filter Inspection</h5>
                        <p>Speech Duration: {selectedItem.data.inspection.speech_duration}s</p>
                        <p>Total Duration: {selectedItem.data.inspection.clip_duration}s</p>
                        <p>Speech Ratio: {selectedItem.data.inspection.actual_ratio} (Threshold: {selectedItem.data.inspection.threshold})</p>
                      </div>
                    )}
                  </div>
                </div>
              )}

              <div className="transcript-box">
                <h4>Transcript Preview</h4>
                <p className="transcript-preview-text">
                  "{selectedItem.data.transcript_preview || selectedItem.data.start_analysis?.transcript_preview || "No preview text available."}"
                </p>
              </div>
            </div>

            <div className="detail-video-panel">
              <h4>Play Original Video Context</h4>
              <VideoSeekPlayer
                src={getVideoUrl(meta.run_uuid)}
                start={selectedItem.start}
                end={selectedItem.end}
                runUuid={meta.run_uuid}
              />
            </div>
          </div>
        </div>
      ) : (
        <div className="card empty-timeline-detail">
          <p>Click on any Timeline segment or marker above to inspect its metrics, heuristic scores, rejection reason, and play the original video context.</p>
        </div>
      )}
    </div>
  );
}
