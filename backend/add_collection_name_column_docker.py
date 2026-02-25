"""
Добавление колонки collection_name в knowledge_documents через Docker exec
"""
import subprocess
import sys
import os


def run():
    container_name = "glame_postgres"
    sql_file = os.path.join(os.path.dirname(__file__), "add_collection_name_column.sql")

    result = subprocess.run(
        ["docker", "ps", "--filter", f"name={container_name}", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    if container_name not in result.stdout:
        print(f"[ERROR] Container '{container_name}' is not running")
        return 1

    with open(sql_file, "r", encoding="utf-8") as f:
        sql = f.read()

    r = subprocess.run(
        ["docker", "exec", "-i", container_name, "psql", "-U", "glame_user", "-d", "glame_db"],
        input=sql,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if r.returncode != 0:
        print("[ERROR] Failed to apply SQL")
        print(r.stderr)
        return r.returncode

    print(r.stdout.strip() or "[OK] Applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())

