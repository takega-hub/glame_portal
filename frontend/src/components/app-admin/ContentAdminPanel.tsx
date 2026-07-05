'use client';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import BannersPanel from '@/components/app-admin/panels/BannersPanel';
import HomeSlidesPanel from '@/components/app-admin/panels/HomeSlidesPanel';
import LookbooksPanel from '@/components/app-admin/panels/LookbooksPanel';
import PromotionsPanel from '@/components/app-admin/panels/PromotionsPanel';
import NewsPanel from '@/components/app-admin/panels/NewsPanel';
import LooksFeedPanel from '@/components/app-admin/panels/LooksFeedPanel';
import StoresPanel from '@/components/app-admin/panels/StoresPanel';
import GiftCertificatesPanel from '@/components/app-admin/panels/GiftCertificatesPanel';

export default function ContentAdminPanel({ role }: { role: string | null }) {
  const canBanners = role === 'admin' || role === 'content_manager';
  const canHome = role === 'admin' || role === 'content_manager';
  const canLookbooks = role === 'admin' || role === 'content_manager';
  const canPromotions = role === 'admin' || role === 'ai_marketer';
  const canNews = role === 'admin' || role === 'ai_marketer';
  const canLooks = role === 'admin' || role === 'content_manager' || role === 'ai_marketer';
  const canStores = role === 'admin' || role === 'content_manager';
  const canCertificates = role === 'admin' || role === 'content_manager';

  const defaultTab = canHome ? 'home' : canBanners ? 'banners' : canPromotions ? 'promotions' : canNews ? 'news' : 'lookbooks';

  return (
    <Tabs defaultValue={defaultTab}>
      <TabsList className="flex flex-wrap">
        <TabsTrigger value="home" disabled={!canHome}>
          Главная
        </TabsTrigger>
        <TabsTrigger value="banners" disabled={!canBanners}>
          Заставки/баннеры
        </TabsTrigger>
        <TabsTrigger value="lookbooks" disabled={!canLookbooks}>
          Лукбуки
        </TabsTrigger>
        <TabsTrigger value="looks" disabled={!canLooks}>
          Образы
        </TabsTrigger>
        <TabsTrigger value="stores" disabled={!canStores}>
          Магазины
        </TabsTrigger>
        <TabsTrigger value="promotions" disabled={!canPromotions}>
          Акции
        </TabsTrigger>
        <TabsTrigger value="news" disabled={!canNews}>
          Новости
        </TabsTrigger>
        <TabsTrigger value="certificates" disabled={!canCertificates}>
          Сертификаты
        </TabsTrigger>
      </TabsList>

      <TabsContent value="home">{canHome ? <HomeSlidesPanel /> : null}</TabsContent>
      <TabsContent value="banners">{canBanners ? <BannersPanel /> : null}</TabsContent>
      <TabsContent value="lookbooks">{canLookbooks ? <LookbooksPanel /> : null}</TabsContent>
      <TabsContent value="looks">{canLooks ? <LooksFeedPanel /> : null}</TabsContent>
      <TabsContent value="stores">{canStores ? <StoresPanel /> : null}</TabsContent>
      <TabsContent value="promotions">{canPromotions ? <PromotionsPanel /> : null}</TabsContent>
      <TabsContent value="news">{canNews ? <NewsPanel /> : null}</TabsContent>
      <TabsContent value="certificates">{canCertificates ? <GiftCertificatesPanel /> : null}</TabsContent>
    </Tabs>
  );
}
