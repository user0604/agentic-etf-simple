import React from 'react';

export default function PortfolioTable({ portfolio }) {
  if (!portfolio || !portfolio.holdings) return null;

  return (
    <div style={{ marginTop: 24 }}>
      <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>Final Portfolio</h2>

      <div style={{ marginBottom: 12, fontSize: 13, color: '#8b949e' }}>
        Total Budget: ¥{Number(portfolio.total_budget).toLocaleString()}
        {' | '}FX Rate: {portfolio.fx_rate}
        {' | '}Date: {portfolio.purchase_date}
      </div>

      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: '1px solid #30363d', color: '#8b949e', textAlign: 'left' }}>
            <th style={{ padding: '8px 12px' }}>Ticker</th>
            <th style={{ padding: '8px 12px' }}>Name</th>
            <th style={{ padding: '8px 12px' }}>Allocation</th>
            <th style={{ padding: '8px 12px' }}>Confidence</th>
            <th style={{ padding: '8px 12px' }}>Thesis</th>
          </tr>
        </thead>
        <tbody>
          {portfolio.holdings.map((h, i) => (
            <tr key={i} style={{ borderBottom: '1px solid #21262d' }}>
              <td style={{ padding: '8px 12px', fontWeight: 600 }}>{h.ticker}</td>
              <td style={{ padding: '8px 12px' }}>{h.name}</td>
              <td style={{ padding: '8px 12px' }}>¥{Number(h.amount).toLocaleString()} ({h.pct}%)</td>
              <td style={{ padding: '8px 12px' }}>{h.confidence}</td>
              <td style={{ padding: '8px 12px', color: '#8b949e', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{h.thesis}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {portfolio.audit_trail && (
        <details style={{ marginTop: 16 }}>
          <summary style={{ cursor: 'pointer', fontSize: 13, color: '#8b949e' }}>Audit Trail</summary>
          <pre style={{ marginTop: 8, padding: 12, background: '#161b22', borderRadius: 6, fontSize: 12, lineHeight: 1.6, overflowX: 'auto', whiteSpace: 'pre-wrap' }}>
            {JSON.stringify(portfolio.audit_trail, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}