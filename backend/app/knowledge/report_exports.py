"""Readable client documents. Evidence excerpts stay in the separate evidence CSV."""
from html import escape
from base64 import b64encode
from typing import Any
from urllib.parse import urlparse

from app.knowledge.publication import document


def source_url(source: dict[str, Any]) -> str:
    url = str(source.get("source_url", ""))
    return url.split("#")[0] + f"#page={source['page']}" if urlparse(url).scheme in {"https", "http"} else ""


def html(payload: dict[str, Any]) -> str:
    from app.knowledge.report_design import asset, badge_asset, number

    doc = document(payload)
    def e(x: Any) -> str:
        return escape(str(x))
    def image(path: Any, alt: str, class_name: str) -> str:
        if not path.exists():
            return f"<b>{e(alt)}</b>"
        return f"<img class='{class_name}' alt='{e(alt)}' src='data:image/png;base64,{b64encode(path.read_bytes()).decode()}'/>"

    styles = """
        *{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#eeedf3;color:#171924;font:15px/1.75 system-ui,sans-serif}
        main{max-width:980px;margin:32px auto;background:#fff;box-shadow:0 20px 80px #1719240c}
        header,section{padding:48px 64px}header{border-bottom:8px solid #8c7bc1;background:linear-gradient(130deg,#fff 55%,#eeebf7)}
        .brand{width:150px;height:auto;display:block;margin-bottom:48px}.eyebrow{font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#6855a2;font-weight:650}
        h1,h2{font-family:Georgia,serif;font-weight:400;line-height:1.15;letter-spacing:-1px}h1{font-size:48px;max-width:740px}h2{font-size:34px;margin:0 0 28px}
        h3{font-size:18px;line-height:1.5;margin:0 0 12px}p{margin:0 0 16px}small{color:#626879;font-size:12px}
        section{border-bottom:1px solid #dddfe7}article{margin:0 0 30px;padding:0 0 28px;border-bottom:1px solid #e8e8ef}article:last-child{border:0;padding-bottom:0}
        table{border-collapse:collapse;width:100%;margin:24px 0;font-size:13px}td,th{padding:13px 12px;text-align:left;border-bottom:1px solid #dddfe7;vertical-align:top}th{background:#f4f3f8;font-size:11px;text-transform:uppercase;letter-spacing:.5px}
        a{color:#6855a2;text-underline-offset:3px}a:focus-visible{outline:2px solid #6855a2;outline-offset:4px}
        .note{padding:18px 22px;background:#f4f3f8;border-left:3px solid #8c7bc1;font-size:13px;color:#626879}
        .badge{width:96px;height:96px;object-fit:contain;float:right;margin:0 0 12px 24px}.award{min-height:120px}
        .bar-row{margin:18px 0}.bar-label{display:flex;justify-content:space-between;gap:20px;font-size:13px}.track{height:8px;background:#eeedf3;position:relative;margin-top:8px;border-radius:4px}.bar{position:absolute;height:8px;background:#8c7bc1;border-radius:4px}
        nav ol{list-style:decimal-leading-zero;padding-left:32px}nav li{padding:8px 0;border-bottom:1px solid #e8e8ef}footer{padding:24px 64px;font-size:11px;color:#626879}
        @media(max-width:650px){main{margin:0}header,section{padding:32px 24px}h1{font-size:36px}h2{font-size:29px}table{font-size:11px}td,th{padding:9px 5px}footer{padding:24px}}
        @media print{body{background:white}main{margin:0;box-shadow:none}section{break-before:page;padding:24px 0}header{padding:30px 0}a{color:inherit}thead{display:table-header-group}tr{break-inside:avoid}.brand,.badge{print-color-adjust:exact}}
    """
    parts = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{e(doc['title'])}</title><style>{styles}</style></head><body><main><header>{image(asset('brand/vero-wordmark.png'), 'Vero', 'brand')}<p class='eyebrow'>{e(doc['package'])}</p><h1>{e(doc['title'])}</h1><p>{e(' / '.join(c['company_name'] for c in payload['definition']['companies']))}</p><small>Prepared {e(payload.get('created_at', '')[:10])}</small></header>"]
    if doc["incomplete"]:
        parts.append("<section><p class='note'><strong>Working draft - analysis incomplete.</strong> Saved findings only; unfinished stages are not included.</p></section>")
    parts.append("<section><p class='eyebrow'>Edition guide</p><h2>In this report</h2><nav aria-label='Report contents'><ol>")
    for i, chapter in enumerate(doc["chapters"]):
        parts.append(f"<li><a href='#chapter-{i}'>{e(chapter['title'])}</a></li>")
    for i, metric in enumerate(doc["awards"]):
        parts.append(f"<li><a href='#metric-{i}'>{e(metric['name'])}</a></li>")
    if doc['badges']:
        parts.append("<li><a href='#distinctions'>Peer distinctions</a></li>")
    parts.append("<li><a href='#sources'>The evidence index</a></li></ol></nav></section>")
    for i, chapter in enumerate(doc["chapters"]):
        parts.append(f"<section id='chapter-{i}'><p class='eyebrow'>Research &amp; comparison / {i+1:02d}</p><h2>{e(chapter['title'])}</h2>")
        for item in chapter["paragraphs"]:
            parts.append(f"<article><h3>{e(item['heading'])}</h3><p>{e(item['text'])}</p><small>Sources: " + ", ".join(f"<a href='#source-{r}'>[{r}]</a>" for r in item["references"]) + "</small></article>")
        parts.append("</section>")
    for i, award in enumerate(doc["awards"]):
        parts.append(f"<section id='metric-{i}'><p class='eyebrow'>Calculated comparison / {i+1:02d}</p><h2>{e(award['name'])}</h2><p>{e(award['criterion'])}</p>")
        values = [float(r['value']) for r in award['rows']]
        low, high = min([0, *values]), max([0, *values])
        span = high-low or 1
        zero = (0-low)/span*100
        for row in award['rows']:
            x = (float(row['value'])-low)/span*100
            parts.append(f"<div class='bar-row'><div class='bar-label'><span>{e(row['company'])}</span><b>{e(number(row['value']))} {e(row['unit'])}</b></div><div class='track' aria-hidden='true'><div class='bar' style='left:{min(zero,x):.4f}%;width:{abs(x-zero):.4f}%'></div></div></div>")
        parts.append(f"<p class='note'>Calculation: {e(award.get('formula', award['operation']))}. {e(award['caveat'])}</p><table><tr><th>Company</th><th>Result</th><th>Year</th></tr>")
        for row in award["rows"]:
            parts.append(f"<tr><td>{e(row['company'])}</td><td>{e(number(row['value']))} {e(row['unit'])}</td><td>{e(row['year'])}</td></tr>")
        parts.append("</table></section>")
    if doc["badges"]:
        parts.append("<section id='distinctions'><p class='eyebrow'>Peer distinctions</p><h2>What sets these peers apart</h2>")
        for badge in doc["badges"]:
            winners = ", ".join(r["company"] for r in badge["rows"] if r["company_id"] in badge["winner_ids"])
            parts.append(f"<article class='award'>{image(badge_asset(badge['name']), 'Peer distinction', 'badge')}<h3>{e(badge['name'])}</h3><b>{e(winners or 'Not awarded')}</b><p>{e(badge['why_it_matters'])}</p></article>")
        parts.append("</section>")
    if doc["disclosure_scores"] and doc["disclosure_scores"].get("criteria"):
        parts.append("<section><h2>Disclosure scorecard</h2><table><tr><th>Company</th><th>Score / 100</th><th>Deductions</th></tr>")
        for row in doc["disclosure_scores"]["rows"]:
            parts.append(f"<tr><td>{e(row['company'])}</td><td>{e(round(row['score'], 1) if row['score'] is not None else 'Pending')}</td><td>{e('; '.join(d['criterion'] for d in row['deductions']))}</td></tr>")
        parts.append("</table></section>")
    if doc["promises"]:
        parts.append(f"<section><p class='note'>The companion workbook contains the full {len(doc['promises'])}-entry promise register, with deadlines, reported delivery and source links. Material promise comparisons are discussed in the chapters above.</p></section>")
    parts.append("<section id='sources'><p class='eyebrow'>Source references</p><h2>The evidence index</h2>")
    for s in doc["references"]:
        parts.append(f"<p id='source-{s['reference']}'>[{s['reference']}] {e(s['company'])}. {e(s['report'])}. <a href='{e(source_url(s))}'>Physical page {s['page']}</a></p>")
    parts.append("</section><footer>VERO / SUSTAINABILITY PEER INTELLIGENCE</footer></main></body></html>")
    return "".join(parts)


def pdf(payload: dict[str, Any]) -> bytes:
    from app.knowledge.report_design import render_pdf

    return render_pdf(payload, document(payload), source_url)
