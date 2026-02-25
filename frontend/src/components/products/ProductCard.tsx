import { Product } from '@/types';
import Link from 'next/link';

interface ProductCardProps {
  product: Product;
}

export default function ProductCard({ product }: ProductCardProps) {
  const formatPrice = (price: number) => {
    return new Intl.NumberFormat('ru-RU', {
      style: 'currency',
      currency: 'RUB',
      minimumFractionDigits: 0,
    }).format(price / 100);
  };

  return (
    <div className="bg-white text-gray-900 border border-gray-200 rounded-lg p-4 hover:shadow-lg transition">
      <Link href={`/products/${product.id}`} className="block">
        {product.images && product.images.length > 0 ? (
          <img
            src={product.images[0]}
            alt={product.name}
            className="w-full h-48 object-cover rounded-lg mb-2"
          />
        ) : (
          <div className="w-full h-48 bg-gray-100 rounded-lg mb-2 flex items-center justify-center">
            <span className="text-gray-500">Нет изображения</span>
          </div>
        )}
        <h3 className="font-semibold text-base sm:text-lg mb-1 text-gray-900 line-clamp-2">
          {product.name}
        </h3>
      </Link>

      {product.brand && <p className="text-sm text-gray-700 mb-1">{product.brand}</p>}
      {(product.article || product.external_code) && (
        <p className="text-xs text-gray-500 mb-1">
          Артикул: <span className="font-medium text-gray-700">{product.article || product.external_code}</span>
        </p>
      )}
      {product.stock !== undefined && product.stock !== null && (
        <p className="text-xs mb-1">
          {product.stock > 0 ? (
            <span className="text-green-600 font-medium">В наличии: {Math.floor(product.stock)} шт.</span>
          ) : (
            <span className="text-red-600 font-medium">Нет в наличии</span>
          )}
        </p>
      )}
      <p className="text-lg font-bold text-gold-600 mb-2">{formatPrice(product.price)}</p>
      {product.tags && product.tags.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {product.tags.map((tag, index) => (
            <span
              key={index}
              className="px-2 py-1 bg-gray-50 border border-gray-200 text-gray-800 text-xs rounded"
            >
              {tag}
            </span>
          ))}
        </div>
      )}
      <button className="mt-3 w-full px-4 py-2 bg-gold-500 text-white rounded-lg hover:bg-gold-600 transition">
        Добавить в корзину
      </button>
    </div>
  );
}
