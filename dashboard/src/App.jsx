import React, { useState, useEffect } from "react";
import "./App.css";

import { fetchAnalysisJobs, fetchAnalysisDetails } from "./api/analysis";
import JobSelector from "./components/JobSelector";
import VideoOverview from "./components/VideoOverview";
import TabNav from "./components/TabNav";

import InteractiveTimeline from "./components/Timeline";
import FinalClips from "./components/Clips";
import CandidateExplorer from "./components/Candidates";
import TranscriptInspector from "./components/Transcript";
import Statistics from "./components/Stats";

export default function App() {
  const [jobs, setJobs] = useState([]);
  const [selectedUuid, setSelectedUuid] = useState("");
  const [analysisData, setAnalysisData] = useState(null);
  const [activeTab, setActiveTab] = useState("timeline");

  // Loading & error states
  const [isLoadingList, setIsLoadingList] = useState(false);
  const [isLoadingDetails, setIsLoadingDetails] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  // Candidate comparison states
  const [compareA, setCompareA] = useState(null);
  const [compareB, setCompareB] = useState(null);
  const [showComparison, setShowComparison] = useState(false);

  // Load jobs list on mount
  useEffect(() => {
    loadJobsList();
  }, []);

  // Fetch details when selected Uuid changes
  useEffect(() => {
    if (selectedUuid) {
      loadJobDetails(selectedUuid);
    } else {
      setAnalysisData(null);
    }
  }, [selectedUuid]);

  const loadJobsList = async () => {
    setIsLoadingList(true);
    setErrorMsg("");
    try {
      const data = await fetchAnalysisJobs();
      setJobs(data.jobs || []);
      // Auto-select the first job if available and none selected yet
      if (data.jobs && data.jobs.length > 0 && !selectedUuid) {
        setSelectedUuid(data.jobs[0].run_uuid);
      }
    } catch (err) {
      console.error("Failed to load jobs list:", err);
      setErrorMsg("Failed to load processed video jobs. Make sure the backend server is running.");
    } finally {
      setIsLoadingList(false);
    }
  };

  const loadJobDetails = async (uuid) => {
    setIsLoadingDetails(true);
    setErrorMsg("");
    try {
      const data = await fetchAnalysisDetails(uuid);
      setAnalysisData(data);
      // Initialize comparison selects with first two candidates
      if (data.candidates && data.candidates.length > 0) {
        setCompareA(data.candidates[0].id);
        if (data.candidates.length > 1) {
          setCompareB(data.candidates[1].id);
        } else {
          setCompareB(data.candidates[0].id);
        }
      }
    } catch (err) {
      console.error("Failed to load job details:", err);
      setErrorMsg("Failed to retrieve algorithm execution trace details.");
    } finally {
      setIsLoadingDetails(false);
    }
  };

  const handleCompareClick = (candAId, candBId) => {
    setCompareA(candAId);
    setCompareB(candBId);
    setShowComparison(true);
    setActiveTab("candidates");
  };

  return (
    <div className="app-container">
      {/* Header */}
      <header className="app-header">
        <h1>
          ClipPods <span className="dev-tag">ALGORITHM DEBUGGER v2</span>
        </h1>
        <p className="subtitle">Developer heuristical explainability and tuning workspace</p>
      </header>

      {/* Main Grid / Layout */}
      <main className="app-content">
        {/* Job Selection Bar */}
        <JobSelector
          jobs={jobs}
          selectedUuid={selectedUuid}
          onSelectJob={setSelectedUuid}
          onRefresh={loadJobsList}
          isLoading={isLoadingList}
        />

        {/* Global Error Banner */}
        {errorMsg && (
          <div className="card" style={{ backgroundColor: "var(--danger-bg)", borderColor: "var(--danger)" }}>
            <div className="card-body text-danger" style={{ fontWeight: "bold" }}>
              Error: {errorMsg}
            </div>
          </div>
        )}

        {isLoadingDetails ? (
          <div className="loading-spinner-container">
            <div className="spinner"></div>
            <p>Loading execution trace analysis from backend...</p>
          </div>
        ) : (
          analysisData && (
            <>
              {/* Overview Bar */}
              <VideoOverview
                meta={analysisData.meta}
                stats={analysisData.stats}
              />

              {/* Tab Navigation */}
              <TabNav
                activeTab={activeTab}
                onTabChange={(tabId) => {
                  setActiveTab(tabId);
                  // Reset comparison toggle when switching away from candidates
                  if (tabId !== "candidates") {
                    setShowComparison(false);
                  }
                }}
              />

              {/* Active Tab Panel */}
              <div className="tab-panel-content">
                {activeTab === "timeline" && (
                  <InteractiveTimeline
                    analysisData={analysisData}
                    onCompareClick={handleCompareClick}
                  />
                )}

                {activeTab === "clips" && (
                  <FinalClips
                    analysisData={analysisData}
                    onCompareClick={handleCompareClick}
                  />
                )}

                {activeTab === "candidates" && (
                  <CandidateExplorer
                    analysisData={analysisData}
                    compareA={compareA}
                    compareB={compareB}
                    setCompareA={setCompareA}
                    setCompareB={setCompareB}
                    showComparison={showComparison}
                    setShowComparison={setShowComparison}
                  />
                )}

                {activeTab === "transcript" && (
                  <TranscriptInspector
                    analysisData={analysisData}
                  />
                )}

                {activeTab === "stats" && (
                  <Statistics
                    analysisData={analysisData}
                  />
                )}
              </div>
            </>
          )
        )}
      </main>

      <footer className="app-footer">
        <p>ClipPods Algorithm Debugger — Developer tool for heuristic validation. Not user-facing.</p>
      </footer>
    </div>
  );
}
