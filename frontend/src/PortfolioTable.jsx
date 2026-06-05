import React, { useState } from 'react';

const JPYollar = new Intl.NumberFormat('ja-JP', {
  style: 'currency', currency: 'JPY', minimumFractionDigits: 0, maximumFractionDigits: 0,
});

export default function PortfolioTable({ portfolio }) {
  const [expandedThesis, setExpandedThesis] = useState({});

  if (!portfolio || !portfolio.holdings) return null;

  const { holdings, total_budget: totalBudget, fx_rate: fxRate, purchase_date: date, audit_trail } = portfolio;

  const toggleThesis = (ticker) => {
    setExpandedThesis(prev => ({ ...prev, [ticker]: !prev[ticker] }));
  };

  return (
    <div style={{ marginTop: 24 }}>
      <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>Final Portfolio</h2>

      <div style={{ marginBottom: 12, fontSize: 13, color: '#8b949e' }}>
        Total Budget: {JPYollar.format(Number(totalBudget) || 0)}
        {fxRate ? ` | FX Rate: ${fxRate} JPY/USD` : ''}
        {date ? ` | Purchase Date: ${date}` : ''}
        {holdings.length > 0 ? ` | Holdings: ${holdings.length}` : ''}
      </div>

      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: '2px solid #30363d', color: '#8b949e', textAlign: 'left' }}>
            <th style={{ padding: '8px 10px' }}>Ticker</th>
            <th style={{ padding: '8px 10px' }}>Name</th>
            <th style={{ padding: '8px 10px' }}>Sector</th>
            <th style={{ padding: '8px 10px', textAlign: 'right' }}>Allocation</th>
            <th style={{ padding: '8px 10px', textAlign: 'right' }}>Price</th>
            <th style={{ padding: '8px 10px', textAlign: 'right' }}>Volume</th>
            <th style={{ padding: '8px 10px', textAlign: 'right' }}>%</th>
            <th style={{ padding: '8px 10px' }}>Confidence</th>
            <th style={{ padding: '8px 10px' }}>Thesis</th>
          </tr>
        </thead>
        <tbody>
          {holdings.map((h, i) => (
            <React.Fragment key={h.ticker}>
              <tr style={{
                borderBottom: expandedThesis[h.ticker] ? 'none' : '1px solid #21262d',
                background: i % 2 === 0 ? 'transparent' : '#0d1117',
              }}>
                <td style={{ padding: '8px 10px', fontWeight: 600, color: '#d2a8ff' }}>{h.ticker}</td>
                <td style={{ padding: '8px 10px', color: '#e1e4e8' }}>{h.name || '—'}</td>
                <td style={{ padding: '8px 10px', color: '#8b949e', fontSize: 12 }}>{h.sector || '—'}</td>
                <td style={{ padding: '8px 10px', textAlign: 'right', color: '#58a6ff', fontVariantNumeric: 'tabular-nums' }}>
                  {h.amount != null ? JPYollar.format(h.amount) : '—'}
                </td>
                <td style={{ padding: '8px 10px', textAlign: 'right', color: '#e1e4e8', fontVariantNumeric: 'tabular-nums' }}>
                  {h.price != null ? `¥${Number(h.price).toLocaleString()}` : '—'}
                </td>
                <td style={{ padding: '8px 10px', textAlign: 'right', color: '#e1e4e8', fontVariantNumeric: 'tabular-nums' }}>
                  {h.volume != null ? Number(h.volume).toLocaleString() : '—'}
                </td>
                <td style={{ padding: '8px 10px', textAlign: 'right', color: '#3fb950', fontVariantNumeric: 'tabular-nums' }}>
                  {h.pct != null ? `${h.pct}%` : '—'}
                </td>
                <td style={{ padding: '8px 10px' }}>
                  <span style={{
                    padding: '1px 6px', borderRadius: 3, fontSize: 11,
                    background: h.confidence === 'high' ? '#23863633'
                             : h.confidence === 'medium' ? '#d2992233'
                             : '#21262d',
                    color: h.confidence === 'high' ? '#3fb950'
                         : h.confidence === 'medium' ? '#d29922'
                         : '#8b949e',
                  }}>
                    {h.confidence || '—'}
                  </span>
                </td>
                <td style={{ padding: '8px 10px' }}>
                  {h.thesis ? (
                    <button
                      onClick={() => toggleThesis(h.ticker)}
                      style={{
                        background: '#161b22', border: '1px solid #30363d', borderRadius: 4,
                        color: '#8b949e', cursor: 'pointer', fontSize: 11, padding: '2px 6px',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {expandedThesis[h.ticker] ? '▼ Hide' : '▶ View'}
                    </button>
                  ) : (
                    <span style={{ color: '#8b949e', fontSize: 11 }}>—</span>
                  )}
                </td>
              </tr>
              {expandedThesis[h.ticker] && h.thesis && (
                <tr style={{ borderBottom: '1px solid #21262d' }}>
                  <td colSpan={9} style={{ padding: '8px 10px 12px 10px' }}>
                    <div style={{
                      padding: '8px 12px', background: '#0d1117', borderRadius: 4,
                      border: '1px solid #21262d', fontSize: 12, color: '#e1e4e8',
                      lineHeight: 1.6,
                    }}>
                      <strong style={{ color: '#d2a8ff' }}>Investment Thesis</strong>
                      <div style={{ marginTop: 4, whiteSpace: 'pre-wrap' }}>{h.thesis}</div>
                    </div>
                  </td>
                </tr>
              )}
            </React.Fragment>
          ))}
        </tbody>
      </table>

      {audit_trail && (
        <details style={{ marginTop: 16 }}>
          <summary style={{ cursor: 'pointer', fontSize: 13, color: '#8b949e' }}>
            Run Audit Trail
          </summary>
          <pre style={{
            marginTop: 8, padding: 12, background: '#161b22', borderRadius: 6,
            fontSize: 12, lineHeight: 1.6, overflowX: 'auto', whiteSpace: 'pre-wrap',
          }}>
            {JSON.stringify(audit_trail, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}