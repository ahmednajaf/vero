"""Synthetic capacity check in an isolated *_test schema, never the product library."""
import argparse
import json
import os
from pathlib import Path
import statistics
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from app.knowledge.contracts import SearchRequest
from app.knowledge.search import search


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--companies", type=int, default=500, choices=range(1, 501))
    parser.add_argument("--pages", type=int, default=200, choices=range(1, 501))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    url = os.environ["TEST_DATABASE_URL"]
    if not (make_url(url).database or "").endswith("_test"):
        raise SystemExit("Only a separately named *_test database is allowed")
    schema = "vero_load_" + uuid4().hex
    admin = create_engine(url)
    engine = create_engine(url, connect_args={"options": "-csearch_path=" + schema})
    try:
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        config = Config(str(ROOT / "backend" / "alembic.ini"))
        with engine.begin() as conn:
            config.attributes["connection"] = conn
            command.upgrade(config, "head")
        started = time.perf_counter()
        with engine.begin() as conn:
            conn.execute(text("""INSERT INTO companies (id,company_name,ticker,exchange,country,region,sector,industry,official_domain,reporting_year)
                SELECT gen_random_uuid(), 'Synthetic load fixture '||n, 'LOAD'||n, 'TEST', 'GB','Europe','Industrials','Synthetic','example.com',2025
                FROM generate_series(1,:companies) n"""), {"companies":args.companies})
            conn.execute(text("""INSERT INTO reports(id,company_id,title,report_type,source_url,requested_year,status,source_policy,content_sha256,page_count,parse_status)
                SELECT gen_random_uuid(),id,'Synthetic report; no real metrics','annual','https://example.com/'||id||'.pdf',2025,'downloaded','official',repeat('a',64),:pages,'parsed' FROM companies"""), {"pages": args.pages})
            conn.execute(text("""INSERT INTO extraction_runs(id,report_id,stage,status,idempotency_key,input_sha256,schema_version,code_version)
                SELECT gen_random_uuid(),id,'parsing','succeeded',id::text,repeat('a',64),'synthetic','synthetic' FROM reports"""))
            conn.execute(text("""INSERT INTO knowledge_indexes(id,report_id,parse_run_id,report_sha256,fingerprint,source_url,version,quality)
                SELECT gen_random_uuid(),r.id,e.id,r.content_sha256,repeat('b',64),r.source_url,'full-report-v1',jsonb_build_object('pages_total',:pages,'coverage','complete_extracted_text')
                FROM reports r JOIN extraction_runs e ON e.report_id=r.id"""), {"pages":args.pages})
            conn.execute(text("""INSERT INTO document_pages(id,report_id,parse_run_id,page_number,width_points,height_points,rotation,raw_text,ordered_text,raw_text_sha256,ordered_text_sha256,text_characters,status,headings,layout,warnings,parser_name,parser_version)
                SELECT gen_random_uuid(),report_id,parse_run_id,n,600,800,0,body,body,encode(sha256(convert_to(body,'UTF8')),'hex'),encode(sha256(convert_to(body,'UTF8')),'hex'),length(body),'parsed','[]','{}','[]','synthetic','1'
                FROM knowledge_indexes CROSS JOIN generate_series(1,:pages) n CROSS JOIN LATERAL
                (SELECT repeat('Synthetic narrative about operating practices and research coverage. ',20) || CASE WHEN n=1 THEN ' Supplier water scarcity programme.' WHEN n=2 THEN ' Biodiversity habitats.' ELSE ' General operations.' END AS body) b"""), {"pages":args.pages})
            conn.execute(text("""INSERT INTO knowledge_passages(id,index_id,page_id,ordinal,kind,content,content_sha256,locator)
                SELECT gen_random_uuid(),k.id,p.id,p.page_number-1,'text',p.raw_text,p.raw_text_sha256,'{}' FROM document_pages p JOIN knowledge_indexes k ON k.report_id=p.report_id"""))
            for name in ("companies", "reports", "extraction_runs", "document_pages", "knowledge_indexes", "knowledge_passages"):
                conn.execute(text(f"ANALYZE {name}"))
        ingestion_ms = (time.perf_counter() - started) * 1000
        checks = []
        with Session(engine) as session:
            for query in ("supplier water", "biodiversity", "operating practices"):
                samples = []
                for _ in range(3):
                    start = time.perf_counter()
                    result = search(session, SearchRequest(query=query, limit=20))
                    samples.append((time.perf_counter() - start) * 1000)
                assert result["coverage"]["companies_with_indexed_reports"] == args.companies
                assert result["coverage"]["pages_indexed"] == args.companies * args.pages
                assert result["items"] and len(result["items"]) <= 20
                checks.append({"query":query,"matching_passages":result["total"],"median_ms":round(statistics.median(samples),2),"samples_ms":[round(n,2) for n in samples]})
            size = session.scalar(text("SELECT sum(pg_total_relation_size(oid)) FROM pg_class WHERE relnamespace=CAST(:schema AS regnamespace) AND relkind='r'"), {"schema":schema})
        report = {"synthetic_only":True,"companies":args.companies,"reports":args.companies,"pages_and_passages":args.companies*args.pages,
            "load_ms":round(ingestion_ms,2),"database_bytes":int(size),"queries":checks,
            "limitations":"Single-process local read test, not a production concurrency test, extraction accuracy test or real report coverage."}
        print(json.dumps(report,indent=2))
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x") as output:
                json.dump(report,output,indent=2)
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


if __name__ == "__main__":
    main()
