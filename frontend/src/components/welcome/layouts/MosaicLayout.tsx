'use client';

import Link from 'next/link';
import { Card, CardContent, Typography, Box } from '@mui/material';

interface NavigationItem {
  name: string;
  href: string;
  icon: string;
}

interface MosaicLayoutProps {
  navigation: NavigationItem[];
}

export default function MosaicLayout({ navigation }: MosaicLayoutProps) {
  const getCardSize = (index: number) => {
    if (index === 0 || index === 1) return 'large';
    if (index >= 2 && index <= 5) return 'medium';
    return 'small';
  };

  const getGridSpan = (size: string) => {
    switch (size) {
      case 'large': return 'col-span-2 row-span-2';
      case 'medium': return 'col-span-2 row-span-1';
      case 'small': return 'col-span-1 row-span-1';
      default: return 'col-span-1 row-span-1';
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 p-6">
      <div className="max-w-7xl mx-auto">
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-gray-800 mb-2">Добро пожаловать в GLAME AI</h1>
          <p className="text-lg text-gray-600">Выберите нужный раздел для начала работы</p>
        </div>
        
        <div className="grid grid-cols-4 gap-6 auto-rows-fr">
          {navigation.map((item, index) => {
            const size = getCardSize(index);
            const gridSpan = getGridSpan(size);
            
            return (
              <Link key={item.href} href={item.href} className="group">
                <Card 
                  className={`${gridSpan} h-full transform transition-all duration-300 hover:scale-105 hover:shadow-xl cursor-pointer`}
                  sx={{
                    background: 'linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%)',
                    border: '1px solid #e5e7eb',
                    '&:hover': {
                      borderColor: '#d4af37',
                      boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
                    },
                  }}
                >
                  <CardContent className="h-full flex flex-col justify-between p-6">
                    <div>
                      <div className="text-4xl mb-4 group-hover:scale-110 transition-transform duration-300">
                        {item.icon}
                      </div>
                      <Typography 
                        variant={size === 'large' ? 'h5' : size === 'medium' ? 'h6' : 'subtitle1'}
                        className="font-bold text-gray-800 mb-2 group-hover:text-gold-600 transition-colors"
                      >
                        {item.name}
                      </Typography>
                    </div>
                    
                    <Box 
                      className="w-12 h-12 rounded-full bg-gradient-to-r from-gold-400 to-gold-500 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-300"
                      sx={{ ml: 'auto' }}
                    >
                      <span className="text-white text-xl">→</span>
                    </Box>
                  </CardContent>
                </Card>
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}