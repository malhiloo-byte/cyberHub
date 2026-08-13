import { Button } from "@/components/ui/button";
/*
 * CyberOS Obsidian Command Center: editorial Swiss rhythm, quiet luxury materials,
 * brass trust signals, and evidence-first operational hierarchy.
 */
import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  Activity,
  ArrowUpRight,
  Bell,
  Braces,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  Crosshair,
  Database,
  FileSearch,
  Fingerprint,
  Globe2,
  LayoutDashboard,
  LockKeyhole,
  Menu,
  Network,
  Radar,
  ServerCog,
  ShieldCheck,
  SlidersHorizontal,
  Target,
  TerminalSquare,
  X,
  Zap,
} from "lucide-react";

type NavItem = { label: string; icon: typeof LayoutDashboard; count?: string };

const navItems: NavItem[] = [
  { label: "Command Center", icon: LayoutDashboard },
  { label: "Engagements", icon: Crosshair, count: "03" },
  { label: "Scope & Targets", icon: Target, count: "12" },
  { label: "Task Execution", icon: TerminalSquare, count: "04" },
  { label: "Evidence Vault", icon: FileSearch, count: "28" },
];

const activity = [
  { time: "09:42:18", label: "Scope authorization renewed", detail: "API Security Lab / production-shadow", tone: "brass" },
  { time: "09:37:04", label: "Task completed", detail: "HTTP header baseline · 1.4s", tone: "teal" },
  { time: "09:31:52", label: "Target excluded", detail: "admin.example.com · policy precedence", tone: "red" },
  { time: "09:18:11", label: "Evidence indexed", detail: "response-headers.json · 4.8 KB", tone: "muted" },
];

const scopes = [
  { name: "API Security Lab", target: "api.example.com", state: "AUTHORIZED", expiry: "11h 24m", coverage: 86 },
  { name: "Web Pentest / Staging", target: "staging.example.net", state: "VALIDATED", expiry: "Pending", coverage: 58 },
  { name: "Network Foundations", target: "192.0.2.0/24", state: "DRAFT", expiry: "Not set", coverage: 24 },
];

const tasks = [
  { id: "tsk_01J4…91A", label: "Header baseline", status: "COMPLETED", duration: "1.4s", accent: "teal" },
  { id: "tsk_01J4…8E2", label: "TLS posture check", status: "RUNNING", duration: "00:18", accent: "brass" },
  { id: "tsk_01J4…7BF", label: "OpenAPI inventory", status: "QUEUED", duration: "—", accent: "muted" },
];

function StatusPill({ label, tone = "muted" }: { label: string; tone?: string }) {
  return <span className={`status-pill status-pill--${tone.toLowerCase()}`}>{label}</span>;
}

function SectionLabel({ index, children }: { index: string; children: ReactNode }) {
  return (
    <div className="section-label">
      <span className="section-label__index">{index}</span>
      <span>{children}</span>
    </div>
  );
}

export default function Home() {
  const [activeNav, setActiveNav] = useState("Command Center");
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [showAllScopes, setShowAllScopes] = useState(false);

  const visibleScopes = useMemo(() => (showAllScopes ? scopes : scopes.slice(0, 2)), [showAllScopes]);

  const announce = (message: string) => {
    setNotice(message);
    window.setTimeout(() => setNotice(null), 2800);
  };

  const chooseNav = (label: string) => {
    setActiveNav(label);
    setMobileNavOpen(false);
    announce(`${label} view selected`);
  };

  return (
    <div className="cyber-shell">
      <aside className={`command-rail ${mobileNavOpen ? "command-rail--open" : ""}`}>
        <div className="rail-brand">
          <div className="brand-mark" aria-hidden="true"><span /></div>
          <div>
            <p className="brand-name">CYBER<span>OS</span></p>
            <p className="brand-subtitle">PERSONAL SECURITY OS</p>
          </div>
          <button className="rail-close" type="button" onClick={() => setMobileNavOpen(false)} aria-label="Close navigation">
            <X size={16} />
          </button>
        </div>

        <div className="rail-context">
          <span className="rail-context__eyebrow">ACTIVE WORKSPACE</span>
          <div className="rail-context__name"><span className="presence-dot" />Web Security Lab</div>
          <span className="rail-context__meta">3 engagements · 12 targets</span>
        </div>

        <nav className="rail-nav" aria-label="Primary navigation">
          <span className="rail-nav__title">OPERATIONS</span>
          {navItems.map(({ label, icon: Icon, count }) => (
            <button
              className={`rail-link ${activeNav === label ? "rail-link--active" : ""}`}
              key={label}
              type="button"
              onClick={() => chooseNav(label)}
              aria-current={activeNav === label ? "page" : undefined}
            >
              <Icon size={17} strokeWidth={1.8} />
              <span>{label}</span>
              {count && <span className="rail-link__count">{count}</span>}
              {activeNav === label && <ChevronRight className="rail-link__chevron" size={14} />}
            </button>
          ))}
          <span className="rail-nav__title rail-nav__title--lower">SYSTEM</span>
          <button className="rail-link" type="button" onClick={() => announce("Audit trail is always on") }><Activity size={17} strokeWidth={1.8} /><span>Audit Trail</span></button>
          <button className="rail-link" type="button" onClick={() => announce("System settings are local-first") }><SlidersHorizontal size={17} strokeWidth={1.8} /><span>System Settings</span></button>
        </nav>

        <div className="rail-footer">
          <div className="rail-footer__status"><span className="presence-dot presence-dot--teal" />Core systems nominal</div>
          <div className="rail-footer__version"><span>CYBEROS CORE</span><span>v0.5.0</span></div>
        </div>
      </aside>

      <main className="command-main">
        <header className="utility-bar">
          <button className="mobile-menu" type="button" onClick={() => setMobileNavOpen(true)} aria-label="Open navigation"><Menu size={20} /></button>
          <div className="breadcrumb"><span>CYBEROS</span><ChevronRight size={13} /><strong>{activeNav.toUpperCase()}</strong></div>
          <div className="utility-actions">
            <div className="system-status"><span className="presence-dot presence-dot--teal" />LOCAL-FIRST <span className="system-status__divider" /> SECURE</div>
            <button className="icon-button" type="button" onClick={() => announce("No new alerts")} aria-label="Notifications"><Bell size={17} /><span className="notification-dot" /></button>
            <button className="avatar-button" type="button" onClick={() => announce("Operator profile")}>ML</button>
          </div>
        </header>

        <div className="command-content">
          <section className="page-intro" id="command-center">
            <div>
              <SectionLabel index="00">OPERATIONAL BRIEFING · 14 AUG 2026</SectionLabel>
              <h1>Operate inside<br /><em>your boundary.</em></h1>
              <p className="intro-copy">One auditable surface for scope, execution, evidence, and the next deliberate move.</p>
            </div>
            <div className="intro-actions">
              <button className="button button--ghost" type="button" onClick={() => announce("Scope review opened before execution")}>Review scope before execution <ArrowUpRight size={15} /></button>
              <button className="button button--brass" type="button" onClick={() => announce("Queue only an authorized task")}>Queue authorized task <Zap size={15} /></button>
            </div>
          </section>

          <section className="hero-grid" aria-label="Operational overview">
            <article className="posture-card panel panel--brass-edge">
              <div className="panel-topline"><SectionLabel index="01">OPERATIONAL POSTURE</SectionLabel><span className="live-indicator"><span />LIVE SNAPSHOT</span></div>
              <div className="posture-main">
                <div className="posture-ring" aria-label="86 percent scope coverage"><div><strong>86</strong><span>%</span><small>COVERAGE</small></div></div>
                <div className="posture-copy"><p className="posture-kicker">TRUST LAYER</p><h2>Authorization<br />is healthy.</h2><p>Every active execution is bound to an approved scope and target.</p><button className="text-link" type="button" onClick={() => announce("Trust layer details opened")}>Inspect trust layer <ArrowUpRight size={14} /></button></div>
              </div>
              <div className="posture-metrics"><div><span>AUTHORIZED</span><strong>01</strong></div><div><span>EXPIRES IN</span><strong>11h 24m</strong></div><div><span>LAST CHECK</span><strong>09:42</strong></div></div>
            </article>
            <article className="authorization-card panel">
              <div className="panel-topline"><SectionLabel index="02">AUTHORIZATION BRIEF</SectionLabel><LockKeyhole size={16} className="icon-brass" /></div>
              <div className="auth-heading"><span className="auth-stamp">SCOPE / 01</span><StatusPill label="AUTHORIZED" tone="brass" /></div>
              <h2>API Security Lab</h2><p className="auth-target"><Globe2 size={14} /> api.example.com <span>·</span> production-shadow</p>
              <div className="auth-rule"><span className="auth-rule__line" /><span>INCLUDE OVERRIDES DENY ONLY WHEN EXPLICIT</span></div>
              <div className="auth-footer"><div><span>REFERENCE</span><strong>approval-123</strong></div><div><span>EXPIRY</span><strong>25 AUG · 21:06 UTC</strong></div><button className="round-button" type="button" onClick={() => announce("Authorization record copied")} aria-label="Copy authorization record"><Braces size={16} /></button></div>
            </article>
          </section>

          <section className="metric-grid" aria-label="System metrics">
            <div className="metric-card"><div className="metric-card__top"><span>ACTIVE TARGETS</span><Target size={15} /></div><strong>12</strong><span className="metric-change metric-change--up"><ArrowUpRight size={12} /> 08% this week</span></div>
            <div className="metric-card"><div className="metric-card__top"><span>TASKS TODAY</span><TerminalSquare size={15} /></div><strong>04</strong><span className="metric-change metric-change--up"><ArrowUpRight size={12} /> 100% completed</span></div>
            <div className="metric-card"><div className="metric-card__top"><span>EVIDENCE INDEXED</span><Database size={15} /></div><strong>28</strong><span className="metric-change">+09 artifacts · 24h</span></div>
            <div className="metric-card metric-card--alert"><div className="metric-card__top"><span>POLICY EVENTS</span><CircleAlert size={15} /></div><strong>01</strong><span className="metric-change metric-change--alert">Excluded target blocked</span></div>
          </section>

          <section className="content-grid">
            <article className="panel activity-panel" id="audit-trail">
              <div className="panel-heading"><div><SectionLabel index="03">AUDIT ACTIVITY</SectionLabel><h2>What changed.</h2></div><button className="text-link" type="button" onClick={() => chooseNav("Audit Trail")}>View all <ArrowUpRight size={14} /></button></div>
              <div className="activity-list">{activity.map((item) => <div className="activity-row" key={`${item.time}-${item.label}`}><span className={`activity-marker activity-marker--${item.tone}`} /><div className="activity-time">{item.time}</div><div className="activity-detail"><strong>{item.label}</strong><span>{item.detail}</span></div><ChevronRight size={15} className="activity-arrow" /></div>)}</div>
            </article>
            <article className="panel trajectory-panel">
              <div className="panel-heading"><div><SectionLabel index="04">BUILD TRAJECTORY</SectionLabel><h2>Your next layer.</h2></div><Radar size={19} className="icon-brass" /></div>
              <div className="trajectory-track"><div className="trajectory-progress" /><span className="trajectory-node trajectory-node--done" /><span className="trajectory-node trajectory-node--current" /><span className="trajectory-node" /><span className="trajectory-node" /></div>
              <div className="trajectory-steps"><div><small>01</small><strong>CORE</strong><span>Complete</span></div><div className="trajectory-current"><small>02</small><strong>RECON</strong><span>Design next</span></div><div><small>03</small><strong>WEB PENTEST</strong><span>Queued</span></div><div><small>04</small><strong>API SECURITY</strong><span>Queued</span></div></div>
              <button className="wide-action" type="button" onClick={() => announce("Open the Module 1 architecture brief before reconnaissance")}>Review Module 1 architecture <ChevronRight size={16} /></button>
            </article>
          </section>

          <section className="panel table-panel" id="scope-targets">
            <div className="panel-heading"><div><SectionLabel index="05">SCOPE REGISTER</SectionLabel><h2>Boundaries in view.</h2></div><button className="button button--small button--ghost" type="button" onClick={() => setShowAllScopes(!showAllScopes)}>{showAllScopes ? "Collapse" : "View register"} <ArrowUpRight size={14} /></button></div>
            <div className="scope-table"><div className="scope-table__head"><span>SCOPE / ENGAGEMENT</span><span>PRIMARY TARGET</span><span>STATE</span><span>EXPIRY</span><span>COVERAGE</span><span /></div>{visibleScopes.map((scope) => <div className="scope-table__row" key={scope.name}><div className="scope-name"><span className="scope-icon"><Globe2 size={14} /></span><div><strong>{scope.name}</strong><small>Web Security Lab</small></div></div><span className="mono-text">{scope.target}</span><StatusPill label={scope.state} tone={scope.state === "AUTHORIZED" ? "brass" : scope.state === "VALIDATED" ? "teal" : "muted"} /><span className="mono-text">{scope.expiry}</span><div className="coverage-cell"><div className="coverage-bar"><span style={{ width: `${scope.coverage}%` }} /></div><span>{scope.coverage}%</span></div><button className="row-action" type="button" onClick={() => announce(`${scope.name} selected`)} aria-label={`Open ${scope.name}`}><ChevronRight size={16} /></button></div>)}</div>
          </section>

          <section className="bottom-grid" id="tasks">
            <article className="panel task-panel"><div className="panel-heading"><div><SectionLabel index="06">TASK EXECUTION</SectionLabel><h2>Recent runs.</h2></div><button className="icon-button" type="button" onClick={() => announce("Task queue refreshed")} aria-label="Refresh tasks"><Activity size={16} /></button></div><div className="task-list">{tasks.map((task) => <div className="task-row" key={task.id}><span className={`task-status-dot task-status-dot--${task.accent}`} /> <div className="task-row__main"><strong>{task.label}</strong><span className="mono-text">{task.id}</span></div><StatusPill label={task.status} tone={task.accent} /><span className="mono-text task-duration">{task.duration}</span><button className="row-action" type="button" onClick={() => announce(`${task.label} details opened`)} aria-label={`Open ${task.label}`}><ArrowUpRight size={14} /></button></div>)}</div></article>
            <article className="panel system-panel"><div className="panel-heading"><div><SectionLabel index="07">SYSTEM HEALTH</SectionLabel><h2>Quietly ready.</h2></div><ServerCog size={19} className="icon-brass" /></div><div className="health-list"><div><span><span className="presence-dot presence-dot--teal" />Core contracts</span><strong>ONLINE</strong></div><div><span><span className="presence-dot presence-dot--teal" />SQLite persistence</span><strong>HEALTHY</strong></div><div><span><span className="presence-dot presence-dot--teal" />Scope matcher</span><strong>ENFORCED</strong></div><div><span><span className="presence-dot presence-dot--brass" />Recon layer</span><strong className="health-muted">NEXT MODULE</strong></div></div><div className="system-footnote"><Fingerprint size={15} /> Privacy-first · local evidence · explicit authorization</div></article>
          </section>

          <footer className="command-footer"><div><div className="footer-mark"><div className="brand-mark brand-mark--small" aria-hidden="true"><span /></div><span>CYBEROS</span></div><p>Personal Cybersecurity Engineering OS</p></div><div className="footer-meta"><span>CORE v0.5.0</span><span>·</span><span>LOCAL-FIRST</span><span>·</span><span>ALL SYSTEMS NOMINAL</span><span className="presence-dot presence-dot--teal" /></div></footer>
        </div>
      </main>

      {notice && <div className="toast" role="status"><CheckCircle2 size={16} />{notice}</div>}
    </div>
  );
}
