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
  EvaluationResults,
} from '../types';

// Browser requests stay same-origin by default: Vite proxies in development and Vercel
// rewrites /api/* to the Render service in production. Optionally supports VITE_API_BASE_URL.
const BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/+$/, '');

export class ApiError extends Error {
  constructor(message: string, public readonly errorCode?: string, public readonly status?: number, public readonly requestId?: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request(input: RequestInfo | URL, init?: RequestInit, timeoutMs = 60_000): Promise<Response> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  let response: Response;
  try {
    response = await fetch(input, { ...init, signal: init?.signal ?? controller.signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError('The PatchPilot request timed out. The backend may be waking up; try again.', 'REQUEST_TIMEOUT');
    }
    if (error instanceof TypeError) {
      throw new ApiError('Could not reach the PatchPilot backend. Check the connection and try again.', 'NETWORK_ERROR');
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
  if (!response.ok) {
    let payload: any = {};
    try { payload = await response.clone().json(); } catch { /* response had no JSON body */ }
    const detail = payload.message || payload.detail || `Request failed (HTTP ${response.status})`;
    const requestId = response.headers.get('X-Request-ID') ?? undefined;
    const message = requestId ? `${detail} (Request ID: ${requestId})` : detail;
    throw new ApiError(message, payload.error_code, response.status, requestId);
  }
  return response;
}

export async function fetchHealth(): Promise<any> {
  const res = await request(`${BASE_URL}/health`, undefined, 90_000);
  return res.json();
}

export async function fetchPublicConfig(): Promise<any> {
  const res = await request(`${BASE_URL}/public/config`, undefined, 90_000);
  return res.json();
}

export async function fetchProviderStatus(): Promise<any> {
  const res = await request(`${BASE_URL}/providers/status`);
  return res.json();
}

export async function testActiveProvider(): Promise<any> {
  const res = await request(`${BASE_URL}/providers/test`, { method: 'POST' }, 90_000);
  return res.json();
}

export async function fetchPublicStats(): Promise<{ projects: number; runs: number; verified_runs: number }> {
  const res = await request(`${BASE_URL}/public/stats`, undefined, 90_000);
  return res.json();
}

export async function fetchEvaluationResults(): Promise<EvaluationResults> {
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
  }, 150_000);
  return res.json();
}

export async function generatePatch(projectId: string, planId?: string, targetFile?: string): Promise<Patch> {
  const res = await request(`${BASE_URL}/projects/${projectId}/patches/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ plan_id: planId, target_file: targetFile }),
  }, 150_000);
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
  }, 150_000);
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
