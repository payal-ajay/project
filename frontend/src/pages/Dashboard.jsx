import { useEffect, useState } from 'react'
import { BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { getEmissions } from '../api/client'
import { AlertTriangle } from 'lucide-react'

const SCOPE_COLORS = { SCOPE_1: '#e11d48', SCOPE_2: '#2563eb', SCOPE_3: '#7c3aed' }
const SOURCE_COLORS = { SAP: '#7c3aed', UTILITY: '#2563eb', TRAVEL: '#059669' }
const STATUS_COLORS = { PENDING: '#d97706', APPROVED: '#16a34a', REJECTED: '#dc2626', FLAGGED: '#b45309' }

function scopeLabel(s) {
  return { SCOPE_1: 'Scope 1', SCOPE_2: 'Scope 2', SCOPE_3: 'Scope 3' }[s] || s
}

export default function Dashboard() {
  const [records, setRecords] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getEmissions()
      .then(d => setRecords(d.results || []))
      .catch(() => setRecords([]))
      .finally(() => setLoading(false))
  }, [])

  // Derived stats
  const total = records.length
  const pending = records.filter(r => r.status === 'PENDING').length
  const approved = records.filter(r => r.status === 'APPROVED').length
  const suspicious = records.filter(r => r.is_suspicious).length
  const totalCO2 = records.reduce((s, r) => s + (r.quantity_co2e_kg || 0), 0)

  // Scope breakdown for pie chart
  const scopeData = ['SCOPE_1', 'SCOPE_2', 'SCOPE_3'].map(s => ({
    name: scopeLabel(s),
    value: records.filter(r => r.scope === s).length,
    co2: records.filter(r => r.scope === s).reduce((sum, r) => sum + (r.quantity_co2e_kg || 0), 0),
  })).filter(d => d.value > 0)

  // Source breakdown for bar chart
  const sourceData = ['SAP', 'UTILITY', 'TRAVEL'].map(src => ({
    name: src,
    records: records.filter(r => r.source_type === src).length,
    co2: Math.round(records.filter(r => r.source_type === src).reduce((s, r) => s + (r.quantity_co2e_kg || 0), 0)),
  })).filter(d => d.records > 0)

  // Status breakdown
  const statusData = ['PENDING', 'APPROVED', 'REJECTED', 'FLAGGED'].map(s => ({
    name: s.charAt(0) + s.slice(1).toLowerCase(),
    value: records.filter(r => r.status === s).length,
    fill: STATUS_COLORS[s],
  })).filter(d => d.value > 0)

  if (loading) return <div className="empty-state"><p>Loading dashboard…</p></div>

  return (
    <div>
      <div className="page-header">
        <h2>Dashboard</h2>
        <p>Overview of all ingested emission records across sources</p>
      </div>

      {/* Stat cards */}
      <div className="stats-row">
        <div className="stat-card">
          <div className="label">Total Records</div>
          <div className="value">{total}</div>
          <div className="sub">across all sources</div>
        </div>
        <div className="stat-card">
          <div className="label">Pending Review</div>
          <div className="value" style={{ color: '#d97706' }}>{pending}</div>
          <div className="sub">{total ? Math.round(pending / total * 100) : 0}% of total</div>
        </div>
        <div className="stat-card">
          <div className="label">Approved</div>
          <div className="value" style={{ color: '#16a34a' }}>{approved}</div>
          <div className="sub">locked for audit</div>
        </div>
        <div className="stat-card">
          <div className="label">Total CO₂e</div>
          <div className="value" style={{ fontSize: 22 }}>{(totalCO2 / 1000).toFixed(1)}</div>
          <div className="sub">tonnes CO₂e (calculated)</div>
        </div>
      </div>

      {/* Suspicious alert */}
      {suspicious > 0 && (
        <div className="alert alert-info" style={{ marginBottom: 20 }}>
          <strong><AlertTriangle size={14} style={{ verticalAlign: 'middle', marginRight: 6 }} />
          {suspicious} record{suspicious > 1 ? 's' : ''} flagged as suspicious</strong> — review these first in the queue.
        </div>
      )}

      {/* Charts */}
      <div className="charts-row">
        <div className="card">
          <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16, color: '#374151' }}>
            Scope breakdown (records)
          </h3>
          {scopeData.length === 0
            ? <div className="empty-state" style={{ padding: 24 }}>No data yet — upload files to begin</div>
            : <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie data={scopeData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}>
                    {scopeData.map((entry, i) => (
                      <Cell key={i} fill={SCOPE_COLORS['SCOPE_' + (i + 1)] || '#888'} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v, n) => [v + ' records', n]} />
                </PieChart>
              </ResponsiveContainer>
          }
        </div>

        <div className="card">
          <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16, color: '#374151' }}>
            Records by source
          </h3>
          {sourceData.length === 0
            ? <div className="empty-state" style={{ padding: 24 }}>No data yet</div>
            : <ResponsiveContainer width="100%" height={220}>
                <BarChart data={sourceData}>
                  <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} />
                  <Tooltip />
                  <Bar dataKey="records" name="Records" radius={[4,4,0,0]}>
                    {sourceData.map((entry, i) => (
                      <Cell key={i} fill={SOURCE_COLORS[entry.name] || '#888'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
          }
        </div>
      </div>

      {/* CO2 by source */}
      <div className="charts-row">
        <div className="card">
          <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16, color: '#374151' }}>
            CO₂e (kg) by source
          </h3>
          {sourceData.length === 0
            ? <div className="empty-state" style={{ padding: 24 }}>No data yet</div>
            : <ResponsiveContainer width="100%" height={200}>
                <BarChart data={sourceData}>
                  <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} />
                  <Tooltip formatter={v => [v.toLocaleString() + ' kg', 'CO₂e']} />
                  <Bar dataKey="co2" name="CO₂e (kg)" radius={[4,4,0,0]}>
                    {sourceData.map((entry, i) => (
                      <Cell key={i} fill={SOURCE_COLORS[entry.name] || '#888'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
          }
        </div>

        <div className="card">
          <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16, color: '#374151' }}>
            Review status
          </h3>
          {statusData.length === 0
            ? <div className="empty-state" style={{ padding: 24 }}>No data yet</div>
            : <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie data={statusData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={75} label={({ name, value }) => `${name}: ${value}`}>
                    {statusData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
          }
        </div>
      </div>
    </div>
  )
}
