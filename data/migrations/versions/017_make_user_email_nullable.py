"""make user email nullable

Revision ID: 017_make_user_email_nullable
Revises: 016_add_store_external_id
Create Date: 2026-02-03 11:20:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '017_make_user_email_nullable'
down_revision = '016_add_store_external_id'
branch_labels = None
depends_on = None


def upgrade():
    # Изменяем колонку email на nullable
    # Сначала удаляем уникальный индекс, если он существует
    try:
        op.drop_index('ix_users_email', table_name='users')
    except Exception:
        pass  # Индекс может не существовать
    
    # Удаляем ограничение unique на email (если оно есть на уровне колонки)
    # В PostgreSQL unique constraint создается через индекс, поэтому мы уже удалили его
    
    # Изменяем колонку на nullable
    op.alter_column('users', 'email',
                    existing_type=sa.String(length=255),
                    nullable=True,
                    existing_nullable=False)
    
    # Создаем частичный уникальный индекс только для не-NULL значений
    # Это позволяет иметь несколько NULL значений, но уникальность для не-NULL
    op.create_index('ix_users_email', 'users', ['email'], 
                    unique=True, 
                    postgresql_where=sa.text('email IS NOT NULL'))


def downgrade():
    # Удаляем частичный индекс
    op.drop_index('ix_users_email', table_name='users')
    
    # Возвращаем колонку обратно на NOT NULL
    # ВНИМАНИЕ: это может вызвать ошибку, если есть NULL значения!
    op.alter_column('users', 'email',
                    existing_type=sa.String(length=255),
                    nullable=False,
                    existing_nullable=True)
    
    # Создаем обычный уникальный индекс
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
