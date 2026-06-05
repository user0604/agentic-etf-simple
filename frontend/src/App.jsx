import React, { useState, useRef, useCallback, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import RunForm from './RunForm.jsx';
import ActivityFeed from './ActivityFeed.jsx';
import PortfolioTable from './PortfolioTable.jsx';
import RunHistory from './RunHistory.jsx';

const AGENT_ROLES = {
  'A': 'Orchestrator',
  'M': 'Macro Strategist',
  'B': 'Portfolio Builder',
  'C': 'Critic',
  'D': 'Tiebreaker',
};

function agentDisplayName(agent) {
  if (!agent) return '';
  if (agent.startsWith('X')) return `Research Agent ${agent}`;
  if (agent === 'system') return 'System';
  return AGENT_ROLES[agent] || agent;
}

const PIPELINE_ORDER = ['M', 'B', 'C', 'D'];

export default function App() {
  const [runActive, setRunActive] = useState(false);
  const [events, setEvents] = useState([]);
  const [finalPortfolio, setFinalPortfolio] = useState(null);
  const [activeRunId, setActiveRunId] = useState(null);
  const [agentStatuses, setAgentStatuses] = useState({});
  const eventSourceRef = useRef(null);

  const { data: pastRuns, refetch: refetchRuns } = useQuery({
    queryKey: ['pastRuns'],
    queryFn: () => fetch('/api/runs').then(r => r.json()),
  });

  const connectSSE = useCallback((runId) => {
    const es = new EventSource(`/api/run/${runId}/events`);
    eventSourceRef.current = es;

    es.onmessage = (e) => {
      let data;
      try { data = JSON.parse(e.data); } catch { return; }

      // Track agent statuses for the bottom bar
      if (data.agent && data.status) {
        setAgentStatuses(prev => {
          const next = { ...prev };
          const key = data.agent;
          const status = data.status;
          if (status === 'working' || status === 'running' || status === 'in_progress') {
            next[key] = 'working';
          } else if (status === 'done' || status === 'completed') {
            next[key] = 'done';
          } else if (status === 'error') {
            next[key] = 'error';
          } else if (status === 'final') {
            next['__pipeline__'] = 'done';
          }
          return next;
        });
      }

      // Add client-side received timestamp for display
      data._receivedAt = new Date().toISOString();
      setEvents(prev => [...prev, data]);

      if (data.status === 'final') {
        setFinalPortfolio(data.portfolio);
        setRunActive(false);
        es.close();
        refetchRuns();
      } else if (data.status === 'error') {
        setRunActive(false);
        es.close();
      }
    };

    es.onerror = () => {
      setRunActive(false);
      es.close();
    };
  }, [refetchRuns]);

  const handleRun = useCallback(async (budget, date) => {
    setRunActive(true);
    setEvents([]);
    setFinalPortfolio(null);
    setAgentStatuses({});

    const res = await fetch('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ budget, date }),
    });
    if (!res.ok) {
      setEvents(prev => [...prev, { agent: 'system', status: 'error', message: 'Failed to start run', _receivedAt: new Date().toISOString() }]);
      setRunActive(false);
      return;
    }
    const { run_id } = await res.json();
    setActiveRunId(run_id);
    connectSSE(run_id);
  }, [connectSSE]);

  const fileInputRef = useRef(null);

  const handleExport = useCallback(() => {
    const payload = {
      exportedAt: new Date().toISOString(),
      runId: activeRunId,
      budget: events.find(e => e.status === 'working' && e.agent === 'A')?.message || '',
      portfolio: finalPortfolio,
      events,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `portfolio-${activeRunId || 'export'}-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [activeRunId, finalPortfolio, events]);

  const handleLoad = useCallback((e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const data = JSON.parse(ev.target.result);
        if (data.events) setEvents(data.events);
        if (data.portfolio) setFinalPortfolio(data.portfolio);
        if (data.runId) setActiveRunId(data.runId);
      } catch (err) {
        console.error('Failed to load export file:', err);
      }
    };
    reader.readAsText(file);
    // Reset input so the same file can be loaded again
    e.target.value = '';
  }, []);

  const handleResume = useCallback(async (folder) => {
    setRunActive(true);
    setEvents([]);
    setFinalPortfolio(null);
    setAgentStatuses({});

    const res = await fetch('/api/run/resume', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folder }),
    });
    if (!res.ok) {
      const err = await res.text();
      setEvents(prev => [...prev, { agent: 'system', status: 'error', message: `Resume failed: ${err}`, _receivedAt: new Date().toISOString() }]);
      setRunActive(false);
      return;
    }
    const { run_id } = await res.json();
    setActiveRunId(run_id);
    connectSSE(run_id);
  }, [connectSSE]);

  // Compute pipeline status groups
  const pipelineStatus = useMemo(() => {
    const finished = [];
    const working = [];
    const upcoming = [];

    // Get agents that have appeared in events
    const seenAgents = new Set();
    for (const ev of events) {
      if (ev.agent && ev.agent !== 'A' && ev.agent !== 'system' && !ev.agent.startsWith('X')) {
        seenAgents.add(ev.agent);
      }
    }

    // Track research agents separately
    const researchWorking = [];

    for (const [agent, status] of Object.entries(agentStatuses)) {
      if (agent.startsWith('__')) continue;
      if (agent.startsWith('X')) {
        if (status === 'working') researchWorking.push(agent);
        continue;
      }
      if (status === 'done') finished.push(agent);
      else if (status === 'working') working.push(agent);
    }

    // Determine upcoming: agents in pipeline order not yet started
    for (const agent of PIPELINE_ORDER) {
      const status = agentStatuses[agent];
      if (!status && !finished.includes(agent)) {
        upcoming.push(agent);
      } else if (status === 'working') {
        // already counted
      }
    }

    // If research phase is active, show a general "Research Agents" label
    const researchActive = Object.keys(agentStatuses).some(k => k.startsWith('X'));
    const researchDone = Object.keys(agentStatuses).some(k => k.startsWith('X') && agentStatuses[k] === 'done');

    return {
      finished,
      working: [...working, ...(researchWorking.length > 0 ? ['R'] : [])],
      upcoming,
      researchActive: researchWorking.length > 0 || (researchActive && !researchDone),
    };
  }, [agentStatuses, events]);

  return (
    <div style={{ display: 'flex', height: '100vh', flexDirection: 'column' }}>
      <style>{`
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
      `}</style>
      {/* Main content area */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Left sidebar */}
        <div style={{
          width: 320, padding: 16, borderRight: '1px solid #21262d',
          display: 'flex', flexDirection: 'column', gap: 16,
          overflowY: 'auto',
        }}>
          {/* Conditionally hide RunForm when running */}
          {!runActive && (
            <>
              <RunForm onRun={handleRun} onResume={handleResume} disabled={runActive} />
              <RunHistory runs={pastRuns} />
            </>
          )}
          {runActive && (
            <div style={{ padding: '16px 0' }}>
              <div style={{
                padding: 12, background: '#161b22', borderRadius: 6,
                border: '1px solid #30363d', textAlign: 'center',
              }}>
                <div style={{ color: '#58a6ff', fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
                  Run in Progress
                </div>
                <div style={{ color: '#8b949e', fontSize: 12 }}>
                  Run ID: {activeRunId || '...'}
                </div>
                <div style={{ marginTop: 8 }}>
                  <span style={{
                    display: 'inline-block', width: 8, height: 8,
                    borderRadius: '50%', background: '#58a6ff',
                    animation: 'pulse 1.5s infinite',
                  }} />
                </div>
              </div>
              <RunHistory runs={pastRuns} />
            </div>
          )}
        </div>

        {/* Content area */}
        <div style={{ flex: 1, padding: 16, overflowY: 'auto' }}>
          <ActivityFeed events={events} agentDisplayFn={agentDisplayName} />

          {/* Export / Load toolbar */}
          {finalPortfolio && (
            <div style={{
              marginTop: 16, padding: '8px 0', display: 'flex', gap: 8,
              borderTop: '1px solid #21262d',
            }}>
              <button
                onClick={handleExport}
                style={{
                  padding: '6px 14px', background: '#1f6feb', color: '#fff',
                  border: 'none', borderRadius: 4, fontSize: 12, fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                ⬇ Export to JSON
              </button>
              <button
                onClick={() => fileInputRef.current?.click()}
                style={{
                  padding: '6px 14px', background: '#21262d', color: '#8b949e',
                  border: '1px solid #30363d', borderRadius: 4, fontSize: 12,
                  fontWeight: 600, cursor: 'pointer',
                }}
              >
                ⬆ Load from JSON
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".json"
                onChange={handleLoad}
                style={{ display: 'none' }}
              />
            </div>
          )}

          {finalPortfolio && <PortfolioTable portfolio={finalPortfolio} />}
        </div>
      </div>

      {/* Bottom pipeline status bar */}
      {runActive && (
        <div style={{
          borderTop: '1px solid #21262d', background: '#0d1117',
          padding: '8px 16px', display: 'flex', gap: 16,
          fontSize: 12, fontFamily: 'monospace', alignItems: 'center',
          flexShrink: 0, flexWrap: 'wrap',
        }}>
          <span style={{ color: '#8b949e', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Agent Status:
          </span>

          {/* Finished */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ color: '#3fb950' }}>✓</span>
            <span style={{ color: '#8b949e', fontSize: 11, marginRight: 2 }}>Finished:</span>
            <span style={{ color: '#8b949e' }}>
              {pipelineStatus.finished.length > 0
                ? pipelineStatus.finished.map(agentDisplayName).join(', ')
                : '—'}
            </span>
          </div>

          <span style={{ color: '#21262d', userSelect: 'none' }}>|</span>

          {/* Working */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{
              display: 'inline-block', width: 6, height: 6,
              borderRadius: '50%', background: '#58a6ff',
              animation: 'pulse 1.5s infinite',
            }} />
            <span style={{ color: '#58a6ff', fontSize: 11, marginRight: 2 }}>Working:</span>
            <span style={{ color: pipelineStatus.researchActive ? '#d29922' : '#58a6ff', fontWeight: 600 }}>
              {pipelineStatus.working.length > 0
                ? pipelineStatus.working.map(a => a === 'R' ? 'Research Agents' : agentDisplayName(a)).join(', ')
                : '—'}
            </span>
          </div>

          <span style={{ color: '#21262d', userSelect: 'none' }}>|</span>

          {/* Up next */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ color: '#30363d' }}>→</span>
            <span style={{ color: '#30363d', fontSize: 11, marginRight: 2 }}>Up next:</span>
            <span style={{ color: '#30363d' }}>
              {pipelineStatus.upcoming.length > 0
                ? pipelineStatus.upcoming.map(agentDisplayName).join(', ')
                : '—'}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}