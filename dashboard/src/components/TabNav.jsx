import React from "react";

export default function TabNav({ activeTab, onTabChange }) {
  const tabs = [
    { id: "timeline", label: "Timeline Debugger" },
    { id: "clips", label: "Selected Clips" },
    { id: "candidates", label: "Candidate Explorer" },
    { id: "transcript", label: "Transcript Inspector" },
    { id: "stats", label: "Stats & Funnel" }
  ];

  return (
    <div className="tab-nav-wrapper">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          className={`tab-btn ${activeTab === tab.id ? "tab-btn-active" : ""}`}
          onClick={() => onTabChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
