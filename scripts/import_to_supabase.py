"""Import local Docker DB data into Supabase.

Usage:
    pip install psycopg2-binary
    python scripts/import_to_supabase.py

Connects to Supabase session pooler and inserts all data
(clients, campaigns, leads, scrape_jobs, audit_logs).
"""

import re
import sys
from pathlib import Path

try:
    import psycopg2
except ImportError:
    print("Install psycopg2-binary first: pip install psycopg2-binary")
    sys.exit(1)

# Supabase session pooler connection
SUPABASE_HOST = "aws-1-us-east-1.pooler.supabase.com"
SUPABASE_PORT = 5432
SUPABASE_DB = "postgres"
SUPABASE_USER = "postgres.gnqisyjnhfnhdwjoapet"
SUPABASE_PASSWORD = "FHY%+&i3@_hw-NC"

SQL_FILE = Path(__file__).parent / "supabase_import.sql"


def main():
    if not SQL_FILE.exists():
        print(f"SQL file not found: {SQL_FILE}")
        print("Generate it first or place it in the scripts/ directory.")
        sys.exit(1)

    print(f"Connecting to Supabase at {SUPABASE_HOST}...")
    conn = psycopg2.connect(
        host=SUPABASE_HOST,
        port=SUPABASE_PORT,
        dbname=SUPABASE_DB,
        user=SUPABASE_USER,
        password=SUPABASE_PASSWORD,
        sslmode="require",
    )
    conn.autocommit = False
    cur = conn.cursor()
    print("Connected!\n")

    # Check current state
    print("Current data in Supabase:")
    for table in ["clients", "campaigns", "leads", "scrape_jobs", "audit_logs"]:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            print(f"  {table}: {count} rows")
        except Exception as e:
            conn.rollback()
            print(f"  {table}: ERROR - {e}")

    print()
    answer = input("Proceed with import? This will INSERT data (not delete existing). [y/N]: ")
    if answer.lower() != "y":
        print("Aborted.")
        conn.close()
        return

    # Read and execute SQL file
    with open(SQL_FILE) as f:
        content = f.read()

    # Split into individual statements
    statements = []
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("INSERT INTO"):
            statements.append(line)

    # Execute in order
    table_order = ["clients", "campaigns", "leads", "scrape_jobs", "audit_logs"]
    success = 0
    errors = 0

    for table in table_order:
        table_stmts = [s for s in statements if f"INSERT INTO public.{table}" in s]
        if not table_stmts:
            continue

        print(f"\nImporting {table} ({len(table_stmts)} rows)...")
        for i, stmt in enumerate(table_stmts):
            try:
                cur.execute("SAVEPOINT sp")
                cur.execute(stmt)
                cur.execute("RELEASE SAVEPOINT sp")
                success += 1
                if (i + 1) % 10 == 0:
                    print(f"  {i + 1}/{len(table_stmts)} done")
            except psycopg2.errors.UniqueViolation:
                cur.execute("ROLLBACK TO SAVEPOINT sp")
                print(f"  Skipped duplicate in {table} (row {i + 1})")
                errors += 1
            except Exception as e:
                cur.execute("ROLLBACK TO SAVEPOINT sp")
                print(f"  ERROR on {table} row {i + 1}: {e}")
                errors += 1

        # Commit after each table
        try:
            conn.commit()
            print(f"  Committed {table}")
        except Exception as e:
            conn.rollback()
            print(f"  COMMIT ERROR for {table}: {e}")

    print(f"\nDone! {success} inserted, {errors} errors/skipped")

    # Verify final state
    print("\nFinal data in Supabase:")
    for table in ["clients", "campaigns", "leads", "scrape_jobs", "audit_logs"]:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            print(f"  {table}: {count} rows")
        except Exception as e:
            conn.rollback()
            print(f"  {table}: ERROR - {e}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
