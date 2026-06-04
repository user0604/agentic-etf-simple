import React from 'react';

export default function RunHistory({ runs }) {
  if (!runs || runs.length === 0) return null;

  return (
    <div>
      <h2 style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, color: '#8b949e' }}>Past Runs</h2>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {runs.map((run, i) => (
          <div
            key={i}
            style={{
              padding: '8px 12px', background: '#161b22', borderRadius: 6, fontSize: 12, cursor: 'pointer',
              border: '1px solid #21262d',
            }}
            onClick={() => window.open(`/api/runs/${run.id}`, '_blank')}
          >
            <div style={{ color: '#e1e4e8' }}>{run.date}</div>
            <div style={{ color: '#8b949e' }}>¥{Number(run.budget).toLocaleString()}</div>
            {run.holdings && <div style={{ color: '#3fb950' }}>{run.holdings} holdings</div>}
          </div>
        ))}
      </div>
    </div>
  );
}