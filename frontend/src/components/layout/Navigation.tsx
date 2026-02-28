'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/components/auth/AuthProvider';
import DesignSwitcher from '@/components/welcome/DesignSwitcher';
import { adminNavigation, customerNavigation } from '@/config/navigation';

export default function Navigation() {
  const pathname = usePathname();
  const { user } = useAuth();
  
  // Определяем навигацию в зависимости от роли
  // Если пользователь - покупатель (is_customer=true и role=customer или null), показываем навигацию покупателя
  // Иначе показываем админскую навигацию
  const isCustomer = user?.is_customer && (user?.role === 'customer' || !user?.role);
  const navigation = isCustomer ? customerNavigation : adminNavigation;

  return (
    <nav className="bg-white shadow-concrete border-b border-concrete-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex">
            <div className="flex-shrink-0 flex items-center">
              <Link href="/" className="text-2xl font-bold text-gold-500 dark:text-gold-400">
                GLAME AI
              </Link>
            </div>
            <div className="hidden sm:ml-6 sm:flex sm:space-x-8">
              {navigation.map((item) => {
                const isActive = pathname === item.href;
                return (
                  <Link
                    key={item.name}
                    href={item.href}
                    className={`inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium transition-colors ${
                      isActive
                        ? 'border-gold-500 text-concrete-900 dark:text-gold-500'
                        : 'border-transparent text-concrete-500 dark:text-gray-300 hover:border-concrete-300 hover:text-concrete-700 dark:hover:text-gray-200'
                    }`}
                  >
                    <span className="mr-2">{item.icon}</span>
                    {item.name}
                  </Link>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Mobile menu */}
      <div className="sm:hidden">
        <div className="pt-2 pb-3 space-y-1">
          {navigation.map((item) => {
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.name}
                href={item.href}
                className={`block pl-3 pr-4 py-2 border-l-4 text-base font-medium transition-colors ${
                  isActive
                    ? 'bg-gold-50 border-gold-500 text-gold-700 dark:text-gold-300'
                    : 'border-transparent text-concrete-500 dark:text-gray-300 hover:bg-concrete-50 hover:border-concrete-300 hover:text-concrete-700 dark:hover:text-gray-200'
                }`}
              >
                <span className="mr-2">{item.icon}</span>
                {item.name}
              </Link>
            );
          })}
        </div>
        
        {/* Design Switcher */}
        <div className="flex items-center">
          <DesignSwitcher />
        </div>
      </div>
    </nav>
  );
}
