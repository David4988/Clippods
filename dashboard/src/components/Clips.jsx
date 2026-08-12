import React, { useState } from "react";
import { formatTime } from "../utils/format";
import { HeuristicBreakdown, VideoSeekPlayer } from "./common";
import { getClipUrl, getVideoUrl } from "../api/analysis";

export default function FinalClips({ analysisData, onCompareClick }) {
  if (!analysisData) {
    return <div className="empty-message">No clips data available. Please select a job.</div>;
  }

  const { final_clips, meta, candidates } = analysisData;

  return (
    <div className="final-clips-tab-container">
      <div className="tab-header-description">
        <h3>Final Selected Clips ({final_clips?.length || 0})</h3>
        <p className="subtitle">These are the winning highlight clips produced by the pipeline. Inspect their details below.</p>
      </div>

      <div className="clips-list-grid">
        {final_clips && final_clips.map((clip, idx) => {
          // Find corresponding candidate for full score breakdown
          const cand = candidates?.find(c => c.id === clip.candidate_id);

          return (
            <ClipCard
              key={idx}
              clip={clip}
              candidate={cand}
              runUuid={meta.run_uuid}
              onCompareClick={onCompareClick}
            />
          );
        })}
      </div>
    </div>
  );
}

function ClipCard({ clip, candidate, runUuid, onCompareClick }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [showOriginalPlayer, setShowOriginalPlayer] = useState(false);

  const scoreBreakdown = candidate?.end_analysis?.score_breakdown || [];
  const totalScore = candidate?.end_analysis?.total_score || clip.end_score || 0;

  return (
    <div className="card clip-card">
      <div className="clip-card-header" onClick={() => setIsExpanded(!isExpanded)}>
        <div className="clip-header-left">
          <span className="clip-index-badge">Clip #{clip.clip_index + 1}</span>
          <h4 className="clip-title">{clip.transcript_preview ? `"${clip.transcript_preview.substring(0, 50)}..."` : `Highlight Clip ${clip.clip_index + 1}`}</h4>
        </div>
        <div className="clip-header-right">
          <span className="clip-duration-badge">{clip.duration}s</span>
          <span className="viral-score-badge">Viral Score: <strong>{clip.viral_score}%</strong></span>
          <span className="expand-indicator">{isExpanded ? "▲" : "▼"}</span>
        </div>
      </div>

      {isExpanded && (
        <div className="clip-card-expanded-body">
          <div className="grid-2col">
            {/* Playback column */}
            <div className="clip-playback-column">
              <div className="playback-toggle-tabs">
                <button
                  className={`btn btn-sm ${!showOriginalPlayer ? "btn-primary" : "btn-outline"}`}
                  onClick={() => setShowOriginalPlayer(false)}
                >
                  Play Generated Clip
                </button>
                <button
                  className={`btn btn-sm ${showOriginalPlayer ? "btn-primary" : "btn-outline"}`}
                  onClick={() => setShowOriginalPlayer(true)}
                >
                  Play Original Video Context
                </button>
              </div>

              <div className="video-player-container">
                {showOriginalPlayer ? (
                  <VideoSeekPlayer
                    src={getVideoUrl(runUuid)}
                    start={clip.start}
                    end={clip.end}
                    runUuid={runUuid}
                  />
                ) : (
                  <div className="generated-clip-player">
                    <video
                      src={getClipUrl(clip.filename)}
                      controls
                      style={{ width: "100%", borderRadius: "var(--radius-sm)", maxHeight: "280px", background: "#000" }}
                    />
                    <div className="clip-source-info">
                      Playing file: <code>{clip.filename}</code>
                    </div>
                  </div>
                )}
              </div>

              <div className="clip-start-end-reasons">
                <div className="reasoning-box start-reasoning">
                  <h5>Start Point Selection Reasons</h5>
                  <ul>
                    {clip.start_reasoning && clip.start_reasoning.length > 0 ? (
                      clip.start_reasoning.map((r, idx) => (
                        <li key={idx} className="success-bullet">{r}</li>
                      ))
                    ) : (
                      <li>Clean window boundaries</li>
                    )}
                  </ul>
                </div>
                <div className="reasoning-box end-reasoning">
                  <h5>End Point Selection Reasons</h5>
                  <ul>
                    {clip.end_reasoning && clip.end_reasoning.length > 0 ? (
                      clip.end_reasoning.map((r, idx) => (
                        <li key={idx} className="success-bullet">{r}</li>
                      ))
                    ) : (
                      <li>Satisfied duration heuristics</li>
                    )}
                  </ul>
                </div>
              </div>
            </div>

            {/* Explanation & Heuristics column */}
            <div className="clip-explanation-column">
              <div className="explanation-section">
                <h4>Selection Explanation</h4>
                <p><strong>Rank:</strong> Candidate #{clip.candidate_id} was ranked #{clip.selection_explanation.rank + 1} overall.</p>
                <p><strong>Reason:</strong> {clip.selection_explanation.reason}.</p>
                <div className="strengths-box">
                  <h5>Key Strengths:</h5>
                  <ul>
                    {clip.selection_explanation.key_strengths?.map((str, idx) => (
                      <li key={idx} className="success-bullet">{str}</li>
                    ))}
                  </ul>
                </div>

                {clip.selection_explanation.next_best_alternative && (
                  <div className="alternative-alert">
                    <p>
                      <strong>Marginal Win:</strong> Beat <strong>Candidate #{clip.selection_explanation.next_best_alternative.candidate_id}</strong> (Rank #2) by a margin of <strong>{Math.abs(clip.selection_explanation.next_best_alternative.score_delta)}</strong> in word density.
                    </p>
                    <button
                      className="btn btn-sm btn-outline"
                      onClick={() => onCompareClick(clip.candidate_id, clip.selection_explanation.next_best_alternative.candidate_id)}
                    >
                      Compare with Next Best Alternative
                    </button>
                  </div>
                )}
              </div>

              <div className="heuristics-section">
                <HeuristicBreakdown
                  scoreBreakdown={scoreBreakdown}
                  totalScore={totalScore}
                />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
