import React from "react";
import { Bar, Doughnut } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
  ArcElement
} from "chart.js";

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend, ArcElement);

export default function Statistics({ analysisData }) {
  if (!analysisData) {
    return <div className="empty-message">No statistics data available. Please select a job.</div>;
  }

  const { stats } = analysisData;

  // Pipeline Funnel data
  const funnelSteps = [
    { label: "Total Windows Scanned", val: stats.total_windows_evaluated },
    { label: "Speech Filter Passed", val: stats.total_windows_evaluated - (stats.filter_breakdown?.no_speech || 0) },
    { label: "Energy Filter Passed", val: stats.total_candidates },
    { label: "Dedup / Positions", val: stats.unique_after_dedup },
    { label: "Selected Final Clips", val: stats.selected }
  ];

  // Rejection pie chart data
  const rejectionData = {
    labels: Object.keys(stats.rejection_breakdown || {}).map(k => k.replace(/_/g, " ").toUpperCase()),
    datasets: [
      {
        data: Object.values(stats.rejection_breakdown || {}),
        backgroundColor: ["#4f46e5", "#10b981", "#f59e0b", "#ef4444", "#a1a1aa"],
        borderWidth: 1
      }
    ]
  };

  // Duration distribution data
  const durationLabels = stats.duration?.distribution?.map(d => d.range) || [];
  const durationCounts = stats.duration?.distribution?.map(d => d.count) || [];
  const durationData = {
    labels: durationLabels,
    datasets: [
      {
        label: "Candidates Count",
        data: durationCounts,
        backgroundColor: "rgba(79, 70, 229, 0.65)",
        borderColor: "var(--accent-2)",
        borderWidth: 1
      }
    ]
  };

  // Stop score distribution data
  const stopScoreLabels = stats.stop_scores?.distribution?.map(d => `Score ${d.score}`) || [];
  const stopScoreCounts = stats.stop_scores?.distribution?.map(d => d.count) || [];
  const stopScoreData = {
    labels: stopScoreLabels,
    datasets: [
      {
        label: "Stopping Points Count",
        data: stopScoreCounts,
        backgroundColor: "rgba(16, 185, 129, 0.65)",
        borderColor: "var(--success)",
        borderWidth: 1
      }
    ]
  };

  return (
    <div className="statistics-tab-container">
      {/* Funnel Card */}
      <div className="card funnel-card">
        <div className="card-header">
          <h3>Algorithm Pipeline Funnel</h3>
          <p className="subtitle">Track how candidates are progressively winnowed down from sliding window boundaries to final clips.</p>
        </div>
        <div className="card-body">
          <PipelineFunnel steps={funnelSteps} />
        </div>
      </div>

      <div className="grid-2col charts-grid">
        {/* Rejection Pie Chart */}
        <div className="card chart-card">
          <div className="card-header">
            <h4>Rejection Breakdown</h4>
            <p className="subtitle">Visualizing why candidate windows were rejected during ranked selection.</p>
          </div>
          <div className="card-body flex justify-center align-center" style={{ maxHeight: "300px", padding: "20px" }}>
            {Object.keys(stats.rejection_breakdown || {}).length > 0 ? (
              <Doughnut
                data={rejectionData}
                options={{
                  responsive: true,
                  plugins: { legend: { position: "right" } }
                }}
              />
            ) : (
              <div className="empty-message">No rejections recorded. (All candidates selected or no candidates evaluated)</div>
            )}
          </div>
        </div>

        {/* Duration distribution */}
        <div className="card chart-card">
          <div className="card-header">
            <h4>Clip Duration Distribution</h4>
            <p className="subtitle">Shows candidate window durations across defined duration buckets.</p>
          </div>
          <div className="card-body">
            <Bar
              data={durationData}
              options={{
                responsive: true,
                scales: { y: { beginAtZero: true } }
              }}
            />
          </div>
        </div>

        {/* Stop Score distribution */}
        <div className="card chart-card">
          <div className="card-header">
            <h4>Stopping Point Scores Distribution</h4>
            <p className="subtitle">Scores calculated across all evaluated stopping point boundaries.</p>
          </div>
          <div className="card-body">
            <Bar
              data={stopScoreData}
              options={{
                responsive: true,
                scales: { y: { beginAtZero: true } }
              }}
            />
          </div>
        </div>

        {/* Filters Summary box */}
        <div className="card stats-summary-box">
          <div className="card-header">
            <h4>Pipeline Filter Summary</h4>
          </div>
          <div className="card-body">
            <div className="stats-list">
              <div className="stats-row-item">
                <span>No Stopping Point found:</span>
                <strong>{stats.filter_breakdown?.no_stopping_point || 0} windows</strong>
              </div>
              <div className="stats-row-item">
                <span>No Speech in window:</span>
                <strong>{stats.filter_breakdown?.no_speech || 0} windows</strong>
              </div>
              <div className="stats-row-item">
                <span>Failed Speech/Energy filter:</span>
                <strong>{stats.filter_breakdown?.failed_energy_filter || 0} windows</strong>
              </div>
              <hr className="divider" />
              <div className="stats-row-item">
                <span>Fallback clips created:</span>
                <strong>{stats.from_fallback || 0} clip(s)</strong>
              </div>
              <div className="stats-row-item">
                <span>Duplicated clips (padding):</span>
                <strong>{stats.duplicated || 0} clip(s)</strong>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function PipelineFunnel({ steps }) {
  const maxVal = steps[0]?.val || 1;

  return (
    <div className="pipeline-funnel">
      {steps.map((step, idx) => {
        const widthPercent = (step.val / maxVal) * 100;
        return (
          <div key={idx} className="funnel-step-row">
            <div className="funnel-label">{step.label}</div>
            <div className="funnel-bar-container">
              <div
                className="funnel-bar"
                style={{
                  width: `${widthPercent}%`,
                  backgroundColor: `rgba(79, 70, 229, ${1.0 - (idx * 0.15)})`
                }}
              >
                <span className="funnel-val">{step.val}</span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
