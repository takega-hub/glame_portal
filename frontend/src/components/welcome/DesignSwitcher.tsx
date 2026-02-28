'use client';

import { useState } from 'react';
import { useDesignStore, LayoutType } from '@/stores/designStore';
import { 
  Button, 
  Menu, 
  MenuItem, 
  ListItemIcon, 
  ListItemText,
  Tooltip 
} from '@mui/material';
import { 
  GridOn as GridIcon,
  Apps as AppsIcon,
  ViewSidebar as SidebarIcon,
  Psychology as AIIcon,
  Settings as SettingsIcon
} from '@mui/icons-material';

const layoutOptions = [
  { 
    id: 'mosaic' as LayoutType, 
    label: 'Мозаичный', 
    icon: <GridIcon />,
    description: 'Современная сетка с карточками'
  },
  { 
    id: 'icons' as LayoutType, 
    label: 'Иконки', 
    icon: <AppsIcon />,
    description: 'Классическая сетка иконок'
  },
  { 
    id: 'sidebar' as LayoutType, 
    label: 'Сайдбар', 
    icon: <SidebarIcon />,
    description: 'Боковая навигация'
  },
  { 
    id: 'ai-centric' as LayoutType, 
    label: 'AI-центр', 
    icon: <AIIcon />,
    description: 'Интерфейс вокруг AI'
  },
];

export default function DesignSwitcher() {
  const { layout, setLayout } = useDesignStore();
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const open = Boolean(anchorEl);

  const handleClick = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };

  const handleClose = () => {
    setAnchorEl(null);
  };

  const handleLayoutChange = (newLayout: LayoutType) => {
    setLayout(newLayout);
    handleClose();
  };

  const currentLayout = layoutOptions.find(option => option.id === layout);

  return (
    <>
      <Tooltip title="Выбрать дизайн">
        <Button
          onClick={handleClick}
          variant="outlined"
          size="small"
          startIcon={currentLayout?.icon || <SettingsIcon />}
          sx={{ 
            borderColor: 'gold.500',
            color: 'gold.700',
            '&:hover': { borderColor: 'gold.600' }
          }}
        >
          {currentLayout?.label}
        </Button>
      </Tooltip>
      
      <Menu
        anchorEl={anchorEl}
        open={open}
        onClose={handleClose}
        anchorOrigin={{
          vertical: 'bottom',
          horizontal: 'right',
        }}
        transformOrigin={{
          vertical: 'top',
          horizontal: 'right',
        }}
        PaperProps={{
          sx: { 
            minWidth: 200,
            border: '1px solid',
            borderColor: 'gold.200',
            boxShadow: '0 4px 12px rgba(0,0,0,0.1)'
          }
        }}
      >
        {layoutOptions.map((option) => (
          <MenuItem
            key={option.id}
            onClick={() => handleLayoutChange(option.id)}
            selected={layout === option.id}
            sx={{
              '&.Mui-selected': {
                backgroundColor: 'gold.50',
                '&:hover': {
                  backgroundColor: 'gold.100',
                },
              },
            }}
          >
            <ListItemIcon sx={{ color: layout === option.id ? 'gold.600' : 'inherit' }}>
              {option.icon}
            </ListItemIcon>
            <ListItemText 
              primary={option.label}
              secondary={option.description}
              primaryTypographyProps={{
                sx: { color: layout === option.id ? 'gold.700' : 'inherit' }
              }}
            />
          </MenuItem>
        ))}
      </Menu>
    </>
  );
}