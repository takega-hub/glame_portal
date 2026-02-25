"""
Отметка миграции как выполненной через Docker exec
Обход проблемы с psycopg2 в Alembic
"""
import subprocess
import sys

def stamp_migration():
    """Отметка миграции 003_knowledge_documents как выполненной"""
    container_name = "glame_postgres"
    revision = "003_knowledge_documents"
    
    print("=" * 60)
    print("Marking migration as completed")
    print("=" * 60)
    
    # Проверяем, запущен ли контейнер
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={container_name}", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if container_name not in result.stdout:
            print(f"[ERROR] Container '{container_name}' is not running")
            return False
        
        print(f"[OK] Container '{container_name}' is running")
        print()
        
        # Проверяем, существует ли таблица alembic_version
        check_table = subprocess.run(
            [
                "docker", "exec", container_name,
                "psql", "-U", "glame_user", "-d", "glame_db", "-t", "-c",
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'alembic_version';"
            ],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if check_table.returncode != 0 or "1" not in check_table.stdout.strip():
            print("[WARNING] Table 'alembic_version' does not exist. Creating it...")
            create_table_sql = """
                CREATE TABLE IF NOT EXISTS alembic_version (
                    version_num VARCHAR(32) NOT NULL PRIMARY KEY
                );
            """
            subprocess.run(
                [
                    "docker", "exec", "-i", container_name,
                    "psql", "-U", "glame_user", "-d", "glame_db"
                ],
                input=create_table_sql,
                capture_output=True,
                text=True,
                timeout=10
            )
        
        # Вставляем запись о миграции
        print(f"Inserting migration record: {revision}")
        
        insert_sql = f"""
            INSERT INTO alembic_version (version_num) 
            VALUES ('{revision}') 
            ON CONFLICT (version_num) DO NOTHING;
        """
        
        result = subprocess.run(
            [
                "docker", "exec", "-i", container_name,
                "psql", "-U", "glame_user", "-d", "glame_db"
            ],
            input=insert_sql,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            print("[OK] Migration record inserted successfully!")
            
            # Проверяем текущую версию
            check_version = subprocess.run(
                [
                    "docker", "exec", container_name,
                    "psql", "-U", "glame_user", "-d", "glame_db", "-t", "-c",
                    "SELECT version_num FROM alembic_version;"
                ],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if check_version.returncode == 0:
                print("\nCurrent migration version:")
                print(check_version.stdout.strip())
            
            print("\n" + "=" * 60)
            print("[SUCCESS] Migration marked as completed!")
            print("=" * 60)
            return True
        else:
            print("[ERROR] Failed to insert migration record")
            if result.stderr:
                print("Error output:")
                print(result.stderr)
            return False
            
    except FileNotFoundError:
        print("[ERROR] Docker is not installed or not in PATH")
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = stamp_migration()
    sys.exit(0 if success else 1)
