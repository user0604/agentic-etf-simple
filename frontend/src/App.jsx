import React, { useState, useRef, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import RunForm from './RunForm.jsx';
import ActivityFeed from './ActivityFeed.jsx';
import PortfolioTable from './PortfolioTable.jsx';
import RunHistory from './RunHistory.jsx';

export default function App() {
  const [runActive, setRunActive] = useState(false);
  const [events, setEvents] = useState([]);
  const [finalPortfolio, setFinalPortfolio] = useState(null);
  const [activeRunId, setActiveRunId] = useState(null);
  const eventSourceRef = useRef(null);

  const { data: pastRuns, refetch: refetchRuns } = useQuery({
    queryKey: ['pastRuns'],
    queryFn: () => fetch('/api/runs').then(r => r.json()),
  });

  const connectSSE = useCallback((runId) => {
    const es = new EventSource(`/api/run/${runId}/events`);
    eventSourceRef.current = es;

    es.onmessage = (e) => {
      const data = JSON.parse(e.data);
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

    const res = await fetch('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ budget, date }),
    });
    if (!res.ok) {
      setEvents(prev => [...prev, { agent: 'system', status: 'error', message: 'Failed to start run' }]);
      setRunActive(false);
      return;
    }
    const { run_id } = await res.json();
    setActiveRunId(run_id);
    connectSSE(run_id);
  }, [connectSSE]);

  const handleResume = useCallback(async (folder) => {
    setRunActive(true);
    setEvents([]);
    setFinalPortfolio(null);

    const res = await fetch('/api/run/resume', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folder }),
    });
    if (!res.ok) {
      const err = await res.text();
      setEvents(prev => [...prev, { agent: 'system', status: 'error', message: `Resume failed: ${err}` }]);
      setRunActive(false);
      return;
    }
    const { run_id } = await res.json();
    setActiveRunId(run_id);
    connectSSE(run_id);
  }, [connectSSE]);

  return (
    <div style={{ display: 'flex', height: '100vh' }}>
      <div style={{ width: 320, padding: 16, borderRight: '1px solid #21262d', display: 'flex', flexDirection: 'column', gap: 16 }}>
        <RunForm onRun={handleRun} onResume={handleResume} disabled={runActive} />
        <RunHistory runs={pastRuns} />
      </div>
      <div style={{ flex: 1, padding: 16, overflowY: 'auto' }}>
        <ActivityFeed events={events} />
        {finalPortfolio && <PortfolioTable portfolio={finalPortfolio} />}
      </div>
    </div>
  );
}