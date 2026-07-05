CREATE TABLE IF NOT EXISTS director_conversation_contexts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    session_id VARCHAR(100) NOT NULL,
    current_topic VARCHAR(200),
    current_phase VARCHAR(50),
    context_data JSONB DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ DEFAULT now(),
    last_activity_at TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ,
    status VARCHAR(50) NOT NULL DEFAULT 'active'
);

CREATE INDEX IF NOT EXISTS idx_director_conv_user ON director_conversation_contexts(user_id);
CREATE INDEX IF NOT EXISTS idx_director_conv_session ON director_conversation_contexts(session_id);

CREATE TABLE IF NOT EXISTS director_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    title VARCHAR(500) NOT NULL,
    description TEXT,
    task_type VARCHAR(50) NOT NULL DEFAULT 'assignment',
    target_agent VARCHAR(100),
    priority VARCHAR(20) NOT NULL DEFAULT 'P2',
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    deadline_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,
    assigned_to VARCHAR(255),
    execution_notes TEXT,
    result_summary TEXT,
    detailed_result JSONB,
    vector_id VARCHAR(100),
    extra_data JSONB DEFAULT '{}'::jsonb,
    related_message_id UUID
);

CREATE INDEX IF NOT EXISTS idx_director_tasks_user ON director_tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_director_tasks_status ON director_tasks(status);
CREATE INDEX IF NOT EXISTS idx_director_tasks_priority ON director_tasks(priority);
CREATE INDEX IF NOT EXISTS idx_director_tasks_task_type ON director_tasks(task_type);
CREATE INDEX IF NOT EXISTS idx_director_tasks_vector ON director_tasks(vector_id);

CREATE TABLE IF NOT EXISTS director_chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    message TEXT NOT NULL,
    message_type VARCHAR(50) NOT NULL DEFAULT 'text',
    message_direction VARCHAR(20) NOT NULL,
    category VARCHAR(100),
    priority VARCHAR(20),
    session_id VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ,
    vector_id VARCHAR(100),
    extra_data JSONB DEFAULT '{}'::jsonb,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    is_important BOOLEAN NOT NULL DEFAULT false,
    parent_message_id UUID REFERENCES director_chat_messages(id),
    related_task_id UUID REFERENCES director_tasks(id)
);

CREATE INDEX IF NOT EXISTS idx_director_msgs_user ON director_chat_messages(user_id);
CREATE INDEX IF NOT EXISTS idx_director_msgs_session ON director_chat_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_director_msgs_direction ON director_chat_messages(message_direction);
CREATE INDEX IF NOT EXISTS idx_director_msgs_type ON director_chat_messages(message_type);
CREATE INDEX IF NOT EXISTS idx_director_msgs_category ON director_chat_messages(category);
CREATE INDEX IF NOT EXISTS idx_director_msgs_priority ON director_chat_messages(priority);
CREATE INDEX IF NOT EXISTS idx_director_msgs_important ON director_chat_messages(is_important);
CREATE INDEX IF NOT EXISTS idx_director_msgs_status ON director_chat_messages(status);
CREATE INDEX IF NOT EXISTS idx_director_msgs_vector ON director_chat_messages(vector_id);
CREATE INDEX IF NOT EXISTS idx_director_msgs_created ON director_chat_messages(created_at);

CREATE TABLE IF NOT EXISTS director_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    memory_type VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    content_type VARCHAR(100),
    vector_id VARCHAR(100),
    extra_data JSONB DEFAULT '{}'::jsonb,
    source_message_id UUID REFERENCES director_chat_messages(id),
    source_task_id UUID REFERENCES director_tasks(id),
    importance INTEGER NOT NULL DEFAULT 1,
    relevance_score FLOAT,
    created_at TIMESTAMPTZ DEFAULT now(),
    last_accessed_at TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ,
    status VARCHAR(50) NOT NULL DEFAULT 'active'
);

CREATE INDEX IF NOT EXISTS idx_director_memory_user ON director_memory(user_id);
CREATE INDEX IF NOT EXISTS idx_director_memory_type ON director_memory(memory_type);
CREATE INDEX IF NOT EXISTS idx_director_memory_importance ON director_memory(importance);
CREATE INDEX IF NOT EXISTS idx_director_memory_relevance ON director_memory(relevance_score);
CREATE INDEX IF NOT EXISTS idx_director_memory_status ON director_memory(status);
CREATE INDEX IF NOT EXISTS idx_director_memory_vector ON director_memory(vector_id);
CREATE INDEX IF NOT EXISTS idx_director_memory_created ON director_memory(created_at);

CREATE TABLE IF NOT EXISTS director_knowledge (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    title VARCHAR(500) NOT NULL,
    category VARCHAR(100) NOT NULL,
    content TEXT NOT NULL,
    content_type VARCHAR(100),
    vector_id VARCHAR(100),
    extra_data JSONB DEFAULT '{}'::jsonb,
    source VARCHAR(255),
    source_message_id UUID REFERENCES director_chat_messages(id),
    source_task_id UUID REFERENCES director_tasks(id),
    importance INTEGER NOT NULL DEFAULT 1,
    usage_count INTEGER NOT NULL DEFAULT 0,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ,
    status VARCHAR(50) NOT NULL DEFAULT 'active'
);

CREATE INDEX IF NOT EXISTS idx_director_knowledge_user ON director_knowledge(user_id);
CREATE INDEX IF NOT EXISTS idx_director_knowledge_category ON director_knowledge(category);
CREATE INDEX IF NOT EXISTS idx_director_knowledge_importance ON director_knowledge(importance);
CREATE INDEX IF NOT EXISTS idx_director_knowledge_usage ON director_knowledge(usage_count);
CREATE INDEX IF NOT EXISTS idx_director_knowledge_status ON director_knowledge(status);
CREATE INDEX IF NOT EXISTS idx_director_knowledge_vector ON director_knowledge(vector_id);
CREATE INDEX IF NOT EXISTS idx_director_knowledge_created ON director_knowledge(created_at);