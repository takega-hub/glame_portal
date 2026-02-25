"""
Проверка доступности PostgreSQL
"""
import socket
import sys

def check_port(host, port, timeout=2):
    """Проверка доступности порта"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception as e:
        print(f"Error checking port: {e}")
        return False

if __name__ == "__main__":
    host = "localhost"
    port = 5432
    
    print(f"Checking PostgreSQL on {host}:{port}...")
    
    if check_port(host, port):
        print(f"[OK] PostgreSQL is accessible on {host}:{port}")
        print("\nYou can try running the table creation script again:")
        print("  python create_table_asyncpg.py")
    else:
        print(f"[ERROR] PostgreSQL is NOT accessible on {host}:{port}")
        print("\nPossible solutions:")
        print("1. Start PostgreSQL service:")
        print("   - Windows: Check Services (services.msc) for 'postgresql'")
        print("   - Or run: net start postgresql-x64-XX (replace XX with version)")
        print("\n2. If PostgreSQL is in Docker:")
        print("   docker ps | grep postgres")
        print("   docker start <container_name>")
        print("\n3. Check PostgreSQL configuration:")
        print("   - Verify listen_addresses in postgresql.conf")
        print("   - Check pg_hba.conf for connection rules")
        print("\n4. Alternative: Create table manually via pgAdmin or DBeaver")
        print("   SQL file: backend/create_knowledge_documents_table.sql")
