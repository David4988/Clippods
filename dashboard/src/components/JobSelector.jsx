import React from "react";

export default function JobSelector({ jobs, selectedUuid, onSelectJob, onRefresh, isLoading }) {
  return (
    <div className="card job-selector-card">
      <div className="card-body selector-flex">
        <div className="selector-label-group">
          <label htmlFor="job-select-dropdown">Select Processed Video Job:</label>
          <p className="subtitle">Choose a run to load its algorithm execution trace analysis.</p>
        </div>
        <div className="selector-controls">
          <select
            id="job-select-dropdown"
            value={selectedUuid || ""}
            onChange={(e) => onSelectJob(e.target.value)}
            disabled={isLoading || jobs.length === 0}
          >
            {jobs.length === 0 ? (
              <option value="">No processed jobs found</option>
            ) : (
              <>
                <option value="">-- Choose a job run --</option>
                {jobs.map((job) => (
                  <option key={job.run_uuid} value={job.run_uuid}>
                    {job.filename} ({job.clips_count} clips, {new Date(job.timestamp).toLocaleString()})
                  </option>
                ))}
              </>
            )}
          </select>
          <button className="btn" onClick={onRefresh} disabled={isLoading}>
            {isLoading ? "Refreshing..." : "Refresh List"}
          </button>
        </div>
      </div>
    </div>
  );
}
