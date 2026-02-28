'use client';

import { useState } from 'react';
import SystemPromptPanel from '@/components/content/SystemPromptPanel';

const AGENTS = [
  { id: 'content-agent', name: 'AI Content Agent' },
  { id: 'stylist', name: 'AI Stylist' },
  { id: 'marketer', name: 'AI Marketer' },
  { id: 'communication', name: 'Communication Agent' },
];

export default function PromptsAdminPage() {
  const [selectedAgent, setSelectedAgent] = useState(AGENTS[0].id);

  return (
    <div className="max-w-7xl mx-auto p-6">
      <h1 className="text-3xl font-bold mb-6">Управление системными промптами</h1>
      
      <div className="mb-8">
        <label className="block text-sm font-medium text-gray-700 mb-2">Выберите агента</label>
        <div className="flex gap-2 flex-wrap">
          {AGENTS.map((agent) => (
            <button
              key={agent.id}
              onClick={() => setSelectedAgent(agent.id)}
              className={`px-4 py-2 rounded-lg transition-colors ${
                selectedAgent === agent.id
                  ? 'bg-gold-500 text-white'
                  : 'bg-white border border-gray-300 text-gray-700 hover:bg-gray-50'
              }`}
            >
              {agent.name}
            </button>
          ))}
        </div>
      </div>

      <div key={selectedAgent}>
        <SystemPromptPanel agentType={selectedAgent} />
      </div>
    </div>
  );
}
