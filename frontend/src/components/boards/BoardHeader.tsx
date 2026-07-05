'use client';

import Link from 'next/link';

interface BoardHeaderProps {
  title: string;
  description: string;
  boardId: string;
  showBackButton?: boolean;
  actions?: React.ReactNode;
}

export default function BoardHeader({ title, description, boardId, showBackButton = true, actions }: BoardHeaderProps) {
  return (
    <div className="border-b border-gray-200 bg-white/80 backdrop-blur-sm sticky top-0 z-10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
        <div className="flex items-start justify-between">
          <div>
            {showBackButton && (
              <Link href="/ai-marketer" className="text-gray-500 hover:text-gray-700 mb-2 inline-flex items-center gap-1 text-sm">
                ← Назад к всем доскам
              </Link>
            )}
            <h1 className="text-2xl font-semibold text-gray-900 tracking-tight">{title}</h1>
            <p className="mt-1 text-gray-600 text-sm leading-relaxed max-w-2xl">{description}</p>
          </div>
          {actions && (
            <div className="flex items-center gap-3">
              {actions}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}