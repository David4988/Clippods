import React, { useState, useRef } from "react";
import { formatTime } from "../utils/format";
import { VideoSeekPlayer } from "./common";
import { getVideoUrl } from "../api/analysis";

export default function TranscriptInspector({ analysisData }) {
  const [videoSeekTime, setVideoSeekTime] = useState(0);
  const [videoEndTime, setVideoEndTime] = useState(null);
  const [showCandidates, setShowCandidates] = useState(false);
  const playerRef = useRef(null);

  if (!analysisData) {
    return <div className="empty-message">No transcript data available. Please select a job.</div>;
  }

  const { transcript, final_clips, candidates, meta } = analysisData;

  const handleLineClick = (start, end) => {
    setVideoSeekTime(start);
    setVideoEndTime(end);
  };

  // Helper to determine if a transcript segment falls inside a clip or candidate
  const getLineStatus = (start, end) => {
    // Check clips first
    const matchingClip = final_clips?.find(
      c => start >= c.start && end <= c.end
    );
    if (matchingClip) {
      return {
        type: "clip",
        color: "rgba(16, 185, 129, 0.15)", // faint success
        borderColor: "var(--success)",
        index: matchingClip.clip_index
      };
    }

    if (showCandidates) {
      const matchingCandidate = candidates?.find(
        cand => start >= cand.window_start && end <= cand.window_end
      );
      if (matchingCandidate) {
        return {
          type: "candidate",
          color: "rgba(79, 70, 229, 0.08)", // faint accent
          borderColor: "var(--accent-2)"
        };
      }
    }

    return null;
  };

  // Helper to find if a clip starts/ends exactly at/near this segment
  const getBoundaryAnnotations = (start, end) => {
    const annotations = [];

    final_clips?.forEach(c => {
      // clip start annotation (if this line starts within 1.0s of the clip start)
      if (Math.abs(start - c.start) < 1.0) {
        annotations.push({
          type: "start",
          clipIndex: c.clip_index + 1,
          reasons: c.start_reasoning || [],
          timestamp: c.start
        });
      }
      // clip end annotation (if this line ends within 1.0s of the clip end)
      if (Math.abs(end - c.end) < 1.0) {
        annotations.push({
          type: "end",
          clipIndex: c.clip_index + 1,
          reasons: c.end_reasoning || [],
          timestamp: c.end
        });
      }
    });

    return annotations;
  };

  return (
    <div className="transcript-inspector-container">
      <div className="card-header transcript-header-bar">
        <div className="header-info">
          <h3>Transcript Boundary Inspector</h3>
          <p className="subtitle">Verify sentence alignments. Green blocks represent finalized clips. Click lines to seek the video player.</p>
        </div>
        <div className="header-actions">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={showCandidates}
              onChange={(e) => setShowCandidates(e.target.checked)}
            />
            Show Candidate Windows (Faint Blue)
          </label>
        </div>
      </div>

      <div className="grid-2col transcript-main-grid">
        {/* Left Side: Transcript Scroll area */}
        <div className="card transcript-scroll-card">
          <div className="card-body transcript-body-scroll">
            {transcript && transcript.length > 0 ? (
              transcript.map((line, idx) => {
                const status = getLineStatus(line.start, line.end);
                const boundaries = getBoundaryAnnotations(line.start, line.end);
                
                const lineStyle = status
                  ? { backgroundColor: status.color, borderLeft: `3px solid ${status.borderColor}` }
                  : { borderLeft: "3px solid transparent" };

                return (
                  <div key={idx} className="transcript-line-wrapper">
                    {/* Render boundary annotations ABOVE the line if it is a start, or BELOW if it is an end */}
                    {boundaries.map((annot, aIdx) => (
                      <div key={aIdx} className={`boundary-annotation boundary-${annot.type}`}>
                        <div className="boundary-title">
                          <strong>{annot.type === "start" ? "▶" : "■"} CLIP #{annot.clipIndex} {annot.type.toUpperCase()}</strong>
                          <span className="boundary-timestamp">({formatTime(annot.timestamp)})</span>
                        </div>
                        <ul className="boundary-reasons">
                          {annot.reasons.map((r, rIdx) => (
                            <li key={rIdx}>{r}</li>
                          ))}
                        </ul>
                      </div>
                    ))}

                    <div
                      className="transcript-line-row"
                      style={lineStyle}
                      onClick={() => handleLineClick(line.start, line.end)}
                    >
                      <span className="line-time">[{formatTime(line.start)}]</span>
                      {line.speaker && (
                        <span className="line-speaker">{line.speaker}:</span>
                      )}
                      <span className="line-text">{line.text}</span>
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="empty-message">No transcript content parsed.</div>
            )}
          </div>
        </div>

        {/* Right Side: Floating Video Player */}
        <div className="transcript-player-column">
          <div className="card sticky-player-card">
            <div className="card-header">
              <h4>Debugger Video Context</h4>
              <p className="subtitle">Seeked to line: {formatTime(videoSeekTime)}</p>
            </div>
            <div className="card-body">
              <VideoSeekPlayer
                ref={playerRef}
                src={getVideoUrl(meta.run_uuid)}
                start={videoSeekTime}
                end={videoEndTime}
                runUuid={meta.run_uuid}
              />
              <div className="player-context-help">
                <p>Clicking any sentence in the transcript list on the left will immediately sync this video player to start playing from that exact timestamp.</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
