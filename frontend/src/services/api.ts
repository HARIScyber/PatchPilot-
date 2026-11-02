import {
  Project,
  FileItem,
  Finding,
  RepairPlan,
  Patch,
  GeneratedTest,
  VerificationRun,
  AuditEvent,
  EvidenceReport,
} from '../types';

const configuredApiBase = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '');
const BASE_URL = configuredApiBase ? `${configuredApiBase}/api` : '/api';

export class ApiError extends Error {
  constructor(message: string, public readonly errorCode?: string, public readonly status?: number) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const response = await fetch(input, init);
  if (!response.ok) {
    let payload: any = {};
    try { payload = await response.clone().json(); } catch { /* response had no JSON body */ }
    const detail = payload.message || payload.detail || `Request failed (HTTP ${response.status})`;
    throw new ApiError(detail, payload.error_code, response.status);
  }
  return response;
}

export async function fetchHealth(): Promise<any> {
  const res = await request(`${BASE_URL}/health`);
  return res.json();
}

export async function fetchEvaluationResults(): Promise<any> {
  const res = await request(`${BASE_URL}/evaluation/results`);
  if (!res.ok) throw new Error(`Evaluation report failed (HTTP ${res.status})`);
  return res.json();
}

export async function listProjects(): Promise<Project[]> {
  const res = await request(`${BASE_URL}/projects/`);
  return res.json();
}

export async function createProject(data: { name: string; bug_description?: string; stack_trace?: string }): Promise<Project> {
  const res = await request(`${BASE_URL}/projects/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return res.json();
}

export async function loadSampleProject(): Promise<Project> {
  const res = await request(`${BASE_URL}/projects/load-sample`, { method: 'POST' });
  return res.json();
}

export async function uploadZip(projectId: string, file: File): Promise<any> {
  const formData = new FormData();
  formData.append('file', file);
  const res = await request(`${BASE_URL}/projects/${projectId}/upload`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Upload failed');
  }
  return res.json();
}

export async function fetchProjectFiles(projectId: string): Promise<FileItem[]> {
  const res = await request(`${BASE_URL}/projects/${projectId}/files`);
  return res.json();
}

export async function fetchFileContent(projectId: string, path: string): Promise<{ path: string; content: string; truncated: boolean }> {
  const res = await request(`${BASE_URL}/projects/${projectId}/files/content?path=${encodeURIComponent(path)}`);
  return res.json();
}

export async function runStaticAnalysis(projectId: string): Promise<{ status: string; findings_count: number; findings: Finding[] }> {
  const res = await request(`${BASE_URL}/projects/${projectId}/analyze`, { method: 'POST' });
  return res.json();
}

export async function fetchFindings(projectId: string): Promise<Finding[]> {
  const res = await request(`${BASE_URL}/projects/${projectId}/findings`);
  return res.json();
}

export async function generateRepairPlan(projectId: string, findingId?: string): Promise<RepairPlan> {
  const res = await request(`${BASE_URL}/projects/${projectId}/repair-plan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ finding_id: findingId }),
  });
  return res.json();
}

export async function generatePatch(projectId: string, planId?: string, targetFile?: string): Promise<Patch> {
  const res = await request(`${BASE_URL}/projects/${projectId}/patches/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ plan_id: planId, target_file: targetFile }),
  });
  return res.json();
}

export async function listPatches(projectId: string): Promise<Patch[]> {
  const res = await request(`${BASE_URL}/projects/${projectId}/patches`);
  return res.json();
}

export async function approvePatch(patchId: string): Promise<any> {
  const res = await request(`${BASE_URL}/patches/${patchId}/approve`, { method: 'POST' });
  return res.json();
}

export async function rejectPatch(patchId: string): Promise<any> {
  const res = await request(`${BASE_URL}/patches/${patchId}/reject`, { method: 'POST' });
  return res.json();
}

export async function applyPatch(patchId: string): Promise<any> {
  const res = await request(`${BASE_URL}/patches/${patchId}/apply`, { method: 'POST' });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Apply failed');
  }
  return res.json();
}

export async function generateTests(patchId: string): Promise<GeneratedTest> {
  const res = await request(`${BASE_URL}/patches/${patchId}/generate-tests`, { method: 'POST' });
  return res.json();
}

export async function verifyPatch(patchId: string): Promise<VerificationRun> {
  const res = await request(`${BASE_URL}/patches/${patchId}/verify`, { method: 'POST' });
  return res.json();
}

export async function runRepairLoop(patchId: string, maxAttempts = 3): Promise<any> {
  const res = await request(`${BASE_URL}/patches/${patchId}/repair-loop`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ max_attempts: maxAttempts }),
  });
  return res.json();
}

export async function fetchReport(projectId: string): Promise<EvidenceReport> {
  const res = await request(`${BASE_URL}/projects/${projectId}/report`);
  return res.json();
}

export async function fetchTimeline(projectId: string): Promise<AuditEvent[]> {
  const res = await request(`${BASE_URL}/projects/${projectId}/timeline`);
  return res.json();
}
