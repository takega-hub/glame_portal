'use client';

import { useAuth } from '@/components/auth/AuthProvider';
import { useDesignStore } from '@/stores/designStore';
import MosaicLayout from './layouts/MosaicLayout';
import IconsLayout from './layouts/IconsLayout';
import SidebarLayout from './layouts/SidebarLayout';
import AiCentricLayout from './layouts/AiCentricLayout';
import { adminNavigation, customerNavigation } from '@/config/navigation';

export default function WelcomePage() {
  const { user } = useAuth();
  const { layout } = useDesignStore();

  const commonProps = {
    userName: user?.email || 'Пользователь',
    isCustomer: user?.is_customer && (user?.role === 'customer' || !user?.role),
  };

  const navigation = commonProps.isCustomer ? customerNavigation : adminNavigation;

  const renderLayout = () => {
    switch (layout) {
      case 'mosaic':
        return <MosaicLayout navigation={navigation} />;
      case 'icons':
        return <IconsLayout navigation={navigation} />;
      case 'sidebar':
        return <SidebarLayout navigation={navigation} />;
      case 'ai-centric':
        return <AiCentricLayout userName={commonProps.userName} navigation={navigation} />;
      default:
        return <MosaicLayout navigation={navigation} />;
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {renderLayout()}
    </div>
  );
}
