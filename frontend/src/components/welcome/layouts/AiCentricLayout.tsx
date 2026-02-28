import { Box, Typography, Paper, Fab, Zoom, Container } from '@mui/material';
import { SmartToy, Analytics, Settings } from '@mui/icons-material';
import Link from 'next/link';

interface NavigationItem {
  name: string;
  href: string;
  icon: string;
}

interface AiCentricLayoutProps {
  userName: string;
  navigation: NavigationItem[];
}

export default function AiCentricLayout({ userName, navigation }: AiCentricLayoutProps) {
  // Размещаем иконки по кругу вокруг центрального AI
  const getCircularPosition = (index: number, total: number) => {
    const angle = (index * 360) / total;
    const radius = 200;
    const x = Math.cos((angle * Math.PI) / 180) * radius;
    const y = Math.sin((angle * Math.PI) / 180) * radius;
    return { x, y };
  };

  return (
    <Container maxWidth="lg" sx={{ py: 4, height: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <Box sx={{ textAlign: 'center', mb: 4 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          Добро пожаловать, {userName}!
        </Typography>
        <Typography variant="subtitle1" color="text.secondary">
          Ваш персональный AI-ассистент готов помочь
        </Typography>
      </Box>

      {/* AI-Centric Layout */}
      <Box 
        sx={{ 
          flexGrow: 1, 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'center',
          position: 'relative',
          minHeight: 500
        }}
      >
        {/* Central AI Assistant */}
        <Paper
          elevation={8}
          sx={{
            position: 'absolute',
            width: 200,
            height: 200,
            borderRadius: '50%',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            color: 'white',
            zIndex: 10,
          }}
        >
          <SmartToy sx={{ fontSize: 60, mb: 1 }} />
          <Typography variant="h6" component="div" sx={{ fontWeight: 'bold' }}>
            GLAME AI
          </Typography>
          <Typography variant="caption">
            Ваш ассистент
          </Typography>
        </Paper>

        {/* Navigation Items in Circle */}
        {navigation.map((item, index) => {
          const position = getCircularPosition(index, navigation.length);
          return (
            <Zoom in={true} style={{ transitionDelay: `${index * 100}ms` }} key={item.href}>
              <Link href={item.href} style={{ textDecoration: 'none' }}>
                <Fab
                  color="primary"
                  size="large"
                  sx={{
                    position: 'absolute',
                    left: `calc(50% + ${position.x}px)`,
                    top: `calc(50% + ${position.y}px)`,
                    transform: 'translate(-50%, -50%)',
                    fontSize: '2rem',
                    '&:hover': {
                      transform: 'translate(-50%, -50%) scale(1.1)',
                    },
                  }}
                >
                  {item.icon}
                </Fab>
              </Link>
            </Zoom>
          );
        })}
      </Box>

      {/* Quick Actions at Bottom */}
      <Box sx={{ mt: 4, display: 'flex', justifyContent: 'center', gap: 2, flexWrap: 'wrap' }}>
        <Paper elevation={2} sx={{ p: 2, borderRadius: 3, cursor: 'pointer', '&:hover': { backgroundColor: 'action.hover' } }}>
          <Link href="/" style={{ textDecoration: 'none', color: 'inherit' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <SmartToy />
              <Typography variant="body2">Начать чат</Typography>
            </Box>
          </Link>
        </Paper>
        
        <Paper elevation={2} sx={{ p: 2, borderRadius: 3, cursor: 'pointer', '&:hover': { backgroundColor: 'action.hover' } }}>
          <Link href="/analytics" style={{ textDecoration: 'none', color: 'inherit' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Analytics />
              <Typography variant="body2">Аналитика</Typography>
            </Box>
          </Link>
        </Paper>
        
        <Paper elevation={2} sx={{ p: 2, borderRadius: 3, cursor: 'pointer', '&:hover': { backgroundColor: 'action.hover' } }}>
          <Link href="/settings" style={{ textDecoration: 'none', color: 'inherit' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Settings />
              <Typography variant="body2">Настройки</Typography>
            </Box>
          </Link>
        </Paper>
      </Box>
    </Container>
  );
}
