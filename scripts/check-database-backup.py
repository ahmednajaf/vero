"""Back up the local Vero DB and restore into a NEW disposable database.

The original database is read-only throughout. Retain the custom-format backup;
remove only the uniquely named restore-check database created by this process.
PDFs are separately inventoried, not copied: this is not a complete disaster backup.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url
from app.core.config import Settings


def main():
    settings = Settings()
    url = make_url(settings.database_url.get_secret_value())
    if url.host not in {"localhost", "127.0.0.1", "::1"}:
        raise SystemExit("This restore smoke check is local-only")
    identifier = uuid4().hex
    destination = ROOT / "backend" / "storage" / "backups" / identifier
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    dump = destination / "database.dump"
    temporary_db = "vero_restore_" + identifier + "_test"
    common = dict(host=url.host, port=url.port or 5432, user=url.username, password=url.password)
    environment = os.environ.copy()
    if url.password:
        environment["PGPASSWORD"] = url.password
    binary = Path(os.environ.get("VERO_PG_BIN", "/opt/homebrew/opt/postgresql@17/bin"))
    flags = ["-h", url.host, "-p", str(url.port or 5432), "-U", url.username]
    created = False
    try:
        with (destination / "diagnostics.log").open("xb") as diagnostics:
            subprocess.run([str(binary / "pg_dump"), *flags, "--format=custom", "--no-owner", "--no-acl", "--file", str(dump), url.database],
                env=environment, check=True, stdout=subprocess.DEVNULL, stderr=diagnostics)
            dump.chmod(0o600)
            with psycopg.connect(**common, dbname="postgres", autocommit=True) as admin:
                admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(temporary_db)))
                created = True
            subprocess.run([str(binary / "pg_restore"), *flags, "--no-owner", "--no-acl", "--exit-on-error", "--dbname", temporary_db, str(dump)],
                env=environment, check=True, stdout=subprocess.DEVNULL, stderr=diagnostics)
        with psycopg.connect(**common, dbname=url.database) as original, psycopg.connect(**common, dbname=temporary_db) as restored:
            names = [r[0] for r in original.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")]
            counts = {}
            for name in names:
                statement = sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(name))
                source_count = original.execute(statement).fetchone()[0]
                restored_count = restored.execute(statement).fetchone()[0]
                if source_count != restored_count:
                    raise RuntimeError("Backup row-count mismatch; check for concurrent source writes")
                counts[name] = restored_count
            files = []
            for report_id, key, expected in restored.execute("SELECT id, storage_key, content_sha256 FROM reports WHERE status='downloaded'"):
                path = (settings.reports_root / (key or "")).resolve()
                good = path.is_relative_to(settings.reports_root.resolve()) and path.is_file()
                if good:
                    with path.open("rb") as content:
                        good = hashlib.file_digest(content,"sha256").hexdigest() == expected
                files.append({"report_id":str(report_id),"storage_key":key,"sha256":expected,"local_file_verified":good})
        result = {"database_restore_passed":True,"table_row_counts":counts,"pdf_manifest":files,
            "pdf_files_copied":False,"backup_file":str(dump),"original_database_modified":False}
        (destination / "manifest.json").write_text(json.dumps(result,indent=2))
        print(json.dumps({"restore_passed":True,"tables":len(counts),"pdf_files_verified":sum(r["local_file_verified"] for r in files),
            "pdf_files_checked":len(files),"backup_directory":str(destination),"pdfs_must_be_backed_up_separately":True},indent=2))
    finally:
        if created:
            with psycopg.connect(**common, dbname="postgres", autocommit=True) as admin:
                admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(temporary_db)))


if __name__ == "__main__":
    main()
