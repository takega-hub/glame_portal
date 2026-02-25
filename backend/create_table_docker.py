"""
Создание таблицы knowledge_documents через Docker exec
"""
import subprocess
import sys
import os

def create_table_via_docker():
    """Создание таблицы через Docker exec"""
    container_name = "glame_postgres"
    
    print("=" * 60)
    print("Creating knowledge_documents table via Docker")
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
            print("\nStart it with:")
            print(f"  docker start {container_name}")
            print("Or start all services:")
            print("  cd infra && docker-compose up -d")
            return False
        
        print(f"[OK] Container '{container_name}' is running")
        print()
        
        # Читаем SQL файл
        sql_file = os.path.join(os.path.dirname(__file__), "create_knowledge_documents_table.sql")
        
        if not os.path.exists(sql_file):
            print(f"[ERROR] SQL file not found: {sql_file}")
            return False
        
        with open(sql_file, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        print("Executing SQL script...")
        
        # Выполняем SQL через docker exec
        result = subprocess.run(
            [
                "docker", "exec", "-i", container_name,
                "psql", "-U", "glame_user", "-d", "glame_db"
            ],
            input=sql_content,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print("[OK] SQL script executed successfully!")
            print()
            if result.stdout:
                print("Output:")
                print(result.stdout)
            
            # Проверяем, что таблица создана
            check_result = subprocess.run(
                [
                    "docker", "exec", container_name,
                    "psql", "-U", "glame_user", "-d", "glame_db", "-t", "-c",
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'knowledge_documents';"
                ],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if check_result.returncode == 0 and "1" in check_result.stdout.strip():
                print("=" * 60)
                print("[SUCCESS] Table 'knowledge_documents' created successfully!")
                print("=" * 60)
                print("\nNext step: Mark migration as completed:")
                print("  alembic stamp head")
                return True
            else:
                print("[WARNING] Table creation may have failed. Check output above.")
                return False
        else:
            print("[ERROR] Failed to execute SQL script")
            if result.stderr:
                print("Error output:")
                print(result.stderr)
            if result.stdout:
                print("Standard output:")
                print(result.stdout)
            return False
            
    except FileNotFoundError:
        print("[ERROR] Docker is not installed or not in PATH")
        print("Install Docker Desktop: https://www.docker.com/products/docker-desktop")
        return False
    except subprocess.TimeoutExpired:
        print("[ERROR] Operation timed out")
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = create_table_via_docker()
    sys.exit(0 if success else 1)
