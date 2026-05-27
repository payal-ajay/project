// api/client.js — all calls to the Django backend

const BASE = '/api'

// ── Ingestion ────────────────────────────────────────────────────────────────

export async function uploadFile(sourceType, file) {
  const form = new FormData()
  form.append('file', file)
  const endpointMap = { SAP: 'sap', UTILITY: 'utility', TRAVEL: 'travel' }
  const res = await fetch(`${BASE}/ingestion/upload/${endpointMap[sourceType]}/`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`)
  return res.json()
}

// ── Emissions ────────────────────────────────────────────────────────────────

export async function getEmissions(filters = {}) {
  const params = new URLSearchParams()
  if (filters.status)      params.set('status', filters.status)
  if (filters.scope)       params.set('scope', filters.scope)
  if (filters.source_type) params.set('source_type', filters.source_type)
  if (filters.suspicious)  params.set('suspicious', filters.suspicious)
  const res = await fetch(`${BASE}/analyst/emissions/?${params}`)
  if (!res.ok) throw new Error('Failed to fetch emissions')
  return res.json()
}

export async function getEmission(id) {
  const res = await fetch(`${BASE}/analyst/emissions/${id}/`)
  if (!res.ok) throw new Error('Not found')
  return res.json()
}

export async function approveEmission(id) {
  const res = await fetch(`${BASE}/analyst/emissions/${id}/approve/`, { method: 'POST' })
  if (!res.ok) throw new Error('Approve failed')
  return res.json()
}

export async function rejectEmission(id, reason = '') {
  const res = await fetch(`${BASE}/analyst/emissions/${id}/reject/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  })
  if (!res.ok) throw new Error('Reject failed')
  return res.json()
}

export async function getAuditLog(id) {
  const res = await fetch(`${BASE}/analyst/emissions/${id}/audit/`)
  if (!res.ok) throw new Error('Audit log failed')
  return res.json()
}

export async function editEmission(id, fields) {
  const res = await fetch(`${BASE}/analyst/emissions/${id}/`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fields),
  })
  if (!res.ok) throw new Error('Edit failed')
  return res.json()
}
