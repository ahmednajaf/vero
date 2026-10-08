import type {ComponentProps} from "react";
import {Link} from "../lib/navigation";
import "../pricing.css";

// Adapted from the composable glass pricing card supplied by the user.
// Existing Vero colours/materials are used instead of adding a second theme.
function Card({className = "", ...props}: ComponentProps<"div">) {return <div className={`pricing-card ${className}`} {...props}/>;}
function Header({children, ...props}: ComponentProps<"div">) {return <div className="pricing-header" {...props}><div className="pricing-glass" aria-hidden="true"/>{children}</div>;}
function Plan(props: ComponentProps<"div">) {return <div className="pricing-plan" {...props}/>;}
function Description(props: ComponentProps<"p">) {return <p className="pricing-description" {...props}/>;}
function Badge(props: ComponentProps<"span">) {return <span className="pricing-badge" {...props}/>;}
function Price(props: ComponentProps<"div">) {return <div className="pricing-price" {...props}/>;}
function Body(props: ComponentProps<"div">) {return <div className="pricing-body" {...props}/>;}
function List(props: ComponentProps<"ul">) {return <ul className="pricing-list" {...props}/>;}
function ListItem({children}: ComponentProps<"li">) {return <li><span aria-hidden="true">✓</span>{children}</li>;}

const plans = [
  {name: "Company benchmark", price: "$5,000", audience: "For sustainability and strategy teams.", features: ["Your company and four selected peers", "Reported metrics with page-level sources", "Peer differences and disclosure gaps", "Exportable briefing and source evidence"]},
  {name: "Sector intelligence", price: "$10,000", audience: "For banks, investors and sector teams.", features: ["An agreed sector research scope", "Cross-company disclosure analysis", "Source-backed findings and comparisons", "An annual edition with its evidence pack"]},
];

export function Pricing() {
  return <section className="pricing-page"><header className="report-page-heading"><div><span className="report-eyebrow">Annual research packages</span><h1>Annual benchmarks.</h1><p>Company comparisons and sector intelligence, with the evidence included.</p></div></header>
    <div className="pricing-grid">{plans.map((plan, index) => <Card key={plan.name}><Header><Plan><h2>{plan.name}</h2>{index === 0 && <Badge>Company teams</Badge>}</Plan><Price><strong>{plan.price}</strong><span>USD / annual edition</span></Price><Description>{plan.audience}</Description></Header><Body><List>{plan.features.map(feature => <ListItem key={feature}>{feature}</ListItem>)}</List><Link className="report-button solid" href={index === 0 ? "/compare" : "/companies"}>{index === 0 ? "Build your peer group" : "Explore sector coverage"} ↗</Link></Body></Card>)}</div>
    <p className="report-caption pricing-note">Proposed commercial packages. Coverage and deliverables are agreed before purchase; checkout is not enabled.</p>
    <div className="pricing-detail"><h2>Built around public evidence.</h2><p>Assess the available company reports before choosing a scope. No independent ESG rating or complete-market coverage is implied.</p><Link href="/sources">Explore source reports ↗</Link></div>
  </section>;
}
