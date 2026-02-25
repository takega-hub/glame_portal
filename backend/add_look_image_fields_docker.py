"""
Добавление полей image_urls и current_image_index в таблицу looks через Docker exec
"""
import subprocess
import sys
import os

def add_look_image_fields_via_docker():
    """Добавление полей через Docker exec"""
    container_name = "glame_postgres"
    
    print("=" * 60)
    print("Adding image_urls and current_image_index fields to looks table")
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
        sql_file = os.path.join(os.path.dirname(__file__), "add_look_image_fields.sql")
        
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
            print("[OK] Fields added successfully!")
            print()
            if result.stdout:
                print("Output:")
                print(result.stdout)
            return True
        else:
            print("[ERROR] Failed to add fields")
            print()
            if result.stderr:
                print("Error:")
                print(result.stderr)
            if result.stdout:
                print("Output:")
                print(result.stdout)
            return False
            
    except subprocess.TimeoutExpired:
        print("[ERROR] Operation timed out")
        return False
    except FileNotFoundError:
        print("[ERROR] Docker not found. Make sure Docker is installed and in PATH")
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = add_look_image_fields_via_docker()
    sys.exit(0 if success else 1)
