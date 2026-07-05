import JewelryPhotoProcessingPanel from '@/components/products/JewelryPhotoProcessingPanel';

export default function Page() {
  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_right,_rgba(245,158,11,0.10),_transparent_34%),linear-gradient(180deg,#f8fafc_0%,#f3f4f6_100%)] px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl">
        <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div>
            <a href="/profile/sellers/dashboard" className="text-sm font-medium text-pink-600 hover:text-pink-700">
              ← Назад в План/Факт
            </a>
            <h1 className="mt-3 text-3xl font-bold tracking-tight text-gray-950">Фото украшений</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-600">
              Рабочее место продавца для подготовки каталожных фото: загрузка исходников, ретушь Hermes GPT Image 2, контроль промпта, проверка крупного превью и добавление результата в карточку товара.
            </p>
          </div>
          <div className="rounded-2xl border border-gold-200 bg-white/80 px-4 py-3 text-sm text-gray-700 shadow-sm backdrop-blur">
            <p className="font-semibold text-gray-950">Стандарт GLAME</p>
            <p className="mt-1 text-xs text-gray-500">3:4 · холодно-белый фон · премиальный свет · без CGI</p>
          </div>
        </div>
        <JewelryPhotoProcessingPanel compact />
      </div>
    </main>
  );
}
