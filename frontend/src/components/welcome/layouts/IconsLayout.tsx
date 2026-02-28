'use client';

import Link from 'next/link';
import { Card, CardContent, Typography } from '@mui/material';

interface NavigationItem {
  name: string;
  href: string;
  icon: string;
}

interface IconsLayoutProps {
  navigation: NavigationItem[];
}

export default function IconsLayout({ navigation }: IconsLayoutProps) {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 p-6">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold text-gray-800 mb-3">GLAME AI Портал</h1>
          <p className="text-lg text-gray-600">Выберите нужный раздел для работы</p>
        </div>
        
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-6">
          {navigation.map((item) => (
            <Link key={item.href} href={item.href} className="group">
              <Card 
                className="h-32 transform transition-all duration-300 hover:scale-105 hover:shadow-lg cursor-pointer"
                sx={{
                  background: 'linear-gradient(135deg, #ffffff 0%, #f8fafc 100%)',
                  border: '1px solid #e2e8f0',
                  borderRadius: '16px',
                  '&:hover': {
                    borderColor: '#d4af37',
                    boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
                  },
                }}
              >
                <CardContent className="h-full flex flex-col items-center justify-center p-4">
                  <div className="text-5xl mb-3 group-hover:scale-110 transition-transform duration-300">
                    {item.icon}
                  </div>
                  <Typography 
                    variant="subtitle1" 
                    className="font-semibold text-gray-700 text-center group-hover:text-gold-600 transition-colors text-sm"
                    sx={{ 
                      lineHeight: 1.2,
                      fontSize: '0.875rem'
                    }}
                  >
                    {item.name}
                  </Typography>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
        
        <div className="mt-12 text-center">
          <div className="inline-flex items-center space-x-2 bg-white px-4 py-2 rounded-full shadow-sm border">
            <span className="text-sm text-gray-500">Всего разделов:</span>
            <span className="text-sm font-semibold text-gold-600">{navigation.length}</span>
          </div>
        </div>
      </div>
    </div>
  );
}