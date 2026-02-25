"""
Проверка создания таблицы knowledge_documents
"""
import subprocess
import sys

def verify_table():
    """Проверка существования и структуры таблицы"""
    container_name = "glame_postgres"
    
    print("=" * 60)
    print("Verifying knowledge_documents table")
    print("=" * 60)
    
    try:
        # Проверяем существование таблицы
        check_table = subprocess.run(
            [
                "docker", "exec", container_name,
                "psql", "-U", "glame_user", "-d", "glame_db", "-t", "-c",
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'knowledge_documents';"
            ],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if "1" in check_table.stdout.strip():
            print("[OK] Table 'knowledge_documents' exists")
        else:
            print("[ERROR] Table 'knowledge_documents' does not exist")
            return False
        
        # Показываем структуру таблицы
        print("\nTable structure:")
        structure = subprocess.run(
            [
                "docker", "exec", container_name,
                "psql", "-U", "glame_user", "-d", "glame_db", "-c",
                "\\d knowledge_documents"
            ],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if structure.returncode == 0:
            print(structure.stdout)
        
        # Проверяем индексы
        print("\nIndexes:")
        indexes = subprocess.run(
            [
                "docker", "exec", container_name,
                "psql", "-U", "glame_user", "-d", "glame_db", "-t", "-c",
                "SELECT indexname FROM pg_indexes WHERE tablename = 'knowledge_documents';"
            ],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if indexes.returncode == 0:
            for idx in indexes.stdout.strip().split('\n'):
                if idx.strip():
                    print(f"  - {idx.strip()}")
        
        print("\n" + "=" * 60)
        print("[SUCCESS] Table verification completed!")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"[ERROR] Verification failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = verify_table()
    sys.exit(0 if success else 1)
