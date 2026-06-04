import React, { useEffect, useRef, useState } from 'react';

const STATUS_ICONS = {
  working: '~',
  done: '✓',
  error: '✗',
  pending: ' ',
  plan_submitted: '⟐',
  plan_approved: '✓',
  detail: '▶',
};

function DetailCollapsible({ detail }) {
  const [open, setOpen] = useState(false);
  if (!detail) return null;

  const content = typeof detail === 'string' ? detail : JSON.stringify(detail, null, 2);
  const preview = typeof detail === 'string'
    ? detail.slice(0, 80)
    : JSON.stringify(detail).slice(0, 80);

  return (
    <div style={{ marginLeft: 24, marginTop: 4 }}>
      <button
        onClick={() => setOpen(!open)}
        style={{
          background: '#161b22', border: '1px solid #30363d', borderRadius: 4,
          color: '#8b949e', cursor: 'pointer', fontSize: 12, padding: '2px 8px',
        }}
      >
        {open ? '▼' : '▶'} {open ? 'Hide details' : 'Show details'} — {preview}…
      </button>
      {open && (
        <pre style={{
          marginTop: 6, padding: 10, background: '#0d1117', borderRadius: 6,
          border: '1px solid #21262d', fontSize: 11, lineHeight: 1.5,
          overflowX: 'auto', whiteSpace: 'pre-wrap', maxHeight: 400, overflowY: 'auto',
        }}>
          {content}
        </pre>
      )}
    </div>
  );
}

function formatEventMessage(ev) {
  if (ev.message) return ev.message;
  if (ev.status === 'detail') return `— detail available for ${ev.agent}`;
  return '';
}

export default function ActivityFeed({ events }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events]);

  // Group events: if an event has detail, attach it to the previous event
  const displayEvents = [];
  let pendingDetail = null;
  for (const ev of events) {
    if (ev.status === 'detail' && ev.detail) {
      pendingDetail = ev.detail;
      continue;
    }
    displayEvents.push({ ...ev, _detail: pendingDetail });
    pendingDetail = null;
  }

  return (
    <div>
      <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>Agent Activity Feed</h2>
      <div style={{ fontFamily: 'monospace', fontSize: 13, lineHeight: 1.8 }}>
        {displayEvents.length === 0 && (
          <div style={{ color: '#8b949e' }}>Enter parameters and click Run to start.</div>
        )}
        {displayEvents.map((ev, i) => (
          <div key={i} style={{ marginBottom: 8 }}>
            <div style={{
              color: ev.status === 'error' ? '#f85149' : '#e1e4e8',
              display: 'flex', alignItems: 'flex-start', gap: 8,
            }}>
              <span style={{
                color: ev.status === 'working' ? '#58a6ff'
                     : ev.status === 'error' ? '#f85149'
                     : ev.status === 'plan_submitted' ? '#d29922'
                     : '#3fb950',
                flexShrink: 0,
              }}>
                [{STATUS_ICONS[ev.status] || ev.status}]
              </span>
              <span style={{ fontWeight: 600, color: '#d2a8ff', flexShrink: 0 }}>{ev.agent}:</span>
              <span>{formatEventMessage(ev)}</span>
            </div>
            {ev._detail && <DetailCollapsible detail={ev._detail} />}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}