'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Card, CardContent, Typography, Box, Divider } from '@mui/material';

interface NavigationItem {
  name: string;
  href: string;
  icon: string;
}

interface SidebarLayoutProps {
  navigation: NavigationItem[];
}

export default function SidebarLayout({ navigation }: SidebarLayoutProps) {
  const pathname = usePathname();

  const groupedNavigation = {
    'AI Инструменты': navigation.filter(item => 
      ['AI Stylist', 'AI Content Agent', 'AI Маркетолог', 'Генератор контента'].includes(item.name)
    ),
    'Управление': navigation.filter(item => 
      ['Каталог товаров', 'Образы', 'Покупатели', 'База знаний'].includes(item.name)
    ),
    'Аналитика': navigation.filter(item => 
      ['Аналитика'].includes(item.name)
    ),
    'Система': navigation.filter(item => 
      ['Настройки'].includes(item.name)
    ),
  };

  return (
    <div className="min-h-screen bg-gray-50 flex">
      {/* Sidebar */}
      <div className="w-80 bg-white shadow-lg">
        <div className="p-6 border-b border-gray-200">
          <h2 className="text-2xl font-bold text-gray-800">GLAME AI</h2>
          <p className="text-sm text-gray-600 mt-1">Панель управления</p>
        </div>
        
        <nav className="p-4">
          {Object.entries(groupedNavigation).map(([group, items]) => (
            items.length > 0 && (
              <div key={group} className="mb-6">
                <Typography 
                  variant="subtitle2" 
                  className="text-gray-500 font-semibold mb-3 px-3"
                  sx={{ fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}
                >
                  {group}
                </Typography>
                
                {items.map((item) => {
                  const isActive = pathname === item.href;
                  
                  return (
                    <Link key={item.href} href={item.href} className="block">
                      <div
                        className={`
                          flex items-center p-3 rounded-lg mb-2 transition-all duration-200
                          ${isActive 
                            ? 'bg-gold-100 text-gold-700 border border-gold-200' 
                            : 'text-gray-700 hover:bg-gray-100'
                          }
                        `}
                      >
                        <span className="text-xl mr-3">{item.icon}</span>
                        <span className="font-medium">{item.name}</span>
                        {isActive && (
                          <div className="ml-auto w-2 h-2 bg-gold-500 rounded-full"></div>
                        )}
                      </div>
                    </Link>
                  );
                })}
                
                <Divider className="my-4" />
              </div>
            )
          ))}
        </nav>
      </div>
      
      {/* Main Content */}
      <div className="flex-1 p-8">
        <div className="max-w-4xl mx-auto">
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-gray-800 mb-2">Добро пожаловать</h1>
            <p className="text-lg text-gray-600">Используйте боковую панель для навигации по разделам</p>
          </div>
          
          {/* Quick Stats */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <Card className="bg-gradient-to-r from-blue-50 to-blue-100 border border-blue-200">
              <CardContent className="p-6">
                <Typography variant="h6" className="text-blue-800 mb-2">
                  Доступных разделов
                </Typography>
                <Typography variant="h3" className="font-bold text-blue-900">
                  {navigation.length}
                </Typography>
              </CardContent>
            </Card>
            
            <Card className="bg-gradient-to-r from-green-50 to-green-100 border border-green-200">
              <CardContent className="p-6">
                <Typography variant="h6" className="text-green-800 mb-2">
                  Активные инструменты
                </Typography>
                <Typography variant="h3" className="font-bold text-green-900">
                  3
                </Typography>
              </CardContent>
            </Card>
            
            <Card className="bg-gradient-to-r from-gold-50 to-gold-100 border border-gold-200">
              <CardContent className="p-6">
                <Typography variant="h6" className="text-gold-800 mb-2">
                  Последнее обновление
                </Typography>
                <Typography variant="h6" className="font-bold text-gold-900">
                  Сегодня
                </Typography>
              </CardContent>
            </Card>
          </div>
          
          {/* Recent Activity */}
          <Card className="shadow-sm">
            <CardContent className="p-6">
              <Typography variant="h6" className="font-bold text-gray-800 mb-4">
                Быстрые действия
              </Typography>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {navigation.slice(0, 4).map((item) => (
                  <Link key={item.href} href={item.href}>
                    <Box className="p-4 rounded-lg border border-gray-200 hover:border-gold-300 hover:bg-gold-50 transition-all duration-200 cursor-pointer">
                      <div className="flex items-center">
                        <span className="text-2xl mr-3">{item.icon}</span>
                        <div>
                          <Typography variant="subtitle1" className="font-semibold text-gray-800">
                            {item.name}
                          </Typography>
                          <Typography variant="body2" className="text-gray-600">
                            Перейти к разделу
                          </Typography>
                        </div>
                      </div>
                    </Box>
                  </Link>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}