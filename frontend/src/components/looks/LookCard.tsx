'use client';

import { useState } from 'react';
import { Look, LookWithProducts } from '@/types';
import { api } from '@/lib/api';
import Link from 'next/link';

interface LookCardProps {
  look: LookWithProducts | Look;
  showTryOn?: boolean;
  onTryOnClick?: (lookId: string) => void;
}

export default function LookCard({ look, showTryOn = true, onTryOnClick }: LookCardProps) {
  const products = (look as LookWithProducts).products;
  const [approving, setApproving] = useState(false);
  const [approved, setApproved] = useState(look.approval_status === 'approved');
  const [currentImageIndex, setCurrentImageIndex] = useState(look.current_image_index ?? 0);

  const handleApprove = async () => {
    if (approved) return;
    
    setApproving(true);
    try {
      await api.approveLook(look.id);
      setApproved(true);
    } catch (error) {
      console.error('Ошибка при одобрении образа:', error);
    } finally {
      setApproving(false);
    }
  };

  // Получаем массив изображений
  const getImageUrls = (): string[] => {
    if (look.image_urls && look.image_urls.length > 0) {
      return look.image_urls.map((img: any) => {
        if (typeof img === 'string') return img;
        return img.url || img;
      });
    }
    if (look.image_url) return [look.image_url];
    return [];
  };

  const imageUrls = getImageUrls();
  const currentImage = imageUrls[currentImageIndex] || look.image_url;

  const handlePrevImage = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (imageUrls.length > 1) {
      setCurrentImageIndex((prev) => (prev > 0 ? prev - 1 : imageUrls.length - 1));
    }
  };

  const handleNextImage = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (imageUrls.length > 1) {
      setCurrentImageIndex((prev) => (prev < imageUrls.length - 1 ? prev + 1 : 0));
    }
  };

  return (
    <div className="border border-concrete-200 rounded-lg p-4 hover:shadow-concrete transition">
      {/* Карусель изображений образа */}
      <div className="relative mb-2">
        {currentImage ? (
          <>
            <img
              src={currentImage}
              alt={look.name}
              className="w-full h-64 object-cover rounded-lg"
            />
            {imageUrls.length > 1 && (
              <>
                <button
                  onClick={handlePrevImage}
                  className="absolute left-2 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/70 text-white rounded-full p-2 transition"
                  aria-label="Предыдущее изображение"
                >
                  ←
                </button>
                <button
                  onClick={handleNextImage}
                  className="absolute right-2 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/70 text-white rounded-full p-2 transition"
                  aria-label="Следующее изображение"
                >
                  →
                </button>
                <div className="absolute bottom-2 left-1/2 -translate-x-1/2 flex gap-1">
                  {imageUrls.map((_, idx) => (
                    <button
                      key={idx}
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        setCurrentImageIndex(idx);
                      }}
                      className={`w-2 h-2 rounded-full transition ${
                        idx === currentImageIndex ? 'bg-white' : 'bg-white/50'
                      }`}
                      aria-label={`Изображение ${idx + 1}`}
                    />
                  ))}
                </div>
                <div className="absolute top-2 right-2 bg-black/50 text-white text-xs px-2 py-1 rounded">
                  {currentImageIndex + 1} / {imageUrls.length}
                </div>
              </>
            )}
          </>
        ) : look.try_on_image_url ? (
          <div className="relative">
            <img
              src={look.try_on_image_url}
              alt={look.name}
              className="w-full h-64 object-cover rounded-lg"
            />
            <span className="absolute top-2 right-2 px-2 py-1 bg-green-500 text-white text-xs rounded">
              Примерка
            </span>
          </div>
        ) : (
          <div className="w-full h-64 bg-concrete-200 rounded-lg flex items-center justify-center">
            <span className="text-concrete-400">Нет изображения</span>
          </div>
        )}
      </div>

      {/* Статусы */}
      <div className="flex items-center gap-2 mb-2">
        {look.status === 'auto_generated' && (
          <span className="px-2 py-1 bg-purple-100 text-purple-700 text-xs rounded">
            AI
          </span>
        )}
        {look.approval_status === 'approved' && (
          <span className="px-2 py-1 bg-green-100 text-green-700 text-xs rounded">
            Одобрен
          </span>
        )}
        {look.approval_status === 'pending' && (
          <span className="px-2 py-1 bg-yellow-100 text-yellow-700 text-xs rounded">
            На рассмотрении
          </span>
        )}
      </div>

      <h3 className="font-semibold text-lg text-concrete-900 mb-1">{look.name}</h3>
      
      {look.style && (
        <span className="inline-block px-2 py-1 bg-gold-100 text-gold-800 text-xs rounded mb-2 font-medium">
          {look.style}
        </span>
      )}
      {look.mood && (
        <span className="inline-block px-2 py-1 bg-metallic-100 text-metallic-800 text-xs rounded mb-2 ml-2 font-medium">
          {look.mood}
        </span>
      )}
      
      {look.description && (
        <p className="text-sm text-concrete-800 mb-2">{look.description}</p>
      )}
      
      {products && products.length > 0 && (
        <div className="mt-2">
          <p className="text-xs text-concrete-700 font-medium mb-1">Товары в образе:</p>
          <div className="flex flex-wrap gap-1">
            {products.slice(0, 3).map((product) => (
              <Link
                key={product.id}
                href={`/products/${product.id}`}
                className="px-2 py-1 bg-concrete-100 text-concrete-900 text-xs rounded hover:bg-concrete-200 transition font-medium"
              >
                {product.name}
              </Link>
            ))}
            {products.length > 3 && (
              <span className="px-2 py-1 bg-concrete-100 text-concrete-900 text-xs rounded font-medium">
                +{products.length - 3}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Действия */}
      <div className="mt-3 space-y-2">
        {showTryOn && (
          <button
            onClick={() => onTryOnClick?.(look.id)}
            className="w-full px-4 py-2 bg-gold-500 text-white rounded-lg hover:bg-gold-600 transition shadow-gold"
          >
            Примерка на фото
          </button>
        )}
        
        {look.status === 'auto_generated' && !approved && (
          <button
            onClick={handleApprove}
            disabled={approving}
            className="w-full px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 transition disabled:opacity-50"
          >
            {approving ? 'Одобрение...' : 'Одобрить образ'}
          </button>
        )}
        
        <Link
          href={`/looks/${look.id}`}
          className="block w-full px-4 py-2 bg-concrete-100 text-concrete-700 rounded-lg hover:bg-concrete-200 transition text-center"
        >
          Подробнее
        </Link>
      </div>
    </div>
  );
}
