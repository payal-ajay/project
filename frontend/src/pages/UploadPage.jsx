import { useState, useRef } from 'react'
import { Upload, FileText, Zap, Plane } from 'lucide-react'
import { uploadFile } from '../api/client'

const SOURCES = [
  {
    key: 'SAP',
    label: 'SAP Flat File',
    icon: FileText,
    color: '#7c3aed',
    bg: '#ede9fe',
    accept: '.csv,.txt',
    desc: 'ME2M / MB51 transaction export (CSV, semicolon-separated)',
    detail: 'Handles German column headers (Buchungsdatum, Werk, Warengruppe), plant codes, and date formats DD.MM.YYYY',
  },
  {
    key: 'UTILITY',
    label: 'Utility Portal CSV',
    icon: Zap,
    color: '#2563eb',
    bg: '#dbeafe',
    accept: '.csv',
    desc: 'Portal export from National Grid, ComEd, PG&E, or similar',
    detail: 'Handles billing periods that don\'t align to calendar months, multiple meters, and mixed units (kWh, MWh, therms)',
  },
  {
    key: 'TRAVEL',
    label: 'Corporate Travel JSON',
    icon: Plane,
    color: '#059669',
    bg: '#d1fae5',
    accept: '.json',
    desc: 'Concur / Navan API export (flights, hotels, ground transport)',
    detail: 'Calculates distances from IATA codes via Haversine formula. Applies DEFRA 2023 emission factors per class.',
  },
]

function UploadCard({ source, onResult }) {
  const [dragging, setDragging] = useState(false)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const inputRef = useRef()

  const Icon = source.icon

  async function handleFile(file) {
    if (!file) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const data = await uploadFile(source.key, file)
      setResult(data)
      onResult(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  function onDrop(e) {
    e.preventDefault()
    setDragging(false)
    handleFile(e.dataTransfer.files[0])
  }

  return (
    <div className="card" style={{ marginBottom: 20 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
        <div style={{
          width: 40, height: 40, borderRadius: 10,
          background: source.bg, display: 'flex', alignItems: 'center', justifyContent: 'center'
        }}>
          <Icon size={20} color={source.color} />
        </div>
        <div>
          <div style={{ fontWeight: 600, fontSize: 15 }}>{source.label}</div>
          <div style={{ fontSize: 12, color: '#6b7280' }}>{source.desc}</div>
        </div>
      </div>

      {/* Detail note */}
      <div style={{ background: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: 7, padding: '8px 12px', fontSize: 12, color: '#6b7280', marginBottom: 14 }}>
        {source.detail}
      </div>

      {/* Drop zone */}
      <div
        className={`upload-zone ${dragging ? 'drag' : ''}`}
        onClick={() => inputRef.current.click()}
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        style={{ padding: 28 }}
      >
        <Upload size={28} style={{ margin: '0 auto 10px', display: 'block', color: '#9ca3af' }} />
        <p>Drop file here or <strong style={{ color: source.color }}>browse</strong></p>
        <span style={{ display: 'block', marginTop: 4 }}>Accepts: {source.accept}</span>
        <input
          ref={inputRef}
          type="file"
          accept={source.accept}
          style={{ display: 'none' }}
          onChange={e => handleFile(e.target.files[0])}
        />
      </div>

      {/* States */}
      {loading && (
        <div className="alert alert-info" style={{ marginTop: 14 }}>
          ⏳ Uploading and running AI analysis…
        </div>
      )}
      {result && (
        <div className="alert alert-success" style={{ marginTop: 14 }}>
          <strong>✓ {result.rows_ingested} records ingested</strong>
          {result.errors > 0 && ` · ${result.errors} parse warnings`}
          {result.summary && (
            <div className="llm-box" style={{ marginTop: 10, marginBottom: 0 }}>
              <strong>AI summary: </strong>{result.summary}
            </div>
          )}
        </div>
      )}
      {error && (
        <div className="alert alert-error" style={{ marginTop: 14 }}>
          ✗ {error}
        </div>
      )}
    </div>
  )
}

export default function UploadPage() {
  const [results, setResults] = useState([])

  return (
    <div>
      <div className="page-header">
        <h2>Upload Data</h2>
        <p>Ingest emission data from SAP, utility portals, or corporate travel platforms</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 0 }}>
        <div style={{ gridColumn: '1 / -1' }}>
          {SOURCES.map(s => (
            <UploadCard
              key={s.key}
              source={s}
              onResult={r => setResults(prev => [{ source: s.key, ...r }, ...prev])}
            />
          ))}
        </div>
      </div>

      {results.length > 0 && (
        <div className="card">
          <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 14 }}>Upload history (this session)</h3>
          <table>
            <thead>
              <tr>
                <th>Source</th>
                <th>Batch ID</th>
                <th>Rows Ingested</th>
                <th>Errors</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r, i) => (
                <tr key={i}>
                  <td><span className={`badge badge-${r.source.toLowerCase()}`}>{r.source}</span></td>
                  <td style={{ fontFamily: 'monospace', fontSize: 11 }}>{r.batch_id?.slice(0, 16)}…</td>
                  <td>{r.rows_ingested}</td>
                  <td style={{ color: r.errors > 0 ? '#d97706' : '#9ca3af' }}>{r.errors}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
