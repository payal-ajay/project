import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle, XCircle } from 'lucide-react'
import { getEmissions, approveEmission, rejectEmission, getAuditLog } from '../api/client'

function scopeBadge(scope) {
  const map = { SCOPE_1: 'scope1', SCOPE_2: 'scope2', SCOPE_3: 'scope3' }
  const labels = { SCOPE_1: 'Scope 1', SCOPE_2: 'Scope 2', SCOPE_3: 'Scope 3' }
  return <span className={`badge badge-${map[scope] || 'ghost'}`}>{labels[scope] || scope}</span>
}

function sourceBadge(src) {
  return <span className={`badge badge-${(src || '').toLowerCase()}`}>{src}</span>
}

function statusBadge(status) {
  return <span className={`badge badge-${(status || '').toLowerCase()}`}>{status}</span>
}

function fmt(n) {
  if (n === null || n === undefined) return '—'
  return Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 })
}

// ── Detail modal ──────────────────────────────────────────────────────────────
function DetailModal({ record, onClose, onApprove, onReject, loading }) {
  const [tab, setTab] = useState('detail')
  const [auditLog, setAuditLog] = useState(null)
  const [rejectReason, setRejectReason] = useState('')
  const [showReject, setShowReject] = useState(false)

  useEffect(() => {
    if (tab === 'audit') {
      getAuditLog(record.id).then(d => setAuditLog(d.audit_trail || []))
    }
  }, [tab, record.id])

  const r = record

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
          <div>
            <h3 style={{ margin: 0 }}>{r.category}</h3>
            <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
              {sourceBadge(r.source_type)}
              {scopeBadge(r.scope)}
              {statusBadge(r.status)}
              {r.is_suspicious && (
                <span className="badge badge-flagged">
                  <AlertTriangle size={11} style={{ marginRight: 3 }} /> Suspicious
                </span>
              )}
            </div>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>✕</button>
        </div>

        {/* Suspicious warning */}
        {r.is_suspicious && r.suspicion_reason && (
          <div className="alert alert-info" style={{ marginBottom: 14, fontSize: 12 }}>
            <AlertTriangle size={12} style={{ verticalAlign: 'middle', marginRight: 4 }} />
            <strong>Anomaly flag: </strong>{r.suspicion_reason}
          </div>
        )}

        {/* Tabs */}
        <div className="tabs">
          <button className={`tab ${tab === 'detail' ? 'active' : ''}`} onClick={() => setTab('detail')}>Details</button>
          <button className={`tab ${tab === 'audit' ? 'active' : ''}`} onClick={() => setTab('audit')}>Audit Trail</button>
        </div>

        {/* Detail tab */}
        {tab === 'detail' && (
          <div className="detail-grid">
            <div className="detail-item">
              <label>Activity</label>
              <span style={{ fontSize: 12 }}>{r.activity_description}</span>
            </div>
            <div className="detail-item">
              <label>Date</label>
              <span>{r.activity_date}</span>
            </div>
            {r.period_start && (
              <div className="detail-item">
                <label>Billing period</label>
                <span style={{ fontSize: 12 }}>{r.period_start} → {r.period_end}</span>
              </div>
            )}
            <div className="detail-item">
              <label>Quantity</label>
              <span>{fmt(r.quantity)} {r.unit}</span>
            </div>
            <div className="detail-item">
              <label>CO₂e (kg)</label>
              <span style={{ color: '#dc2626', fontWeight: 600 }}>
                {r.quantity_co2e_kg ? fmt(r.quantity_co2e_kg) + ' kg' : '—'}
              </span>
            </div>
            <div className="detail-item">
              <label>Emission factor</label>
              <span style={{ fontSize: 11 }}>{r.emission_factor_used || '—'}</span>
            </div>
            <div className="detail-item">
              <label>Factor source</label>
              <span style={{ fontSize: 12 }}>{r.emission_factor_source || '—'}</span>
            </div>
            <div className="detail-item">
              <label>Facility / entity</label>
              <span>{r.facility_or_entity || '—'}</span>
            </div>
            {r.origin_iata && (
              <div className="detail-item">
                <label>Route</label>
                <span>{r.origin_iata} → {r.destination_iata} ({fmt(r.distance_km)} km)</span>
              </div>
            )}
            {r.travel_class && (
              <div className="detail-item">
                <label>Class</label>
                <span>{r.travel_class}</span>
              </div>
            )}
            <div className="detail-item">
              <label>Batch ID</label>
              <span style={{ fontSize: 11, fontFamily: 'monospace' }}>{r.batch_id}</span>
            </div>
          </div>
        )}

        {/* Audit trail tab */}
        {tab === 'audit' && (
          <div>
            {!auditLog
              ? <p className="text-muted">Loading…</p>
              : auditLog.length === 0
                ? <p className="text-muted" style={{ textAlign: 'center', padding: 24 }}>
                    No edits recorded yet
                  </p>
                : <table>
                    <thead>
                      <tr>
                        <th>Field</th>
                        <th>Before</th>
                        <th>After</th>
                        <th>When</th>
                        <th>Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {auditLog.map((log, i) => (
                        <tr key={i}>
                          <td style={{ fontWeight: 500 }}>{log.field}</td>
                          <td style={{ color: '#dc2626', fontFamily: 'monospace', fontSize: 11 }}>{log.old_value}</td>
                          <td style={{ color: '#16a34a', fontFamily: 'monospace', fontSize: 11 }}>{log.new_value}</td>
                          <td style={{ fontSize: 11, color: '#6b7280' }}>{new Date(log.changed_at).toLocaleString()}</td>
                          <td style={{ fontSize: 11, color: '#6b7280' }}>{log.reason || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
            }
          </div>
        )}

        {/* Actions */}
        {!r.is_locked && (
          <div className="modal-footer">
            {showReject ? (
              <>
                <input
                  placeholder="Reason for rejection (optional)"
                  value={rejectReason}
                  onChange={e => setRejectReason(e.target.value)}
                  style={{ flex: 1, padding: '7px 12px', border: '1px solid #e5e7eb', borderRadius: 7, fontSize: 13 }}
                />
                <button className="btn btn-danger" disabled={loading} onClick={() => onReject(r.id, rejectReason)}>
                  Confirm Reject
                </button>
                <button className="btn btn-ghost" onClick={() => setShowReject(false)}>Cancel</button>
              </>
            ) : (
              <>
                <button className="btn btn-ghost btn-sm" onClick={() => setShowReject(true)} disabled={loading}>
                  <XCircle size={14} /> Reject
                </button>
                <button className="btn btn-primary btn-sm" onClick={() => onApprove(r.id)} disabled={loading}>
                  <CheckCircle size={14} /> Approve
                </button>
              </>
            )}
          </div>
        )}
        {r.is_locked && (
          <div style={{ textAlign: 'right', marginTop: 16, fontSize: 12, color: '#16a34a' }}>
            🔒 Locked — approved for audit
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function ReviewQueue() {
  const [records, setRecords] = useState([])
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState(false)
  const [selected, setSelected] = useState(null)
  const [filters, setFilters] = useState({ status: '', scope: '', source_type: '', suspicious: '' })
  const [toast, setToast] = useState(null)

  function showToast(msg, type = 'success') {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3000)
  }

  async function load() {
    setLoading(true)
    try {
      const data = await getEmissions(filters)
      setRecords(data.results || [])
    } catch {
      setRecords([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [filters])

  async function handleApprove(id) {
    setActionLoading(true)
    try {
      await approveEmission(id)
      showToast('Record approved and locked for audit')
      setSelected(null)
      load()
    } catch {
      showToast('Approve failed', 'error')
    } finally {
      setActionLoading(false)
    }
  }

  async function handleReject(id, reason) {
    setActionLoading(true)
    try {
      await rejectEmission(id, reason)
      showToast('Record rejected')
      setSelected(null)
      load()
    } catch {
      showToast('Reject failed', 'error')
    } finally {
      setActionLoading(false)
    }
  }

  const setFilter = (k, v) => setFilters(f => ({ ...f, [k]: v }))
  const pendingCount = records.filter(r => r.status === 'PENDING').length
  const suspiciousCount = records.filter(r => r.is_suspicious).length

  // Build export URLs with current filters applied
  const exportParams = new URLSearchParams()
  if (filters.status) exportParams.set('status', filters.status)
  if (filters.source_type) exportParams.set('source_type', filters.source_type)
  const exportQuery = exportParams.toString() ? `?${exportParams.toString()}` : ''

  return (
    <div>
      <div className="page-header">
        <h2>Review Queue</h2>
        <p>Review ingested emission records, flag issues, and approve for audit</p>
      </div>

      {/* Toast */}
      {toast && (
        <div className={`alert alert-${toast.type === 'error' ? 'error' : 'success'}`} style={{ marginBottom: 16 }}>
          {toast.msg}
        </div>
      )}

      {/* Summary bar */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
        <div className="stat-card" style={{ flex: 1, padding: '12px 16px' }}>
          <div className="label">Pending</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: '#d97706' }}>{pendingCount}</div>
        </div>
        <div className="stat-card" style={{ flex: 1, padding: '12px 16px' }}>
          <div className="label">Flagged</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: '#b45309' }}>{suspiciousCount}</div>
        </div>
        <div className="stat-card" style={{ flex: 1, padding: '12px 16px' }}>
          <div className="label">Total shown</div>
          <div style={{ fontSize: 22, fontWeight: 700 }}>{records.length}</div>
        </div>
      </div>

      {/* Filter bar + export buttons */}
      <div className="filter-bar">
        <select value={filters.status} onChange={e => setFilter('status', e.target.value)}>
          <option value="">All statuses</option>
          <option value="PENDING">Pending</option>
          <option value="APPROVED">Approved</option>
          <option value="REJECTED">Rejected</option>
          <option value="FLAGGED">Flagged</option>
        </select>
        <select value={filters.scope} onChange={e => setFilter('scope', e.target.value)}>
          <option value="">All scopes</option>
          <option value="SCOPE_1">Scope 1</option>
          <option value="SCOPE_2">Scope 2</option>
          <option value="SCOPE_3">Scope 3</option>
        </select>
        <select value={filters.source_type} onChange={e => setFilter('source_type', e.target.value)}>
          <option value="">All sources</option>
          <option value="SAP">SAP</option>
          <option value="UTILITY">Utility</option>
          <option value="TRAVEL">Travel</option>
        </select>
        <select value={filters.suspicious} onChange={e => setFilter('suspicious', e.target.value)}>
          <option value="">All records</option>
          <option value="true">Suspicious only</option>
          <option value="false">Clean only</option>
        </select>
        <button className="btn btn-ghost btn-sm" onClick={load}>Refresh</button>

        {/* Export buttons */}
        <a
          href={`/api/analyst/export/csv/${exportQuery}`}
          style={{
            padding: '4px 12px', borderRadius: 7,
            background: '#f0fdf4', color: '#16a34a',
            border: '1px solid #86efac', fontSize: 12,
            fontWeight: 500, textDecoration: 'none',
            display: 'inline-flex', alignItems: 'center', gap: 4,
          }}
        >
          ⬇ Export CSV
        </a>
        <a
          href={`/api/analyst/export/json/${exportQuery}`}
          style={{
            padding: '4px 12px', borderRadius: 7,
            background: '#eff6ff', color: '#2563eb',
            border: '1px solid #93c5fd', fontSize: 12,
            fontWeight: 500, textDecoration: 'none',
            display: 'inline-flex', alignItems: 'center', gap: 4,
          }}
        >
          ⬇ Export JSON
        </a>
      </div>

      {/* Table */}
      <div className="card" style={{ padding: 0 }}>
        <div className="table-wrap">
          {loading ? (
            <div className="empty-state"><p>Loading…</p></div>
          ) : records.length === 0 ? (
            <div className="empty-state">
              <p>No records match the current filters.</p>
              <p style={{ marginTop: 8 }}>Upload data from the Upload page to get started.</p>
            </div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th></th>
                  <th>Category</th>
                  <th>Source</th>
                  <th>Scope</th>
                  <th>Date</th>
                  <th>Quantity</th>
                  <th>CO₂e (kg)</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {records.map(r => (
                  <tr
                    key={r.id}
                    className={r.is_suspicious ? 'suspicious' : ''}
                    style={{ cursor: 'pointer' }}
                    onClick={() => setSelected(r)}
                  >
                    <td style={{ width: 20 }}>
                      {r.is_suspicious && <AlertTriangle size={13} className="suspicious-icon" />}
                    </td>
                    <td>
                      <div style={{ fontWeight: 500, fontSize: 13 }}>{r.category}</div>
                      {r.facility_or_entity && (
                        <div style={{ fontSize: 11, color: '#9ca3af' }}>{r.facility_or_entity}</div>
                      )}
                    </td>
                    <td>{sourceBadge(r.source_type)}</td>
                    <td>{scopeBadge(r.scope)}</td>
                    <td style={{ fontSize: 12, color: '#6b7280' }}>{r.activity_date}</td>
                    <td style={{ fontFamily: 'monospace', fontSize: 12 }}>
                      {fmt(r.quantity)} {r.unit}
                    </td>
                    <td style={{ fontFamily: 'monospace', fontSize: 12, color: r.quantity_co2e_kg ? '#dc2626' : '#9ca3af' }}>
                      {r.quantity_co2e_kg ? fmt(r.quantity_co2e_kg) : '—'}
                    </td>
                    <td>{statusBadge(r.status)}</td>
                    <td onClick={e => e.stopPropagation()}>
                      {!r.is_locked && r.status === 'PENDING' && (
                        <div style={{ display: 'flex', gap: 4 }}>
                          <button
                            className="btn btn-primary btn-sm"
                            onClick={e => { e.stopPropagation(); handleApprove(r.id) }}
                            disabled={actionLoading}
                          >✓</button>
                          <button
                            className="btn btn-danger btn-sm"
                            onClick={e => { e.stopPropagation(); setSelected(r) }}
                            disabled={actionLoading}
                          >✗</button>
                        </div>
                      )}
                      {r.is_locked && <span style={{ fontSize: 11, color: '#16a34a' }}>🔒</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Detail modal */}
      {selected && (
        <DetailModal
          record={selected}
          onClose={() => setSelected(null)}
          onApprove={handleApprove}
          onReject={handleReject}
          loading={actionLoading}
        />
      )}
    </div>
  )
}