import React from "react";
import { formatTime } from "../utils/format";

export default function VideoOverview({ meta, stats }) {
  if (!meta) return null;

  return (
    <div className="card video-overview-card">
      <div className="card-body overview-grid-compact">
        <div className="overview-item">
          <span className="label">File Name</span>
          <strong className="val" title={meta.filename}>{meta.filename}</strong>
        </div>
        <div className="overview-item">
          <span className="label">Job ID</span>
          <strong className="val">{meta.job_id || "N/A"}</strong>
        </div>
        <div className="overview-item">
          <span className="label">Video Duration</span>
          <strong className="val">{formatTime(meta.video_duration_seconds)}</strong>
        </div>
        <div className="overview-item">
          <span className="label">Processing Time</span>
          <strong className="val">
            {meta.processing_time_ms ? `${(meta.processing_time_ms / 1000).toFixed(2)}s` : "N/A"}
          </strong>
        </div>
        <div className="overview-item">
          <span className="label">Clips Count</span>
          <strong className="val">{stats?.selected || 0} / {meta.config?.max_clips || 3}</strong>
        </div>
        <div className="overview-item">
          <span className="label">Candidates</span>
          <strong className="val">{stats?.total_candidates || 0}</strong>
        </div>
        <div className="overview-item">
          <span className="label">Algorithm Version</span>
          <strong className="val"><code>{meta.algorithm_version}</code></strong>
        </div>
      </div>
    </div>
  );
}
