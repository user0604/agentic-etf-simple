import React, { useEffect, useRef, useState } from 'react';

function formatJST(isoString) {
  if (!isoString) return '';
  const d = new Date(isoString);
  if (isNaN(d.getTime())) return '';
  // Convert to JST (UTC+9)
  const jst = new Date(d.getTime() + 9 * 60 * 60 * 1000);
  const yyyy = jst.getUTCFullYear();
  const MM = String(jst.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(jst.getUTCDate()).padStart(2, '0');
  const hh = String(jst.getUTCHours()).padStart(2, '0');
  const mm = String(jst.getUTCMinutes()).padStart(2, '0');
  const ss = String(jst.getUTCSeconds()).padStart(2, '0');
  return `${yyyy}/${MM}/${dd} ${hh}:${mm}:${ss}`;
}

const AGENT_ROLES = {
  'A': 'Orchestrator',
  'M': 'Macro Strategist',
  'B': 'Portfolio Builder',
  'C': 'Critic',
  'D': 'Tiebreaker',
};

function agentLabel(agent) {
  if (!agent) return '';
  if (agent.startsWith('X')) {
    return `Research Agent ${agent}`;
  }
  const role = AGENT_ROLES[agent];
  return role ? `${role} (${agent})` : agent;
}

// ── Smart detail formatters ──────────────────────────────────────

function formatTasks(detail) {
  const tasks = detail.tasks || (detail.research_tasks) || [];
  if (!Array.isArray(tasks) || tasks.length === 0) return null;
  return (
    <div>
      <div style={{ fontWeight: 600, marginBottom: 6, color: '#d2a8ff' }}>Research Tasks</div>
      {tasks.map((t, i) => (
        <div key={i} style={{ marginBottom: 8, padding: '6px 8px', background: '#0d1117', borderRadius: 4, border: '1px solid #21262d' }}>
          <div><strong style={{ color: '#e1e4e8' }}>{t.topic || t.theme || 'Task ' + (i+1)}</strong></div>
          <div style={{ color: '#8b949e', fontSize: 11, marginTop: 2 }}>
            {t.industry && <span>{t.industry}{t.sub_industry ? ` / ${t.sub_industry}` : ''} · </span>}
            {t.geography && <span>{t.geography} · </span>}
            {t.focus && <span>{t.focus}</span>}
          </div>
          {t.budget_target_pct != null && (
            <div style={{ marginTop: 4 }}>
              <span style={{ background: '#1f6feb33', color: '#58a6ff', padding: '1px 6px', borderRadius: 3, fontSize: 11 }}>
                {t.budget_target_pct}% allocation
              </span>
            </div>
          )}
        </div>
      ))}
      {detail.fx_rate && (
        <div style={{ color: '#8b949e', fontSize: 11, marginTop: 4 }}>
          FX Rate: {detail.fx_rate} JPY/USD
        </div>
      )}
    </div>
  );
}

function formatCritique(detail) {
  const critique = detail.critique || detail;
  if (!critique || (!critique.issues && !critique.verdict)) return null;
  const issues = critique.issues || [];
  const strengths = critique.strengths || [];
  return (
    <div>
      <div style={{ fontWeight: 600, marginBottom: 6, color: '#d2a8ff' }}>
        Critique {detail.round ? `Round ${detail.round}` : ''}
      </div>
      {critique.verdict && (
        <div style={{ marginBottom: 6 }}>
          <span style={{
            padding: '2px 8px', borderRadius: 3, fontSize: 11, fontWeight: 600,
            background: critique.verdict === 'approve' ? '#23863633' : '#d2992233',
            color: critique.verdict === 'approve' ? '#3fb950' : '#d29922',
          }}>
            Verdict: {critique.verdict}
          </span>
        </div>
      )}
      {issues.length > 0 && (
        <div style={{ marginBottom: 6 }}>
          <div style={{ color: '#f85149', fontSize: 11, fontWeight: 600, marginBottom: 3 }}>Issues</div>
          {issues.map((iss, i) => (
            <div key={i} style={{ padding: '3px 6px', marginBottom: 2, background: '#0d1117', borderRadius: 3, fontSize: 11, color: '#e1e4e8' }}>
              {iss.ticker && <strong>{iss.ticker}: </strong>}
              {iss.concern || iss.issue}
              {iss.severity && (
                <span style={{
                  marginLeft: 6, padding: '0 4px', borderRadius: 2, fontSize: 10,
                  background: iss.severity === 'high' ? '#f8514933' : '#d2992233',
                  color: iss.severity === 'high' ? '#f85149' : '#d29922',
                }}>
                  {iss.severity}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
      {strengths.length > 0 && (
        <div>
          <div style={{ color: '#3fb950', fontSize: 11, fontWeight: 600, marginBottom: 3 }}>Strengths</div>
          {strengths.map((s, i) => (
            <div key={i} style={{ color: '#8b949e', fontSize: 11, padding: '2px 6px' }}>+ {s}</div>
          ))}
        </div>
      )}
      {critique.suggested_adjustments && Object.keys(critique.suggested_adjustments).length > 0 && (
        <div style={{ marginTop: 4 }}>
          <div style={{ color: '#58a6ff', fontSize: 11, fontWeight: 600, marginBottom: 2 }}>Suggested Adjustments</div>
          {Object.entries(critique.suggested_adjustments).map(([ticker, adj]) => (
            <div key={ticker} style={{ fontSize: 11, color: '#e1e4e8', padding: '2px 6px' }}>
              {ticker}: {typeof adj === 'object' ? JSON.stringify(adj) : String(adj)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function formatPortfolio(detail) {
  // detail might be the portfolio_draft itself or contain it
  const draft = detail.portfolio_draft || detail;
  const holdings = draft.holdings || [];
  if (!Array.isArray(holdings) || holdings.length === 0) return null;

  const totalPct = holdings.reduce((s, h) => s + (h.allocation_pct || h.pct || 0), 0);

  return (
    <div>
      <div style={{ fontWeight: 600, marginBottom: 6, color: '#d2a8ff' }}>Portfolio Holdings</div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
        <thead>
          <tr style={{ borderBottom: '1px solid #30363d', color: '#8b949e' }}>
            <th style={{ padding: '4px 6px', textAlign: 'left' }}>Ticker</th>
            <th style={{ padding: '4px 6px', textAlign: 'right' }}>Alloc %</th>
            <th style={{ padding: '4px 6px', textAlign: 'left' }}>Confidence</th>
            <th style={{ padding: '4px 6px', textAlign: 'right' }}>Return</th>
          </tr>
        </thead>
        <tbody>
          {holdings.map((h, i) => (
            <tr key={i} style={{ borderBottom: '1px solid #21262d' }}>
              <td style={{ padding: '3px 6px', fontWeight: 600, color: '#e1e4e8' }}>{h.ticker || '?'}</td>
              <td style={{ padding: '3px 6px', textAlign: 'right', color: '#58a6ff' }}>
                {h.allocation_pct ?? h.pct ?? 0}%
              </td>
              <td style={{ padding: '3px 6px', color: '#8b949e' }}>{h.confidence || ''}</td>
              <td style={{ padding: '3px 6px', textAlign: 'right', color: '#3fb950' }}>
                {h.base_return_pct ? `${h.base_return_pct}%` : h.expected_return ? `${h.expected_return}%` : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {draft.fx_rate && (
        <div style={{ color: '#8b949e', fontSize: 10, marginTop: 4 }}>
          FX Rate: {draft.fx_rate} JPY/USD | Total: {totalPct.toFixed(1)}%
        </div>
      )}
      {draft.revision_notes && (
        <div style={{ color: '#d29922', fontSize: 11, marginTop: 4, padding: '4px 6px', background: '#0d1117', borderRadius: 3 }}>
          {draft.revision_notes}
        </div>
      )}
    </div>
  );
}

function formatTiebreaker(detail) {
  const verdict = detail.verdict || (detail.critique && detail.critique.verdict);
  const finalPortfolio = detail.final_portfolio;
  return (
    <div>
      {verdict && (
        <div style={{ marginBottom: 6 }}>
          <span style={{
            padding: '2px 8px', borderRadius: 3, fontSize: 12, fontWeight: 600,
            background: verdict === 'approve' ? '#23863633' : '#d2992233',
            color: verdict === 'approve' ? '#3fb950' : '#d29922',
          }}>
            {verdict === 'approve' ? '✓ APPROVED' : '↻ REVISE'}
          </span>
        </div>
      )}
      {detail.reasoning && (
        <div style={{ color: '#8b949e', fontSize: 11, marginTop: 4 }}>{detail.reasoning}</div>
      )}
      {finalPortfolio && formatPortfolio({ portfolio_draft: finalPortfolio })}
    </div>
  );
}

function formatMacroBrief(detail) {
  if (!detail || typeof detail !== 'object') return null;
  // Unwrap {macro_brief: {...}} if that's the shape
  const brief = detail.macro_brief || detail;
  const sections = [];
  for (const [key, value] of Object.entries(brief)) {
    if (key === '_prompt' || key === '_user_message' || key === '_response_text') continue;
    const label = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    const val = typeof value === 'string' ? value : JSON.stringify(value);
    sections.push({ label, value: val });
  }
  if (sections.length === 0) return null;
  return (
    <div>
      <div style={{ fontWeight: 600, marginBottom: 6, color: '#d2a8ff' }}>Macro Brief</div>
      {sections.map((s, i) => (
        <div key={i} style={{ marginBottom: 4, fontSize: 11 }}>
          <span style={{ color: '#8b949e' }}>{s.label}: </span>
          <span style={{ color: '#e1e4e8' }}>{s.value}</span>
        </div>
      ))}
    </div>
  );
}

// ── Main formatter dispatcher ────────────────────────────────────

function smartFormatDetail(detail, agent) {
  if (!detail) return null;

  // Based on the agent, try appropriate formatters
  if (agent === 'B') {
    // Could be tasks (planning phase) or portfolio (draft/revision)
    const tasks = detail.tasks || (detail.research_tasks) || [];
    const holdings = detail.holdings || (detail.portfolio_draft && detail.portfolio_draft.holdings) || [];
    if (Array.isArray(tasks) && tasks.length > 0 && !Array.isArray(holdings)) {
      return formatTasks(detail);
    }
    if (Array.isArray(holdings) && holdings.length > 0) {
      return formatPortfolio(detail);
    }
    // Fallback: maybe detail has tasks inside
    if (detail.tasks && Array.isArray(detail.tasks)) {
      return formatTasks(detail);
    }
  }

  if (agent === 'C') return formatCritique(detail);

  if (agent === 'D') return formatTiebreaker(detail);

  if (agent === 'M') return formatMacroBrief(detail);

  if (agent && agent.startsWith('X')) {
    // Research candidates
    if (detail.candidates && Array.isArray(detail.candidates)) {
      return formatCandidates(detail);
    }
    // Research plan submission
    if (detail.plan && typeof detail.plan === 'object' && !Array.isArray(detail.plan)) {
      return formatResearchPlan(detail.plan);
    }
    // Plan approval event — plan may be at top level
    if (detail.topic || detail.candidate_screening_criteria || detail.approach) {
      return formatResearchPlan(detail);
    }
  }

  // Generic JSON fallback
  return formatGenericJson(detail);
}

function formatCandidates(detail) {
  const candidates = detail.candidates || [];
  if (!Array.isArray(candidates) || candidates.length === 0) return null;
  return (
    <div>
      <div style={{ fontWeight: 600, marginBottom: 6, color: '#d2a8ff' }}>
        Research Candidates ({candidates.length})
      </div>
      {candidates.map((c, i) => (
        <div key={i} style={{
          marginBottom: 8, padding: '8px 10px', background: '#0d1117',
          borderRadius: 6, border: '1px solid #21262d', fontSize: 11,
        }}>
          {/* Ticker + Name + Exchange */}
          <div style={{ color: '#e1e4e8', marginBottom: 4 }}>
            <strong style={{ fontSize: 13 }}>{c.ticker || '?'}</strong>
            {c.exchange && <span style={{ color: '#8b949e', fontSize: 10, marginLeft: 4 }}>{c.exchange}</span>}
            {c.name && <span style={{ color: '#8b949e', marginLeft: 4 }}>— {c.name}</span>}
          </div>

          {/* Sector/Industry */}
          {(c.sector || c.industry || c.sub_industry) && (
            <div style={{ color: '#8b949e', marginBottom: 4 }}>
              {c.sector && <span>{c.sector}</span>}
              {(c.industry || c.sub_industry) && <span> / {c.industry || c.sub_industry}</span>}
              {c.price && <span> · Price: {c.price}</span>}
              {c.market_cap && <span> · Mkt Cap: {c.market_cap}</span>}
            </div>
          )}

          {/* Thesis — blue accent bar */}
          {c.thesis && (
            <div style={{
              marginBottom: 6, padding: '6px 8px', background: '#0c2d6b33',
              borderLeft: '3px solid #58a6ff', borderRadius: '0 4px 4px 0',
              color: '#c9d1d9', lineHeight: 1.4,
            }}>
              {c.thesis}
            </div>
          )}

          {/* Scenario grid: Bull / Base / Bear */}
          <div style={{ display: 'flex', gap: 6, marginBottom: 6 }}>
            {c.bull_case && (
              <div style={{ flex: 1, padding: '5px 6px', background: '#0d2818', borderRadius: 4, border: '1px solid #1a3a2a' }}>
                <div style={{ color: '#3fb950', fontWeight: 600, marginBottom: 2 }}>Bull {c.bull_return_pct != null ? `+${c.bull_return_pct}%` : ''}</div>
                <div style={{ color: '#8b949e', fontSize: 10, lineHeight: 1.3 }}>{c.bull_case}</div>
              </div>
            )}
            {c.base_case && (
              <div style={{ flex: 1, padding: '5px 6px', background: '#1c1c1c', borderRadius: 4, border: '1px solid #30363d' }}>
                <div style={{ color: '#e1e4e8', fontWeight: 600, marginBottom: 2 }}>Base {c.base_return_pct != null ? `${c.base_return_pct >= 0 ? '+' : ''}${c.base_return_pct}%` : ''}</div>
                <div style={{ color: '#8b949e', fontSize: 10, lineHeight: 1.3 }}>{c.base_case}</div>
              </div>
            )}
            {c.bear_case && (
              <div style={{ flex: 1, padding: '5px 6px', background: '#2d0c0c', borderRadius: 4, border: '1px solid #4a1a1a' }}>
                <div style={{ color: '#f85149', fontWeight: 600, marginBottom: 2 }}>Bear {c.bear_downside_pct != null ? `${c.bear_downside_pct}%` : ''}</div>
                <div style={{ color: '#8b949e', fontSize: 10, lineHeight: 1.3 }}>{c.bear_case}</div>
              </div>
            )}
          </div>

          {/* Confidence badge + reason */}
          <div style={{ marginBottom: 4 }}>
            {c.confidence && (
              <span style={{
                padding: '1px 5px', borderRadius: 3, fontSize: 10, fontWeight: 600,
                background: c.confidence === 'high' ? '#23863633' : c.confidence === 'medium' || c.confidence === 'medium-high' ? '#d2992233' : '#21262d',
                color: c.confidence === 'high' ? '#3fb950' : c.confidence === 'medium' || c.confidence === 'medium-high' ? '#d29922' : '#8b949e',
                marginRight: 4,
              }}>
                {c.confidence}
              </span>
            )}
            {c.confidence_reason && (
              <span style={{ color: '#8b949e', fontStyle: 'italic' }}>{c.confidence_reason}</span>
            )}
          </div>

          {/* Known catch with severity */}
          {c.known_catch && (
            <div style={{
              padding: '5px 6px', background: '#2d1c0c', borderRadius: 4,
              border: '1px solid #4a301a', marginBottom: 4,
            }}>
              <span style={{ color: '#d29922', fontWeight: 600 }}>⚠ Catch: </span>
              <span style={{ color: '#c9d1d9' }}>{c.known_catch}</span>
              {c.catch_severity && (
                <span style={{
                  marginLeft: 4, padding: '0 4px', borderRadius: 2, fontSize: 10,
                  background: c.catch_severity.toLowerCase().startsWith('high') ? '#f8514933' : c.catch_severity.toLowerCase().startsWith('moderate') ? '#d2992233' : '#21262d',
                  color: c.catch_severity.toLowerCase().startsWith('high') ? '#f85149' : c.catch_severity.toLowerCase().startsWith('moderate') ? '#d29922' : '#8b949e',
                }}>
                  {c.catch_severity}
                </span>
              )}
            </div>
          )}

          {/* Data sources */}
          {c.data_sources && Array.isArray(c.data_sources) && c.data_sources.length > 0 && (
            <div style={{ color: '#8b949e', fontSize: 10 }}>
              Sources: {c.data_sources.join(', ')}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function formatGenericJson(detail) {
  const lines = [];
  const obj = typeof detail === 'object' ? detail : {};
  for (const [key, value] of Object.entries(obj)) {
    if (key === '_prompt' || key === '_user_message' || key === '_response_text') continue;
    const label = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    if (Array.isArray(value)) {
      lines.push({ label, value: `${value.length} items`, raw: value });
    } else if (typeof value === 'object' && value !== null) {
<<<<<<< HEAD
      lines.push({ label, value: JSON.stringify(value, null, 1) });
    } else {
      lines.push({ label, value: String(value) });
=======
      lines.push({ label, value: JSON.stringify(value, null, 2), raw: value });
    } else {
      lines.push({ label, value: String(value), raw: value });
>>>>>>> worktree-feature+mf-deep-integration
    }
  }
  if (lines.length === 0) return null;
  return (
    <div>
      {lines.map((l, i) => (
        <div key={i} style={{ fontSize: 11, marginBottom: 2, color: '#8b949e' }}>
          <span style={{ color: '#8b949e' }}>{l.label}: </span>
<<<<<<< HEAD
          <span style={{
            color: '#e1e4e8', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
          }}>{l.value}</span>
=======
          <span style={{ color: '#e1e4e8', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{l.value}</span>
>>>>>>> worktree-feature+mf-deep-integration
        </div>
      ))}
    </div>
  );
}

function formatResearchPlan(detail) {
  const plan = detail.plan || detail;
  if (!plan || typeof plan !== 'object') return null;
  const topic = plan.topic || '';
  const criteria = plan.candidate_screening_criteria;
  const sources = plan.intended_sources;
  const approach = plan.approach;
  if (!topic && !criteria && !approach) return null;
  return (
    <div>
      <div style={{ fontWeight: 600, marginBottom: 6, color: '#d2a8ff' }}>Research Plan</div>
      {topic && (
        <div style={{ marginBottom: 4, fontSize: 12 }}>
          <span style={{ color: '#8b949e' }}>Topic: </span>
          <span style={{ color: '#e1e4e8', fontWeight: 600 }}>{topic}</span>
        </div>
      )}
      {criteria && (
        <div style={{ marginBottom: 4, fontSize: 11 }}>
          <span style={{ color: '#8b949e' }}>Screening: </span>
          <span style={{ color: '#58a6ff' }}>{typeof criteria === 'string' ? criteria : JSON.stringify(criteria)}</span>
        </div>
      )}
      {approach && (
        <div style={{ marginBottom: 4, fontSize: 11 }}>
          <span style={{ color: '#8b949e' }}>Approach: </span>
          <span style={{ color: '#e1e4e8' }}>{typeof approach === 'string' ? approach : JSON.stringify(approach)}</span>
        </div>
      )}
      {Array.isArray(sources) && sources.length > 0 && (
        <div style={{ marginBottom: 2, fontSize: 11 }}>
          <span style={{ color: '#8b949e' }}>Sources: </span>
          {sources.map((s, i) => (
            <span key={i} style={{
              display: 'inline-block', margin: '1px 3px 1px 0',
              padding: '0 5px', background: '#1f6feb33', color: '#58a6ff',
              borderRadius: 3, fontSize: 10,
            }}>
              {typeof s === 'string' ? s : s.name || String(s).slice(0, 60)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

// ── DetailCollapsible ────────────────────────────────────────────

function DetailCollapsible({ detail, agent }) {
  const [open, setOpen] = useState(false);
  if (!detail) return null;

  const formatted = smartFormatDetail(detail, agent);
  if (!formatted) return null;

  return (
    <div style={{ marginLeft: 24, marginTop: 4 }}>
      <button
        onClick={() => setOpen(!open)}
        style={{
          background: '#161b22', border: '1px solid #30363d', borderRadius: 4,
          color: '#8b949e', cursor: 'pointer', fontSize: 11, padding: '2px 8px',
        }}
      >
        {open ? '▼' : '▶'} {open ? 'Hide details' : 'Show details'}
      </button>
      {open && (
        <div style={{
          marginTop: 6, padding: 10, background: '#0d1117', borderRadius: 6,
          border: '1px solid #21262d', fontSize: 12, lineHeight: 1.6,
        }}>
          {formatted}
        </div>
      )}
    </div>
  );
}

function formatEventMessage(ev) {
  if (ev.message) return ev.message;
  if (ev.status === 'detail') return `— detail available for ${agentLabel(ev.agent)}`;
  return '';
}

export default function ActivityFeed({ events, agentDisplayFn }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events]);

  const displayFn = agentDisplayFn || agentLabel;

  // Group events: "detail" events attach their detail payload to the next
  // non-detail event. If an event carries its own detail field (like
  // plan_approved), use that as fallback when no pending detail exists.
  const displayEvents = [];
  let pendingDetail = null;
  let pendingDetailAgent = null;
  for (const ev of events) {
    if (ev.status === 'detail' && ev.detail) {
      pendingDetail = ev.detail;
      pendingDetailAgent = ev.agent;
      continue;
    }
    // Use the event's own detail when available (e.g. plan_approved,
    // critique verdicts), otherwise fall back to the most recent pending
    // detail from a preceding "detail" event.
    const ownDetail = ev.detail || null;
    displayEvents.push({
      ...ev,
      _detail: ownDetail || pendingDetail || null,
      _detailAgent: ev.agent,
    });
    pendingDetail = null;
    pendingDetailAgent = null;
  }

  // Determine status icon
  const icon = (ev) => {
    if (ev.status === 'retry') return '⟳';
    if (ev.status === 'working' || ev.status === 'running' || ev.status === 'in_progress') return '⟳';
    if (ev.status === 'done' || ev.status === 'completed') return '✓';
    if (ev.status === 'error') return '✗';
    if (ev.status === 'final') return '★';
    if (ev.status === 'plan_submitted') return '⟐';
    if (ev.status === 'plan_approved') return '✓';
    return '•';
  };

  const iconColor = (ev) => {
    if (ev.status === 'retry') return '#d29922';
    if (ev.status === 'working' || ev.status === 'running' || ev.status === 'in_progress') return '#58a6ff';
    if (ev.status === 'error') return '#f85149';
    if (ev.status === 'final') return '#d2a8ff';
    if (ev.status === 'plan_submitted') return '#d29922';
    if (ev.status === 'done' || ev.status === 'completed') return '#3fb950';
    return '#8b949e';
  };

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
              display: 'flex', alignItems: 'flex-start', gap: 6,
            }}>
              <span style={{ color: '#484f58', fontSize: 11, flexShrink: 0, minWidth: 115, fontVariantNumeric: 'tabular-nums' }}>
                {formatJST(ev._receivedAt)}
              </span>
              <span style={{ color: iconColor(ev), flexShrink: 0 }}>
                [{icon(ev)}]
              </span>
              <span style={{ fontWeight: 600, color: '#d2a8ff', flexShrink: 0 }}>
                {displayFn(ev.agent)}:
              </span>
              <span>{formatEventMessage(ev)}</span>
            </div>
            {(ev._detail) && (
              <DetailCollapsible detail={ev._detail} agent={ev._detailAgent || ev.agent} />
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}