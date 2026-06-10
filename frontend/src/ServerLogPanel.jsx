import React, { useEffect, useRef, useState, useCallback } from 'react';

export default function ServerLogPanel({ runId, active, onClose }) {
  const [lines, setLines] = useState([]);
  const [width, setWidth] = useState(380);
  const bottomRef = useRef(null);
  const autoScrollRef = useRef(true);
  const dragging = useRef(false);
  const panelRef = useRef(null);

  // ── Resize by dragging the left border ──────────────────────────
  const handleMouseDown = useCallback((e) => {
    e.preventDefault();
    dragging.current = true;
    const startX = e.clientX;
    const startW = panelRef.current?.offsetWidth || 380;

    const onMove = (ev) => {
      if (!dragging.current) return;
      const newW = startW - (ev.clientX - startX); // drag left edge
      setWidth(Math.max(200, Math.min(800, newW)));
    };
    const onUp = () => { dragging.current = false; };

    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp, { once: true });
  }, []);

  // ── Poll logs while run is active ───────────────────────────────
  useEffect(() => {
    if (!runId || !active) {
      setLines([]);
      return;
    }

    let cancelled = false;
    let lastLineCount = 0;

    const poll = async () => {
      try {
        const res = await fetch(`/api/run/${runId}/logs?tail=200`);
        if (!res.ok) return;
        const data = await res.json();
        if (cancelled) return;
        if (data.lines && data.lines.length !== lastLineCount) {
          setLines(data.lines);
          lastLineCount = data.lines.length;
        }
      } catch {
        // ignore
      }
    };

    poll();
    const interval = setInterval(poll, 2000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [runId, active]);

  // ── Auto-scroll ─────────────────────────────────────────────────
  useEffect(() => {
    if (autoScrollRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [lines]);

  const handleScroll = (e) => {
    const el = e.target;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    autoScrollRef.current = atBottom;
  };

  // ── Helpers ─────────────────────────────────────────────────────
  const levelColor = (line) => {
    if (line.includes('[ERROR]') || line.includes('[CRITICAL]')) return '#f85149';
    if (line.includes('[WARNING]')) return '#d29922';
    if (line.includes('[INFO]')) return '#e1e4e8';
    return '#484f58';
  };

  return (
    <div ref={panelRef} style={{
      width, borderLeft: '1px solid #21262d',
      display: 'flex', flexDirection: 'row',
      position: 'relative',
    }}>
      {/* Drag handle */}
      <div
        onMouseDown={handleMouseDown}
        style={{
          width: 4, cursor: 'col-resize', flexShrink: 0,
          background: 'transparent', position: 'relative', zIndex: 2,
        }}
      />

      {/* Panel content */}
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        background: '#0d1117', overflow: 'hidden', minWidth: 0,
      }}>
        {/* Header */}
        <div style={{
          padding: '6px 10px', borderBottom: '1px solid #21262d',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ color: '#8b949e', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Server Log
            </span>
            {active && (
              <span style={{
                display: 'inline-block', width: 5, height: 5,
                borderRadius: '50%', background: '#3fb950',
                animation: 'pulse 1.5s infinite',
              }} />
            )}
          </div>
          <button
            onClick={onClose}
            title="Close log panel"
            style={{
              background: 'none', border: 'none', color: '#484f58',
              cursor: 'pointer', fontSize: 14, padding: '0 2px', lineHeight: 1,
            }}
          >
            ✕
          </button>
        </div>

        {/* Log lines */}
        <div
          onScroll={handleScroll}
          style={{
            flex: 1, overflow: 'auto', padding: '4px 0',
            fontFamily: 'monospace', fontSize: 11, lineHeight: 1.6,
          }}
        >
          {lines.length === 0 && (
            <div style={{ color: '#484f58', padding: '8px 12px', fontStyle: 'italic' }}>
              {active ? 'Waiting for logs...' : 'No active run'}
            </div>
          )}
          {lines.map((line, i) => (
            <div
              key={i}
              style={{
                color: levelColor(line),
                padding: '0 12px',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-all',
              }}
            >
              {line.replace(/\n$/, '')}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      </div>
    </div>
  );
}