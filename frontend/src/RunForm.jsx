import React, { useState } from 'react';

export default function RunForm({ onRun, onResume, disabled }) {
  const [budget, setBudget] = useState('1000000');
  const [date, setDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() + 7);
    return d.toISOString().split('T')[0];
  });
  const [resumeFolder, setResumeFolder] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!disabled) onRun(budget, date);
  };

  const handleResumeClick = () => {
    if (!disabled && resumeFolder.trim() && onResume) {
      onResume(resumeFolder.trim());
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <h2 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>Run Parameters</h2>
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div>
          <label style={{ display: 'block', fontSize: 12, color: '#8b949e', marginBottom: 4 }}>
            Budget (JPY)
          </label>
          <input
            type="number"
            value={budget}
            onChange={e => setBudget(e.target.value)}
            disabled={disabled}
            style={{ width: '100%', padding: '8px 12px', background: '#161b22', border: '1px solid #30363d', borderRadius: 6, color: '#e1e4e8', fontSize: 14 }}
          />
        </div>
        <div>
          <label style={{ display: 'block', fontSize: 12, color: '#8b949e', marginBottom: 4 }}>
            Purchase Date
          </label>
          <input
            type="date"
            value={date}
            onChange={e => setDate(e.target.value)}
            disabled={disabled}
            style={{ width: '100%', padding: '8px 12px', background: '#161b22', border: '1px solid #30363d', borderRadius: 6, color: '#e1e4e8', fontSize: 14 }}
          />
        </div>
        <button
          type="submit"
          disabled={disabled}
          style={{
            padding: '10px 16px', background: disabled ? '#21262d' : '#238636', color: '#fff',
            border: 'none', borderRadius: 6, fontSize: 14, fontWeight: 600, cursor: disabled ? 'not-allowed' : 'pointer',
          }}
        >
          {disabled ? 'Running...' : 'Run'}
        </button>
      </form>

      <hr style={{ border: 'none', borderTop: '1px solid #21262d', margin: '4px 0' }} />

      <h2 style={{ fontSize: 14, fontWeight: 600, margin: 0 }}>Resume Past Run</h2>
      <div>
        <label style={{ display: 'block', fontSize: 12, color: '#8b949e', marginBottom: 4 }}>
          Run Folder Path
        </label>
        <input
          type="text"
          value={resumeFolder}
          onChange={e => setResumeFolder(e.target.value)}
          placeholder="e.g. backend/runs/2026-06-03T12-00-00_abc123"
          disabled={disabled}
          style={{ width: '100%', padding: '8px 12px', background: '#161b22', border: '1px solid #30363d', borderRadius: 6, color: '#e1e4e8', fontSize: 13 }}
        />
      </div>
      <button
        type="button"
        onClick={handleResumeClick}
        disabled={disabled || !resumeFolder.trim()}
        style={{
          padding: '10px 16px',
          background: disabled || !resumeFolder.trim() ? '#21262d' : '#1f6feb',
          color: '#fff', border: 'none', borderRadius: 6, fontSize: 14,
          fontWeight: 600, cursor: disabled || !resumeFolder.trim() ? 'not-allowed' : 'pointer',
        }}
      >
        {disabled ? 'Running...' : 'Resume from Folder'}
      </button>
    </div>
  );
}