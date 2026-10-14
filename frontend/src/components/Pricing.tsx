import {useState, type FormEvent} from "react";
import {motion} from 'framer-motion';
import {PackageArt} from './ui/package-art';
import {PressDepth} from './ui/press-depth';
import {Link, useNavigation} from "../lib/navigation";
import "../pricing.css";

export const packages = [
  {id: "company", name: "Company benchmark", price: "$5,000", audience: "For sustainability and strategy teams.", features: ["Your company and four agreed peers", "Excel workbook of findings, figures and sources", "Emissions, people and innovation comparisons", "Disclosure gaps and calculated award criteria", "Written briefing and a findings consultation"]},
  {id: "sector", name: "Sector intelligence", price: "$10,000", audience: "For banks, investors and sector teams.", features: ["An agreed sector cohort and reporting cycle", "Cross-company patterns and emerging themes", "Carbon credits, transition plans and reported progress", "Sector workbook, charts and research briefing", "Tailored questions and a findings consultation"]},
] as const;

export function Pricing() {
  return <section className="pricing-page"><header className="report-page-heading"><div><span className="report-eyebrow">Research packages</span><h1>Choose the questions. Get the insight.</h1><p>A defined peer group, an annual report and an evidence workbook you can use.</p></div></header>
    <div className="pricing-grid">{packages.map(plan => <motion.article whileHover="hover" whileFocus="hover" className="pricing-card" data-package={plan.id} key={plan.id}><div className="pricing-header"><PackageArt variant={plan.id}/><div className="pricing-plan"><span className="report-eyebrow">{plan.id==='company'?'01 / Your position':'02 / The wider picture'}</span><h2>{plan.name}</h2></div><div className="pricing-price"><strong>{plan.price}</strong><span>USD / annual edition</span></div><p className="pricing-description">{plan.audience}</p></div><div className="pricing-body"><ul className="pricing-list">{plan.features.map(feature => <li key={feature}><span aria-hidden="true">✓</span>{feature}</li>)}</ul><Link className="report-button solid" href={`/contact?package=${plan.id}`}>Request {plan.name.toLowerCase()} ↗</Link></div></motion.article>)}</div>
    <p className="report-caption pricing-note">Proposed packages. Final scope and price are agreed in a consultation; checkout is not enabled.</p>
    <div className="workspace-panel pricing-detail"><h2>Start with a conversation.</h2><ol className="commercial-steps"><li>Prepare your package request and tell us which companies or questions matter.</li><li>Agree the peer group, source coverage, timing and deliverables in a consultation.</li><li>Receive client access after the scope is agreed. Repeat with the next reporting cycle.</li></ol><Link className="workspace-text-button" href="/methodology">How the research works ↗</Link></div>
  </section>;
}

export function PackageEnquiry({salesEmail = import.meta.env.VITE_SALES_EMAIL ?? ""}: {salesEmail?: string}) {
  const {search} = useNavigation();
  const initial = new URLSearchParams(search).get("package");
  const [plan, setPlan] = useState(packages.find(p => p.id === initial)?.id ?? "company");
  const [name, setName] = useState(""), [company, setCompany] = useState(""), [email, setEmail] = useState(""), [scope, setScope] = useState("");
  const [prepared, setPrepared] = useState(false);
  const selected = packages.find(p => p.id === plan)!;
  const recipient = salesEmail.trim();
  const emailReady = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(recipient);
  const request = `Vero package enquiry\n\nPackage: ${selected.name}\nIndicative price: ${selected.price} USD / annual edition\nName: ${name.trim()}\nCompany: ${company.trim()}\nEmail: ${email.trim()}\n\nResearch questions / peer group:\n${scope.trim()}\n\nNext step: consultation to agree scope, followed by client access.\n`;
  function prepare(event: FormEvent) {event.preventDefault(); setPrepared(true);}
  function download() {
    const url = URL.createObjectURL(new Blob([request], {type: "text/plain;charset=utf-8"}));
    const link = document.createElement("a"); link.href = url; link.download = "Vero-package-enquiry.txt"; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <section><Link className="report-back" href="/pricing">← Packages</Link><header className="report-page-heading"><div><span className="report-eyebrow">Package enquiry</span><h1>What would you like to understand?</h1><p>Set out your questions. The scope comes next.</p></div></header><div className="enquiry-layout">
    <div className="workspace-panel">{!prepared ? <form className="enquiry-form" onSubmit={prepare}>
      <label>Package<select value={plan} onChange={e => setPlan(e.target.value as typeof plan)}>{packages.map(p => <option key={p.id} value={p.id}>{p.name} · {p.price}</option>)}</select></label>
      <label>Your name<input required autoComplete="name" maxLength={100} value={name} onChange={e => setName(e.target.value)}/></label>
      <label>Company<input required autoComplete="organization" maxLength={150} value={company} onChange={e => setCompany(e.target.value)}/></label>
      <label>Work email<input required type="email" autoComplete="email" maxLength={254} value={email} onChange={e => setEmail(e.target.value)}/></label>
      <label>Questions or companies to explore<textarea required maxLength={3000} value={scope} onChange={e => setScope(e.target.value)} placeholder="Which peers, sector or questions should the research cover?"/></label>
      <PressDepth type="submit">Prepare request →</PressDepth>
      <p className="report-caption">Your details stay in this page until you choose to export or email them.</p>
    </form> : <><h2>Your request is ready to share.</h2><p role="status">Not sent. {emailReady ? "Open your email app to review and send it." : "Vero’s enquiry address has not been set up yet. Download your brief to share directly."}</p><pre className="enquiry-summary">{request}</pre><div className="report-actions">{emailReady && <a className="report-button solid" href={`mailto:${recipient}?subject=${encodeURIComponent(`Vero — ${selected.name} enquiry`)}&body=${encodeURIComponent(request)}`}>Open email draft ↗</a>}<button className="report-button" onClick={download}>Download request ↓</button><button className="workspace-text-button" onClick={() => setPrepared(false)}>Edit request</button></div></>}
    </div><aside className="workspace-panel"><h2>{selected.name}</h2><p>{selected.price} USD / annual edition</p><ol className="commercial-steps"><li>Package request</li><li>Consultation and agreed scope</li><li>Client access and research delivery</li></ol><p className="report-caption">No payment or account is created by this form.</p></aside>
  </div></section>;
}
