content = """# Backend
DATABASE_URL=postgresql://glame_user:glame_password@localhost:5432/glame_db
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
REDIS_URL=redis://localhost:6379
OPENROUTER_API_KEY=your_openrouter_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
JWT_SECRET_KEY=your_jwt_secret_key_change_in_production
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000

# Application
ENVIRONMENT=development
LOG_LEVEL=INFO
"""

with open('.env.example', 'w', encoding='utf-8') as f:
    f.write(content)

print(".env.example created successfully!")
