import { useEffect, useState } from 'react';
import { Activity, ArrowDownRight, ArrowRight, CircleHelp, Code2, ShieldCheck, Sun, Terminal, Zap } from 'lucide-react';
import { fetchPublicConfig, fetchPublicStats } from './services/api';

type Theme = 'aurora' | 'meta-blue' | 'daylight';
type Stats = { projects: number; runs: number; verified_runs: number };
type PublicConfig = { mode: string; provider_status: string; execution_backend: string; demo_enabled: boolean; public_ai_enabled: boolean };
type BuildInfo = { commit: string; build_date: string };
const APP_MODE = import.meta.env.VITE_APP_MODE || 'local';

function initialTheme(): Theme {
  const saved = localStorage.getItem('patchpilot-theme');
  if (saved === 'aurora' || saved === 'meta-blue' || saved === 'daylight') return saved;
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'daylight' : 'aurora';
}

export default function Landing() {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [stats, setStats] = useState<Stats | null>(null);
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [buildInfo, setBuildInfo] = useState<BuildInfo | null>(null);
  const [statsUnavailable, setStatsUnavailable] = useState(false);
  const path = window.location.pathname;
  const page = path === '/privacy' ? 'privacy' : path === '/terms' ? 'terms' : path === '/gallery' ? 'gallery' : 'home';

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('patchpilot-theme', theme);
  }, [theme]);
  useEffect(() => {
    let active = true;
    fetchPublicStats()
      .then((value) => { if (active) setStats(value); })
      .catch(() => { if (active) setStatsUnavailable(true); });
    fetchPublicConfig()
      .then((publicConfig) => { if (active) setConfig(publicConfig); })
      .catch(() => { if (active) setConfig(null); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    let active = true;
    fetch('/version.json', { cache: 'no-store' })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error('build info unavailable')))
      .then((value: BuildInfo) => { if (active) setBuildInfo(value); })
      .catch(() => undefined);
    return () => { active = false; };
  }, []);

  const cycleTheme = () => setTheme((current) => current === 'aurora' ? 'meta-blue' : current === 'meta-blue' ? 'daylight' : 'aurora');
  const themeLabel = theme === 'daylight' ? 'Daylight' : theme === 'meta-blue' ? 'Meta Blue' : 'Aurora';

  return <div className="launch-shell">
    <header className="launch-header">
      <a className="launch-brand" href="/" aria-label="PatchPilot home"><span className="launch-mark"><ShieldCheck size={19}/></span><span>patchpilot<span className="brand-dot">.</span></span></a>
      <nav aria-label="Main navigation" className="launch-nav"><a href="/gallery">Gallery</a><a href="/work">Workspace</a><a href="/privacy">Privacy</a></nav>
      <div className="launch-actions"><button className="theme-button" onClick={cycleTheme} aria-label={`Current theme ${themeLabel}. Change theme`}><Sun size={15}/><span>{themeLabel}</span></button><a className="button button-small" href="/work">Open workspace <ArrowRight size={15}/></a></div>
    </header>

    {page === 'home' && <main>
      <section className="hero">
        <div className="hero-copy"><div className="eyebrow"><span className="pulse-dot"/> REPAIR WORKFLOW · EVIDENCE FIRST</div>
          <h1>AI that proves<br/><span>its fixes.</span></h1>
          <p className="hero-lede">Patches that carry their own proof. Trace a bug from first clue to candidate patch, with every model action and verification result kept in view.</p>
          <div className="hero-ctas"><a className="button" href="/work">Explore the workspace <ArrowRight size={17}/></a><a className="text-link" href="/gallery">Browse recorded examples <ArrowDownRight size={16}/></a></div>
          <p className="honesty-note"><CircleHelp size={15}/> Execution is currently unavailable. Generated patches are proposals; this build does not prove they pass tests.</p>
        </div>
        <div className="hero-art" aria-label="Illustration of a repair workflow trace">
          <div className="orbit orbit-one"/><div className="orbit orbit-two"/><div className="trace-card">
            <div className="trace-top"><span><span className="pulse-dot"/> REPAIR TRACE</span><span className="trace-tag">{APP_MODE === 'production' ? 'PUBLIC PROTOTYPE' : 'LOCAL PROTOTYPE'}</span></div>
            <div className="trace-step"><span className="trace-icon"><Activity size={16}/></span><span><b>Investigate</b><small>Static findings · model hypothesis</small></span><span className="step-state">READY</span></div>
            <div className="trace-connector"/><div className="trace-step"><span className="trace-icon accent"><Code2 size={16}/></span><span><b>Propose patch</b><small>Validated edit blocks</small></span><span className="step-state">READY</span></div>
            <div className="trace-connector"/><div className="trace-step unavailable"><span className="trace-icon muted-icon"><Terminal size={16}/></span><span><b>Verify tests</b><small>Execution backend not available</small></span><span className="step-state">NOT RUN</span></div>
            <div className="trace-foot"><span><span className="mini-dot amber"/> META STATUS UNVERIFIED</span><span>NO TEST CLAIMS</span></div>
          </div><div className="hero-orb"><Zap size={20}/></div>
        </div>
      </section>
      {config?.mode === 'public_demo' && !config.public_ai_enabled && <aside className="launch-status" role="status">Live AI is off while launch gates are incomplete. No live model calls are made from this workspace. Do not submit private or proprietary code.</aside>}
      {stats && stats.runs > 0 && <section className="stats-strip" aria-label="Recorded project statistics"><div><b>{stats.projects}</b><span>recorded projects</span></div><div><b>{stats.runs}</b><span>verification records</span></div><div><b>{stats.verified_runs}</b><span>marked verified by recorded tests</span></div><small>Counts from the connected database</small></section>}
      <section className="pipeline-section"><div className="section-heading"><div><div className="eyebrow">A CLEAR PATH THROUGH THE WORK</div><h2>Every step leaves a trace.</h2></div><span>01 — 03</span></div>
        <div className="pipeline-grid"><article><div className="pipeline-number">01 <Activity size={18}/></div><h3>Investigate</h3><p>Bring a bug report or inspect the included sample project. Separate observed code facts from model suggestions.</p><span className="capability">STATIC ANALYSIS + OPTIONAL MODEL</span></article><article><div className="pipeline-number">02 <Code2 size={18}/></div><h3>Patch</h3><p>Review candidate edit blocks and their validation status before choosing what to apply.</p><span className="capability">HUMAN REVIEW</span></article><article><div className="pipeline-number">03 <Terminal size={18}/></div><h3>Verify</h3><p>Test execution is disabled in this build. No passing result is claimed until a safe runner exists.</p><span className="capability unavailable-label">EXECUTION UNAVAILABLE</span></article></div>
      </section>
      <section className="trust-band"><div><div className="eyebrow">CURRENT CAPABILITIES</div><h2>Clear about what ran.</h2><p>PatchPilot keeps proposed repairs separate from execution evidence. Provider state and test results are reported by the backend when available.</p></div><div className="trust-badges"><span><i className="status-icon neutral"><CircleHelp size={16}/></i><b>Provider</b><small>{config?.provider_status || 'STATUS UNKNOWN'}</small></span><span><i className="status-icon amber-icon"><Terminal size={16}/></i><b>Execution</b><small>{config?.execution_backend === 'none' ? 'UNAVAILABLE' : (config?.execution_backend || 'STATUS UNKNOWN').toUpperCase()}</small></span><span><i className="status-icon green-icon"><ShieldCheck size={16}/></i><b>Safety</b><small>FAIL CLOSED</small></span></div></section>
      <section className="cta-band"><div><h2>See the evidence boundary for yourself.</h2><p>Open the existing workspace and inspect the prototype’s current capabilities.</p></div><a className="button" href="/work">Open workspace <ArrowRight size={17}/></a></section>
      {statsUnavailable && <p className="stats-note">Live database counts are unavailable right now.</p>}
    </main>}

    {page === 'gallery' && <main className="document-page"><div className="eyebrow">RECORDED EXAMPLES</div><h1>Verified fix gallery</h1><p className="doc-lede">Only owner-approved runs with recorded test evidence belong here.</p><div className="empty-state"><ShieldCheck size={24}/><h2>No approved examples yet</h2><p>This installation has no gallery records. We don't publish sample output as a real run.</p><a className="text-link" href="/work">Open the workspace <ArrowRight size={15}/></a></div></main>}
    {page === 'privacy' && <main className="document-page"><div className="eyebrow">PLAIN-LANGUAGE NOTICE</div><h1>Privacy</h1><p className="doc-lede">PatchPilot is an early prototype. Treat all submitted code and reports as data you are choosing to share.</p><div className="doc-content"><h2>What may be stored</h2><p>The connected backend stores project descriptions, repository file data for projects it accepts, findings, repair plans, patches, verification records and audit events in its configured database. This build does not provide private share links, user accounts, or a configured deletion schedule.</p><h2>Model provider</h2><p>When live provider actions are enabled, submitted project context may be sent to Meta’s Model API. Do not submit secrets, credentials, personal data, or proprietary code. The provider API key is configured on the backend and is not intended for the frontend.</p><h2>Retention and controls</h2><p>Retention depends on the backend host and database configuration. No automatic seven-day deletion is implemented. Public demo controls and rate limits may be process-local and are not a durable abuse-prevention service.</p><h2>Contact and status</h2><p>This is a hackathon prototype without authentication. Use only non-sensitive sample material.</p></div></main>}
    {page === 'terms' && <main className="document-page"><div className="eyebrow">PROTOTYPE TERMS</div><h1>Terms & limitations</h1><p className="doc-lede">PatchPilot is a hackathon prototype, provided without warranty.</p><div className="doc-content"><h2>Use of suggestions</h2><p>Model-generated plans and patches can be wrong or unsafe. Review every change yourself. The current build does not execute repository code and cannot establish that a proposed fix works.</p><h2>Availability</h2><p>The service may be incomplete, unavailable, or reset during hosting restarts. There is no service-level commitment, authentication, or production support.</p><h2>Data</h2><p>Submit only material you are authorized to share. See the <a href="/privacy">Privacy notice</a> for backend storage and provider details.</p></div></main>}

    <footer className="launch-footer"><a className="launch-brand" href="/"><span className="launch-mark"><ShieldCheck size={16}/></span><span>patchpilot<span className="brand-dot">.</span></span></a><span>AI repair proposals, separated from test evidence.</span><div><a href="/gallery">Gallery</a><a href="/privacy">Privacy</a><a href="/terms">Terms</a><a href="/work">Workspace</a></div>{buildInfo && <small className="build-info">Build {buildInfo.commit === 'unknown' ? 'unknown' : buildInfo.commit.slice(0, 7)} · {buildInfo.build_date}</small>}</footer>
  </div>;
}
