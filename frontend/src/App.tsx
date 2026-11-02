import React, { useState, useEffect } from 'react';
import {
  Shield,
  Cpu,
  FolderTree,
  FileCode,
  Bug,
  Wrench,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Play,
  RotateCcw,
  Download,
  Terminal,
  Activity,
  Layers,
  Sparkles,
  RefreshCw,
  UploadCloud,
  FileCheck,
  Check,
  X,
  Clock,
  BarChart3,
} from 'lucide-react';

import * as api from './services/api';
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
} from './types';

export default function App() {
  const [theme, setTheme] = useState(() => {
    const saved = localStorage.getItem('patchpilot-theme');
    return saved === 'aurora' || saved === 'meta-blue' || saved === 'daylight' ? saved : (window.matchMedia('(prefers-color-scheme: light)').matches ? 'daylight' : 'aurora');
  });
  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem('patchpilot-theme', theme); }, [theme]);
  const [activeTab, setActiveTab] = useState<'intake' | 'explorer' | 'findings' | 'repair' | 'verification' | 'report' | 'eval'>('intake');
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [health, setHealth] = useState<any>(null);
  const [serverReady, setServerReady] = useState(false);
  const [serverWaking, setServerWaking] = useState(true);
  const [evaluationResults, setEvaluationResults] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' | 'info' } | null>(null);

  // Intake State
  const [newProjectName, setNewProjectName] = useState('');
  const [newBugDesc, setNewBugDesc] = useState('');
  const [newStackTrace, setNewStackTrace] = useState('');
  const [uploadFile, setUploadFile] = useState<File | null>(null);

  // Explorer State
  const [files, setFiles] = useState<FileItem[]>([]);
  const [selectedFilePath, setSelectedFilePath] = useState<string>('');
  const [fileContent, setFileContent] = useState<string>('');

  // Findings State
  const [findings, setFindings] = useState<Finding[]>([]);
  const [selectedFinding, setSelectedFinding] = useState<Finding | null>(null);

  // Repair & Patch State
  const [activePlan, setActivePlan] = useState<RepairPlan | null>(null);
  const [patches, setPatches] = useState<Patch[]>([]);
  const [activePatch, setActivePatch] = useState<Patch | null>(null);
  const [generatedTests, setGeneratedTests] = useState<GeneratedTest[]>([]);

  // Verification & Loop State
  const [verificationRuns, setVerificationRuns] = useState<VerificationRun[]>([]);
  const [activeRun, setActiveRun] = useState<VerificationRun | null>(null);
  const [loopResult, setLoopResult] = useState<any>(null);
  const [repairLoopRunning, setRepairLoopRunning] = useState(false);

  // Report & Timeline State
  const [report, setReport] = useState<EvidenceReport | null>(null);
  const [timeline, setTimeline] = useState<AuditEvent[]>([]);

  useEffect(() => {
    let cancelled = false;
    const wakeBackend = async () => {
      const delays = [0, 1000, 2000, 4000, 8000, 15000, 30000];
      for (const delay of delays) {
        if (delay) await new Promise((resolve) => setTimeout(resolve, delay));
        if (cancelled) return;
        try {
          const data = await api.fetchHealth();
          if (cancelled) return;
          setHealth(data);
          setServerReady(true);
          setServerWaking(false);
          await loadProjects();
          return;
        } catch {
          setServerWaking(true);
        }
      }
    };
    void wakeBackend();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (selectedProject) {
      loadProjectData(selectedProject.id);
    }
  }, [selectedProject?.id]);

  useEffect(() => {
    if (activeTab === 'eval') {
      api.fetchEvaluationResults().then(setEvaluationResults).catch((err) => showToast(err.message, 'error'));
    }
  }, [activeTab]);

  const showToast = (text: string, type: 'success' | 'error' | 'info' = 'info') => {
    setMessage({ text, type });
    setTimeout(() => setMessage(null), 5000);
  };

  const loadProjects = async () => {
    try {
      const data = await api.listProjects();
      setProjects(data);
      if (data.length > 0 && !selectedProject) {
        setSelectedProject(data[0]);
      }
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  const loadProjectData = async (projectId: string) => {
    setLoading(true);
    try {
      const [filesData, findingsData, patchesData, timelineData] = await Promise.all([
        api.fetchProjectFiles(projectId),
        api.fetchFindings(projectId),
        api.listPatches(projectId),
        api.fetchTimeline(projectId),
      ]);
      setFiles(filesData);
      setFindings(findingsData);
      setPatches(patchesData);
      setTimeline(timelineData);

      if (filesData.length > 0) {
        handleSelectFile(filesData[0].path);
      }
      if (patchesData.length > 0) {
        setActivePatch(patchesData[0]);
        loadPatchVerifications(patchesData[0].id);
      }
    } catch (err: any) {
      showToast(err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleSelectFile = async (path: string) => {
    if (!selectedProject) return;
    setSelectedFilePath(path);
    try {
      const data = await api.fetchFileContent(selectedProject.id, path);
      setFileContent(data.content);
    } catch (err: any) {
      setFileContent(`[Failed to load file content: ${err.message}]`);
    }
  };

  const loadPatchVerifications = async (patchId: string) => {
    try {
      const res = await fetch(`/api/patches/${patchId}/verification-history`);
      if (res.ok) {
        const history = await res.json();
        setVerificationRuns(history);
        if (history.length > 0) {
          setActiveRun(history[0]);
        }
      }
    } catch {
      // ignore
    }
  };

  const handleLoadSample = async () => {
    setLoading(true);
    try {
      const p = await api.loadSampleProject();
      setProjects((prev) => [p, ...prev]);
      setSelectedProject(p);
      showToast('Sample Demo Project loaded successfully! (Calculator Accumulator Bug)', 'success');
      setActiveTab('intake');
    } catch (err: any) {
      showToast(err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjectName) return;
    setLoading(true);
    try {
      const p = await api.createProject({
        name: newProjectName,
        bug_description: newBugDesc,
        stack_trace: newStackTrace,
      });

      if (uploadFile) {
        await api.uploadZip(p.id, uploadFile);
      }

      setProjects((prev) => [p, ...prev]);
      setSelectedProject(p);
      setNewProjectName('');
      setNewBugDesc('');
      setNewStackTrace('');
      setUploadFile(null);
      showToast(`Project '${p.name}' created!`, 'success');
    } catch (err: any) {
      showToast(err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleRunAnalysis = async () => {
    if (!selectedProject) return;
    setLoading(true);
    try {
      const res = await api.runStaticAnalysis(selectedProject.id);
      setFindings(res.findings);
      showToast(`Static inspection complete: ${res.findings_count} findings identified`, 'success');
      setActiveTab('findings');
      loadProjectData(selectedProject.id);
    } catch (err: any) {
      showToast(err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleGeneratePlan = async (findingId?: string) => {
    if (!selectedProject) return;
    setLoading(true);
    try {
      const plan = await api.generateRepairPlan(selectedProject.id, findingId);
      setActivePlan(plan);
      showToast('AI Repair Plan generated by Meta AI!', 'success');
      setActiveTab('repair');
    } catch (err: any) {
      showToast(err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleGeneratePatch = async () => {
    if (!selectedProject) return;
    setLoading(true);
    try {
      const patch = await api.generatePatch(selectedProject.id, activePlan?.id);
      setPatches((prev) => [patch, ...prev]);
      setActivePatch(patch);
      showToast(`Unified diff patch generated for ${patch.target_file}!`, 'success');
    } catch (err: any) {
      showToast(err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleApprovePatch = async (patchId: string) => {
    try {
      await api.approvePatch(patchId);
      showToast('Patch approved! Ready for isolated sandbox verification or application.', 'success');
      loadProjectData(selectedProject!.id);
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  const handleRejectPatch = async (patchId: string) => {
    try {
      await api.rejectPatch(patchId);
      showToast('Patch rejected.', 'info');
      loadProjectData(selectedProject!.id);
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  const handleApplyPatch = async (patchId: string) => {
    try {
      await api.applyPatch(patchId);
      showToast('Patch permanently applied to project workspace!', 'success');
      loadProjectData(selectedProject!.id);
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  const handleGenerateTests = async (patchId: string) => {
    setLoading(true);
    try {
      const test = await api.generateTests(patchId);
      setGeneratedTests((prev) => [test, ...prev]);
      showToast(`Pytest regression test suite generated (${health?.meta_provider?.status || 'provider status unknown'}).`, 'info');
    } catch (err: any) {
      showToast(err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyPatch = async (patchId: string) => {
    setLoading(true);
    try {
      const run = await api.verifyPatch(patchId);
      setActiveRun(run);
      setVerificationRuns((prev) => [run, ...prev]);
      showToast(`Verification run complete. Status: ${run.verification_status}`, run.verification_status === 'VERIFIED_AGAINST_DEFINED_TESTS' ? 'success' : 'info');
      setActiveTab('verification');
    } catch (err: any) {
      showToast(err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleRunRepairLoop = async (patchId: string) => {
    setRepairLoopRunning(true);
    try {
      const result = await api.runRepairLoop(patchId, 3);
      setLoopResult(result);
      showToast(`Repair loop finished in ${result.attempts_made} iterations. Status: ${result.final_status}`, result.final_status === 'VERIFIED_AGAINST_DEFINED_TESTS' ? 'success' : 'info');
      setActiveTab('verification');
      loadProjectData(selectedProject!.id);
    } catch (err: any) {
      showToast(err.message, 'error');
    } finally {
      setRepairLoopRunning(false);
    }
  };

  const handleLoadReport = async () => {
    if (!selectedProject) return;
    setLoading(true);
    try {
      const rep = await api.fetchReport(selectedProject.id);
      setReport(rep);
      setActiveTab('report');
    } catch (err: any) {
      showToast(err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col min-h-screen bg-slate-950 text-slate-100">
      {/* Toast Notification */}
      {message && (
        <div
          className={`fixed bottom-6 right-6 z-50 px-5 py-3 rounded-lg shadow-2xl flex items-center gap-3 border text-sm font-medium transition-all transform animate-bounce ${
            message.type === 'success'
              ? 'bg-emerald-950/90 border-emerald-500/50 text-emerald-200'
              : message.type === 'error'
              ? 'bg-rose-950/90 border-rose-500/50 text-rose-200'
              : 'bg-sky-950/90 border-sky-500/50 text-sky-200'
          }`}
        >
          {message.type === 'success' ? (
            <CheckCircle2 className="w-5 h-5 text-emerald-400" />
          ) : message.type === 'error' ? (
            <XCircle className="w-5 h-5 text-rose-400" />
          ) : (
            <AlertTriangle className="w-5 h-5 text-sky-400" />
          )}
          <span>{message.text}</span>
        </div>
      )}

      {serverWaking && (
        <div className="bg-amber-950/60 border-b border-amber-800 px-6 py-2 text-xs text-amber-200">
          Waking the server (free hosting can take up to a minute). Start actions unlock when the API is ready.
        </div>
      )}

      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur-md sticky top-0 z-40 px-6 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-teal-500 to-indigo-500 p-0.5 flex items-center justify-center shadow-lg shadow-teal-500/20">
              <div className="w-full h-full bg-slate-950 rounded-[10px] flex items-center justify-center">
                <Shield className="w-5 h-5 text-teal-400" />
              </div>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-lg tracking-tight bg-gradient-to-r from-teal-300 via-sky-300 to-indigo-300 bg-clip-text text-transparent">
                  PatchPilot
                </span>
                <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-teal-500/10 text-teal-400 border border-teal-500/20">
                  Self-Verifying AI Agent
                </span>
              </div>
              <p className="text-xs text-slate-400">Autonomous Software Repair Grounded in Test Verification</p>
            </div>
          </div>
        </div>

        {/* Project Selector & Actions */}
        <div className="flex items-center gap-3">
          <label className="sr-only" htmlFor="workspace-theme">Color theme</label>
          <select id="workspace-theme" value={theme} onChange={(event) => setTheme(event.target.value)} className="border border-slate-700 rounded-lg px-2 py-1.5 text-xs" aria-label="Color theme">
            <option value="aurora">Aurora</option><option value="meta-blue">Meta Blue</option><option value="daylight">Daylight</option>
          </select>
          <div className="flex items-center gap-2 bg-slate-800/80 px-3 py-1.5 rounded-lg border border-slate-700/60 text-xs">
            <Cpu className="w-3.5 h-3.5 text-indigo-400" />
            <span className="text-slate-400">Model:</span>
            <span className="font-mono text-indigo-300 font-medium">
              {health?.meta_provider?.model_id || 'Model unknown'}
            </span>
            <span
              className={`w-2 h-2 rounded-full ${
                health?.meta_provider?.status === 'LIVE_CONNECTED' ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'
              }`}
              title={health?.meta_provider?.message || health?.meta_provider?.status || 'Provider status unavailable'}
            />
            <span className="text-slate-400">{health?.meta_provider?.status || 'STATUS UNKNOWN'}</span>
          </div>

          <button
            onClick={handleLoadSample}
            disabled={loading || !serverReady}
            className="flex items-center gap-2 text-xs font-medium px-3.5 py-1.5 rounded-lg bg-gradient-to-r from-teal-500/20 to-sky-500/20 hover:from-teal-500/30 hover:to-sky-500/30 text-teal-300 border border-teal-500/30 transition shadow-sm"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>One-Click Demo Bug</span>
          </button>

          {projects.length > 0 && (
            <select
              value={selectedProject?.id || ''}
              onChange={(e) => {
                const found = projects.find((p) => p.id === e.target.value);
                if (found) setSelectedProject(found);
              }}
              className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-teal-500"
            >
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          )}
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-2 border-b border-slate-800 bg-slate-950 px-6 py-2 text-[11px]">
        <span className="rounded border border-slate-700 px-2 py-1 font-semibold">
          {health?.demo_mode ? 'DEMO MODE: SIMULATED AI OUTPUT' : health?.app_mode === 'public_demo'
            ? `PUBLIC DEMO · META ${health?.meta_provider?.status || 'STATUS UNKNOWN'}` : 'LOCAL MODE'}
        </span>
        <span className="rounded border border-rose-900 px-2 py-1 text-rose-300">
          {health?.sandbox?.execution_status || 'EXECUTION STATUS UNKNOWN'}
        </span>
        <span className="text-slate-500">SQLite data may reset on free-host restarts. Do not submit personal or confidential data.</span>
      </div>

      {/* Navigation Bar */}
      <nav className="border-b border-slate-800 bg-slate-900/30 px-6 flex items-center gap-1 overflow-x-auto text-xs font-medium">
        {[
          { id: 'intake', label: '1. Project Intake', icon: Layers },
          { id: 'explorer', label: '2. Repository Explorer', icon: FolderTree },
          { id: 'findings', label: '3. Static Inspection', icon: Bug, badge: findings.length },
          { id: 'repair', label: '4. AI Repair Workspace', icon: Wrench, badge: patches.length },
          { id: 'verification', label: '5. Verification Sandbox', icon: Terminal, badge: verificationRuns.length },
          { id: 'report', label: '6. Evidence Report', icon: FileCheck },
          { id: 'eval', label: '7. Benchmarks & Evaluation', icon: BarChart3 },
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => {
                setActiveTab(tab.id as any);
                if (tab.id === 'report') handleLoadReport();
              }}
              className={`flex items-center gap-2 px-4 py-3 border-b-2 transition whitespace-nowrap ${
                isActive
                  ? 'border-teal-400 text-teal-300 bg-teal-500/5 font-semibold'
                  : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700'
              }`}
            >
              <Icon className={`w-4 h-4 ${isActive ? 'text-teal-400' : 'text-slate-500'}`} />
              <span>{tab.label}</span>
              {typeof tab.badge === 'number' && tab.badge > 0 && (
                <span className="px-1.5 py-0.2 rounded-full text-[10px] font-bold bg-slate-800 text-slate-300">
                  {tab.badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Main Content Area */}
      <main className="flex-1 p-6 max-w-7xl mx-auto w-full">
        {/* TAB 1: Intake & Management */}
        {activeTab === 'intake' && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="md:col-span-2 space-y-6">
              <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800/80 shadow-xl">
                <h2 className="text-base font-semibold text-slate-200 mb-1 flex items-center gap-2">
                  <UploadCloud className="w-5 h-5 text-teal-400" />
                  <span>Create Project & Upload Repository</span>
                </h2>
                <p className="text-xs text-slate-400 mb-6">
                  Extracts safely into an isolated workspace with path traversal and zip bomb defenses.
                </p>

                {health?.app_mode === 'public_demo' ? (
                  <p className="rounded-lg border border-slate-700 bg-slate-950 p-4 text-xs text-slate-300">
                    Public demo accepts bundled sample projects only. Repository uploads and custom projects are disabled.
                  </p>
                ) : <form onSubmit={handleCreateProject} className="space-y-4">
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">Project Name *</label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. Payments Gateway Microservice"
                      value={newProjectName}
                      onChange={(e) => setNewProjectName(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3.5 py-2 text-sm text-slate-100 focus:outline-none focus:border-teal-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">Bug Description</label>
                    <textarea
                      rows={3}
                      placeholder="Describe the defect, incorrect behavior, or expected output..."
                      value={newBugDesc}
                      onChange={(e) => setNewBugDesc(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3.5 py-2 text-sm text-slate-100 focus:outline-none focus:border-teal-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">
                      Observed Stack Trace / Error Output
                    </label>
                    <textarea
                      rows={3}
                      placeholder="Paste runtime error stack trace, assertion failure, or traceback..."
                      value={newStackTrace}
                      onChange={(e) => setNewStackTrace(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3.5 py-2 font-mono text-xs text-slate-100 focus:outline-none focus:border-teal-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">Repository ZIP Archive</label>
                    <input
                      type="file"
                      accept=".zip"
                      onChange={(e) => setUploadFile(e.target.files ? e.target.files[0] : null)}
                      className="w-full text-xs text-slate-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-teal-500/10 file:text-teal-400 hover:file:bg-teal-500/20 cursor-pointer"
                    />
                  </div>

                  <div className="pt-2 flex items-center justify-between">
                    <button
                      type="submit"
                      disabled={loading || !serverReady || !newProjectName}
                      className="px-5 py-2.5 rounded-lg bg-teal-500 hover:bg-teal-400 text-slate-950 font-semibold text-xs transition shadow-lg shadow-teal-500/20 disabled:opacity-50"
                    >
                      {loading ? 'Processing...' : 'Create & Ingest Repository'}
                    </button>

                    <button
                      type="button"
                      onClick={handleLoadSample}
                      className="text-xs text-slate-400 hover:text-teal-400 transition underline underline-offset-4"
                    >
                      Or load demo project (Calculator Accumulator Bug)
                    </button>
                  </div>
                </form>}
              </div>
            </div>

            {/* Current Active Project Details */}
            <div className="space-y-6">
              <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800/80 shadow-xl">
                <h3 className="text-sm font-semibold text-slate-200 mb-3 flex items-center gap-2">
                  <Activity className="w-4 h-4 text-indigo-400" />
                  <span>Selected Project Overview</span>
                </h3>

                {selectedProject ? (
                  <div className="space-y-3 text-xs">
                    <div>
                      <span className="text-slate-500">Name:</span>
                      <p className="font-medium text-slate-200 text-sm mt-0.5">{selectedProject.name}</p>
                    </div>
                    <div>
                      <span className="text-slate-500">Project ID:</span>
                      <p className="font-mono text-slate-400 text-[11px] truncate">{selectedProject.id}</p>
                    </div>
                    <div className="grid grid-cols-2 gap-2 pt-2 border-t border-slate-800/80">
                      <div>
                        <span className="text-slate-500">Files:</span>
                        <p className="font-bold text-slate-200 text-sm">{selectedProject.file_count}</p>
                      </div>
                      <div>
                        <span className="text-slate-500">Size:</span>
                        <p className="font-bold text-slate-200 text-sm">
                          {(selectedProject.size_bytes / 1024).toFixed(1)} KB
                        </p>
                      </div>
                    </div>
                    <div className="pt-2 border-t border-slate-800/80">
                      <span className="text-slate-500">Defect Summary:</span>
                      <p className="text-slate-300 mt-1 leading-relaxed bg-slate-950 p-2.5 rounded-lg border border-slate-800/60 text-[11px]">
                        {selectedProject.bug_description || 'No defect description provided.'}
                      </p>
                    </div>
                    <div className="pt-3">
                      <button
                        onClick={handleRunAnalysis}
                        disabled={loading || !serverReady}
                        className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-indigo-500/20 hover:bg-indigo-500/30 text-indigo-300 border border-indigo-500/30 font-medium text-xs transition"
                      >
                        <Bug className="w-4 h-4" />
                        <span>Run Static Inspection & Localization</span>
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-8 text-xs text-slate-500">
                    No project selected. Create one or load the demo project above.
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: Repository Explorer */}
        {activeTab === 'explorer' && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* File Tree */}
            <div className="p-4 rounded-2xl bg-slate-900/60 border border-slate-800/80 shadow-xl overflow-hidden flex flex-col h-[650px]">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3 px-2 flex items-center justify-between">
                <span>Repository Files</span>
                <span className="text-[10px] font-mono text-slate-500">{files.length} items</span>
              </h3>
              <div className="flex-1 overflow-y-auto space-y-1 pr-1">
                {files.length === 0 ? (
                  <div className="text-center py-10 text-xs text-slate-500">No files found in workspace</div>
                ) : (
                  files.map((f) => (
                    <button
                      key={f.path}
                      onClick={() => handleSelectFile(f.path)}
                      className={`w-full text-left px-3 py-2 rounded-lg text-xs font-mono flex items-center justify-between transition ${
                        selectedFilePath === f.path
                          ? 'bg-teal-500/20 text-teal-200 border border-teal-500/40'
                          : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/40'
                      }`}
                    >
                      <div className="flex items-center gap-2 truncate">
                        <FileCode className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                        <span className="truncate">{f.path}</span>
                      </div>
                      <span className="text-[10px] text-slate-600 ml-2">{(f.size_bytes / 1024).toFixed(1)}k</span>
                    </button>
                  ))
                )}
              </div>
            </div>

            {/* File Content Preview */}
            <div className="md:col-span-2 p-4 rounded-2xl bg-slate-900/60 border border-slate-800/80 shadow-xl flex flex-col h-[650px]">
              <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-3 px-2">
                <span className="font-mono text-xs text-slate-300 font-medium truncate">{selectedFilePath || 'Select a file'}</span>
                <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded bg-slate-800 text-slate-400">
                  Read Only Preview
                </span>
              </div>
              <div className="flex-1 overflow-auto bg-slate-950 p-4 rounded-xl border border-slate-800/60 font-mono text-xs text-slate-300 whitespace-pre">
                {fileContent || '// Select a file from the repository tree to inspect'}
              </div>
            </div>
          </div>
        )}

        {/* TAB 3: Static Inspection & Localization */}
        {activeTab === 'findings' && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-base font-semibold text-slate-200">Static Inspection & Bug Localization</h2>
                <p className="text-xs text-slate-400">
                  Signals derived via AST analysis, traceback reference matching, and token overlap.
                </p>
              </div>
              <button
                onClick={handleRunAnalysis}
                disabled={loading || !serverReady}
                className="flex items-center gap-2 text-xs font-semibold px-4 py-2 rounded-lg bg-teal-500 hover:bg-teal-400 text-slate-950 transition"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                <span>Re-run Inspection</span>
              </button>
            </div>

            {findings.length === 0 ? (
              <div className="text-center py-16 bg-slate-900/40 rounded-2xl border border-slate-800/80">
                <Bug className="w-10 h-10 text-slate-600 mx-auto mb-3" />
                <p className="text-sm text-slate-400">No static inspection findings recorded yet.</p>
                <button
                  onClick={handleRunAnalysis}
                  className="mt-4 px-4 py-2 bg-indigo-500/20 border border-indigo-500/30 text-indigo-300 rounded-lg text-xs font-medium"
                >
                  Run Static Analysis & Localization Now
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {findings.map((f) => (
                  <div
                    key={f.id}
                    className="p-5 rounded-xl bg-slate-900/60 border border-slate-800/80 shadow-lg flex flex-col justify-between"
                  >
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <span
                          className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${
                            f.severity === 'critical'
                              ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                              : f.severity === 'high'
                              ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                              : 'bg-sky-500/20 text-sky-400 border border-sky-500/30'
                          }`}
                        >
                          {f.severity}
                        </span>
                        <span className="text-[11px] text-slate-500 font-mono">
                          Confidence: {(f.confidence * 100).toFixed(0)}%
                        </span>
                      </div>
                      <h4 className="text-sm font-semibold text-slate-100 mb-1">{f.title}</h4>
                      <p className="text-xs text-slate-400 mb-3">{f.description}</p>
                      <div className="font-mono text-[11px] text-slate-400 bg-slate-950 px-2.5 py-1.5 rounded border border-slate-800 mb-3 truncate">
                        {f.file_path} {f.line_number ? `(line ${f.line_number})` : ''}
                      </div>
                      {f.code_snippet && (
                        <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 font-mono text-xs text-slate-300 whitespace-pre overflow-x-auto mb-3">
                          {f.code_snippet}
                        </div>
                      )}
                    </div>
                    <div className="pt-3 border-t border-slate-800/80 flex items-center justify-between">
                      <span className="text-[11px] text-slate-500 italic truncate max-w-[220px]">
                        Rec: {f.recommended_action || 'Inspect candidate'}
                      </span>
                      <button
                        onClick={() => handleGeneratePlan(f.id)}
                        className="text-xs font-semibold px-3 py-1.5 rounded bg-teal-500/20 hover:bg-teal-500/30 text-teal-300 border border-teal-500/30 transition flex items-center gap-1.5"
                      >
                        <Wrench className="w-3.5 h-3.5" />
                        <span>Plan Repair</span>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* TAB 4: AI Repair Workspace */}
        {activeTab === 'repair' && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-base font-semibold text-slate-200">AI Repair Planning & Patch Studio</h2>
                <p className="text-xs text-slate-400">
                  Structured root-cause hypotheses, unified diffs, and human review before application.
                </p>
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => handleGeneratePlan()}
                  disabled={loading || !serverReady}
                  className="flex items-center gap-2 text-xs font-medium px-4 py-2 rounded-lg bg-indigo-500/20 hover:bg-indigo-500/30 text-indigo-300 border border-indigo-500/30 transition"
                >
                  <Cpu className="w-3.5 h-3.5" />
                  <span>Generate New Plan</span>
                </button>
                <button
                  onClick={handleGeneratePatch}
                  disabled={loading || !serverReady}
                  className="flex items-center gap-2 text-xs font-semibold px-4 py-2 rounded-lg bg-teal-500 hover:bg-teal-400 text-slate-950 transition shadow-lg shadow-teal-500/20"
                >
                  <Wrench className="w-3.5 h-3.5" />
                  <span>Generate Unified Diff</span>
                </button>
              </div>
            </div>

            {/* Repair Plan Card */}
            {activePlan && (
              <div className="p-6 rounded-2xl bg-gradient-to-br from-slate-900/80 to-slate-900/40 border border-slate-800 shadow-xl space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] uppercase font-bold tracking-wider px-2.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                    AI Hypothesis & Plan
                  </span>
                  <span className="text-xs text-slate-500 font-mono">Plan ID: {activePlan.id.slice(0, 8)}</span>
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-100">{activePlan.problem_summary}</h3>
                  <p className="text-xs text-slate-400 mt-1 leading-relaxed">{activePlan.root_cause}</p>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs pt-2">
                  <div className="bg-slate-950/60 p-3.5 rounded-xl border border-slate-800/80">
                    <span className="font-semibold text-slate-300 block mb-1.5">Proposed Steps:</span>
                    <ul className="list-disc list-inside space-y-1 text-slate-400">
                      {activePlan.proposed_changes.map((step, idx) => (
                        <li key={idx}>{step}</li>
                      ))}
                    </ul>
                  </div>
                  <div className="bg-slate-950/60 p-3.5 rounded-xl border border-slate-800/80">
                    <span className="font-semibold text-slate-300 block mb-1.5">Expected Behavior:</span>
                    <p className="text-slate-400 leading-relaxed">{activePlan.expected_behavior}</p>
                  </div>
                </div>
              </div>
            )}

            {/* Active Patch Unified Diff Viewer */}
            {activePatch ? (
              <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800 shadow-xl space-y-4">
                <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                  <div>
                    <span className="font-mono text-sm font-semibold text-slate-200">
                      Target: {activePatch.target_file}
                    </span>
                    <div className="flex items-center gap-2 mt-1">
                      <span
                        className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${
                          activePatch.validation_status === 'valid'
                            ? 'bg-emerald-500/20 text-emerald-400'
                            : 'bg-rose-500/20 text-rose-400'
                        }`}
                      >
                        Status: {activePatch.validation_status}
                      </span>
                      {activePatch.is_approved && (
                        <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-teal-500/20 text-teal-300 border border-teal-500/30">
                          Human Approved
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {!activePatch.is_approved ? (
                      <button
                        onClick={() => handleApprovePatch(activePatch.id)}
                        className="px-3.5 py-1.5 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/30 text-xs font-semibold flex items-center gap-1.5 transition"
                      >
                        <Check className="w-3.5 h-3.5" />
                        <span>Approve Patch</span>
                      </button>
                    ) : (
                      <button
                        onClick={() => handleApplyPatch(activePatch.id)}
                        className="px-3.5 py-1.5 rounded-lg bg-teal-500 hover:bg-teal-400 text-slate-950 text-xs font-semibold flex items-center gap-1.5 transition"
                      >
                        <Check className="w-3.5 h-3.5" />
                        <span>Apply to Workspace</span>
                      </button>
                    )}

                    <button
                      onClick={() => handleRejectPatch(activePatch.id)}
                      className="px-3 py-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/20 text-xs font-medium flex items-center gap-1.5 transition"
                    >
                      <X className="w-3.5 h-3.5" />
                      <span>Reject</span>
                    </button>

                    <button
                      onClick={() => handleGenerateTests(activePatch.id)}
                      className="px-3.5 py-1.5 rounded-lg bg-indigo-500/20 hover:bg-indigo-500/30 text-indigo-300 border border-indigo-500/30 text-xs font-medium flex items-center gap-1.5 transition"
                    >
                      <FileCheck className="w-3.5 h-3.5" />
                      <span>Generate Tests</span>
                    </button>

                    <button
                      onClick={() => handleVerifyPatch(activePatch.id)}
                      className="px-4 py-1.5 rounded-lg bg-teal-500 hover:bg-teal-400 text-slate-950 text-xs font-bold flex items-center gap-1.5 transition shadow-lg shadow-teal-500/20"
                    >
                      <Play className="w-3.5 h-3.5" />
                      <span>Verify in Sandbox</span>
                    </button>
                  </div>
                </div>

                {/* Diff Lines View */}
                <div className="bg-slate-950 p-4 rounded-xl border border-slate-800/80 font-mono text-xs overflow-x-auto leading-relaxed">
                  {activePatch.diff_content.split('\n').map((line, idx) => {
                    const isAdd = line.startsWith('+') && !line.startsWith('+++');
                    const isDel = line.startsWith('-') && !line.startsWith('---');
                    const isHeader = line.startsWith('@@') || line.startsWith('---') || line.startsWith('+++');
                    return (
                      <div
                        key={idx}
                        className={`px-2 py-0.5 rounded ${
                          isAdd
                            ? 'bg-emerald-950/40 text-emerald-300'
                            : isDel
                            ? 'bg-rose-950/40 text-rose-300'
                            : isHeader
                            ? 'text-sky-400 font-bold'
                            : 'text-slate-400'
                        }`}
                      >
                        {line || ' '}
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              <div className="text-center py-16 bg-slate-900/40 rounded-2xl border border-slate-800">
                <Wrench className="w-10 h-10 text-slate-600 mx-auto mb-3" />
                <p className="text-sm text-slate-400">No patches generated yet.</p>
                <button
                  onClick={handleGeneratePatch}
                  className="mt-4 px-4 py-2 bg-teal-500 hover:bg-teal-400 text-slate-950 rounded-lg text-xs font-semibold"
                >
                  Generate Patch for Active Finding
                </button>
              </div>
            )}
          </div>
        )}

        {/* TAB 5: Verification Sandbox & Bounded Repair Loop */}
        {activeTab === 'verification' && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-base font-semibold text-slate-200">Execution Sandbox & Self-Repair Loop</h2>
                <p className="text-xs text-slate-400">
                  Container isolation is unavailable; repository execution is disabled. Disposable snapshots alone are not process isolation.
                </p>
              </div>

              {activePatch && (
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => handleVerifyPatch(activePatch.id)}
                    disabled={loading || !serverReady || repairLoopRunning}
                    className="flex items-center gap-2 text-xs font-semibold px-4 py-2 rounded-lg bg-sky-500/20 hover:bg-sky-500/30 text-sky-300 border border-sky-500/30 transition"
                  >
                    <Play className="w-3.5 h-3.5" />
                    <span>Run Single Verification</span>
                  </button>

                  <button
                    onClick={() => handleRunRepairLoop(activePatch.id)}
                    disabled={loading || !serverReady || repairLoopRunning}
                    className="flex items-center gap-2 text-xs font-bold px-4 py-2 rounded-lg bg-gradient-to-r from-teal-500 to-emerald-500 hover:from-teal-400 hover:to-emerald-400 text-slate-950 transition shadow-lg shadow-teal-500/20"
                  >
                    <RotateCcw className={`w-3.5 h-3.5 ${repairLoopRunning ? 'animate-spin' : ''}`} />
                    <span>{repairLoopRunning ? 'Executing Repair Loop...' : 'Run Closed-Loop Self-Repair (3x)'}</span>
                  </button>
                </div>
              )}
            </div>

            {/* Differential Results Card */}
            {activeRun ? (
              <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800 shadow-xl space-y-6">
                <div className="flex items-center justify-between pb-4 border-b border-slate-800">
                  <div className="flex items-center gap-3">
                    <span
                      className={`text-xs font-bold px-3 py-1 rounded-full uppercase tracking-wider ${
                        activeRun.verification_status === 'VERIFIED_AGAINST_DEFINED_TESTS'
                          ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                          : activeRun.verification_status === 'TESTS_FAILED'
                          ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                          : 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                      }`}
                    >
                      {activeRun.verification_status.replace(/_/g, ' ')}
                    </span>
                    <span className="text-xs text-slate-400 font-mono">Run ID: {activeRun.id.slice(0, 8)}</span>
                  </div>

                  <span className="text-xs text-slate-500 flex items-center gap-1.5 font-mono">
                    <Clock className="w-3.5 h-3.5" />
                    <span>Duration: {activeRun.duration_seconds}s</span>
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* Baseline Sandbox Run */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-slate-300">Baseline Sandbox Execution (Unmodified)</span>
                      <span
                        className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                        activeRun.baseline_passed == null ? 'bg-slate-800 text-slate-400' : activeRun.baseline_passed ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'
                        }`}
                      >
                        {activeRun.baseline_passed == null ? 'NOT RUN' : activeRun.baseline_passed ? 'PASSED' : 'FAILED'} (Exit {activeRun.baseline_exit_code ?? '—'})
                      </span>
                    </div>
                    <div className="bg-slate-950 p-4 rounded-xl border border-slate-800/80 font-mono text-xs text-slate-300 h-64 overflow-y-auto whitespace-pre leading-relaxed">
                      {activeRun.baseline_stdout || '// No baseline output recorded'}
                    </div>
                  </div>

                  {/* Patched Sandbox Run */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-slate-300">Patched Sandbox Execution (Candidate)</span>
                      <span
                        className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                        activeRun.patched_passed == null ? 'bg-slate-800 text-slate-400' : activeRun.patched_passed ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'
                        }`}
                      >
                        {activeRun.patched_passed == null ? 'NOT RUN' : activeRun.patched_passed ? 'PASSED' : 'FAILED'} (Exit {activeRun.patched_exit_code ?? '—'})
                      </span>
                    </div>
                    <div className="bg-slate-950 p-4 rounded-xl border border-slate-800/80 font-mono text-xs text-slate-300 h-64 overflow-y-auto whitespace-pre leading-relaxed">
                      {activeRun.patched_stdout || activeRun.patched_stderr || '// No patched output recorded'}
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center py-16 bg-slate-900/40 rounded-2xl border border-slate-800">
                <Terminal className="w-10 h-10 text-slate-600 mx-auto mb-3" />
                <p className="text-sm text-slate-400">No test executions recorded yet.</p>
                {activePatch && (
                  <button
                    onClick={() => handleVerifyPatch(activePatch.id)}
                    className="mt-4 px-4 py-2 bg-teal-500 hover:bg-teal-400 text-slate-950 rounded-lg text-xs font-semibold"
                  >
                    Run Differential Sandbox Verification
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        {/* TAB 6: Auditable Evidence Report */}
        {activeTab === 'report' && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-base font-semibold text-slate-200">Evidence Report & Audit Trail</h2>
                <p className="text-xs text-slate-400">
                  Physical execution evidence separating model hypotheses from actual pass/fail logs.
                </p>
              </div>

              {selectedProject && (
                <div className="flex items-center gap-3">
                  <a
                    href={`/api/projects/${selectedProject.id}/report?format=markdown`}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center gap-1.5 text-xs font-medium px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 transition"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>Download Markdown</span>
                  </a>
                  <a
                    href={`/api/projects/${selectedProject.id}/report`}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center gap-1.5 text-xs font-medium px-3.5 py-2 rounded-lg bg-teal-500/20 hover:bg-teal-500/30 text-teal-300 border border-teal-500/30 transition"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>Download JSON</span>
                  </a>
                </div>
              )}
            </div>

            {report && (
              <div className="p-8 rounded-2xl bg-slate-900/60 border border-slate-800 shadow-2xl space-y-6">
                <div className="flex items-center justify-between pb-4 border-b border-slate-800">
                  <div>
                    <h3 className="text-lg font-bold text-slate-100">{report.project.name}</h3>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Report ID: {report.meta.report_id} | Provider: {report.meta.ai_provider}
                    </p>
                  </div>
                  <span className="text-xs font-bold uppercase tracking-wider px-3 py-1 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                    {report.verification_evidence.verification_status}
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <div className="md:col-span-2 space-y-4">
                    <div>
                      <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-1">
                        Reported Defect
                      </h4>
                      <p className="text-xs text-slate-300 bg-slate-950 p-3 rounded-lg border border-slate-800/80">
                        {report.project.bug_description || 'N/A'}
                      </p>
                    </div>

                    <div>
                      <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-1">
                        AI Hypothesis & Root Cause
                      </h4>
                      <div className="text-xs text-slate-300 bg-slate-950 p-3.5 rounded-lg border border-slate-800/80 space-y-2">
                        <p className="font-semibold text-slate-200">{report.ai_hypothesis.problem_summary}</p>
                        <p className="text-slate-400">{report.ai_hypothesis.root_cause}</p>
                      </div>
                    </div>

                    {report.patch_details.diff_content && (
                      <div>
                        <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-1">
                          Candidate Patch Diff
                        </h4>
                        <pre className="bg-slate-950 p-4 rounded-lg border border-slate-800/80 font-mono text-xs text-emerald-300 overflow-x-auto whitespace-pre">
                          {report.patch_details.diff_content}
                        </pre>
                      </div>
                    )}
                  </div>

                  {/* Audit Timeline */}
                  <div>
                    <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-1.5">
                      <Clock className="w-3.5 h-3.5 text-slate-400" />
                      <span>Audit Trail</span>
                    </h4>
                    <div className="space-y-3 bg-slate-950 p-4 rounded-xl border border-slate-800/80 max-h-[500px] overflow-y-auto">
                      {report.timeline.map((event, idx) => (
                        <div key={idx} className="border-l-2 border-teal-500/40 pl-3 py-1 space-y-0.5">
                          <p className="text-xs font-semibold text-slate-200">{event.title}</p>
                          <span className="text-[10px] text-slate-500 font-mono">
                            {new Date(event.timestamp).toLocaleTimeString()}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB 7: Benchmarks & Evaluation */}
        {activeTab === 'eval' && (
          <div className="space-y-6">
            <div>
              <h2 className="text-base font-semibold text-slate-200">Overall Performance</h2>
              <p className="text-xs text-slate-400">
                Observed project run status and the available benchmark record. Unmeasured results are shown as unavailable.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <section className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800/80 shadow-xl space-y-4">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-base font-bold text-slate-100">Synthetic benchmark</h3>
                  <span className="text-[10px] uppercase font-bold px-2 py-1 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
                    {evaluationResults?.evaluation_status || 'Loading'}
                  </span>
                </div>
                <p className="text-sm text-slate-600">
                  {evaluationResults?.reason || 'Loading the evaluation record…'}
                </p>
                <dl className="grid grid-cols-2 gap-3 pt-3 border-t border-slate-800 text-xs">
                  <div><dt className="text-slate-500">Dataset</dt><dd className="font-mono text-slate-200">{evaluationResults?.dataset || '—'}</dd></div>
                  <div><dt className="text-slate-500">Cases</dt><dd className="font-mono text-slate-200">{evaluationResults?.case_count ?? '—'}</dd></div>
                  <div><dt className="text-slate-500">Measured metrics</dt><dd className="font-mono text-slate-200">{evaluationResults?.metrics ? 'Available' : 'Not measured'}</dd></div>
                  <div><dt className="text-slate-500">Skipped</dt><dd className="font-mono text-slate-200">{evaluationResults?.skipped_cases ?? '—'}</dd></div>
                </dl>
              </section>

              <section className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800/80 shadow-xl space-y-4">
                <h3 className="text-base font-bold text-slate-100">Selected project verification</h3>
                <p className="text-sm text-slate-600">Observed run records only; no estimate is counted as a passing test.</p>
                <dl className="grid grid-cols-2 gap-3 pt-3 border-t border-slate-800 text-xs">
                  <div><dt className="text-slate-500">Recorded runs</dt><dd className="font-mono text-slate-200">{verificationRuns.length}</dd></div>
                  <div><dt className="text-slate-500">Verified runs</dt><dd className="font-mono text-slate-200">{verificationRuns.filter((run) => run.verification_status === 'VERIFIED_AGAINST_DEFINED_TESTS').length}</dd></div>
                  <div><dt className="text-slate-500">Execution unavailable</dt><dd className="font-mono text-slate-200">{verificationRuns.filter((run) => run.verification_status === 'EXECUTION_UNAVAILABLE').length}</dd></div>
                  <div><dt className="text-slate-500">Provider mode</dt><dd className="font-mono text-slate-200">{health?.meta_provider?.status || 'Unknown'}</dd></div>
                </dl>
              </section>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
