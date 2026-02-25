'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/components/auth/AuthProvider';
import { auth } from '@/lib/auth';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [cardNumber, setCardNumber] = useState('');
  const [code, setCode] = useState('');
  const [isRegister, setIsRegister] = useState(false);
  const [isCustomerLogin, setIsCustomerLogin] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [codeSent, setCodeSent] = useState(false);
  const router = useRouter();
  const { login, register, loginByCard, isAuthenticated } = useAuth();

  useEffect(() => {
    // Если уже авторизован, перенаправляем на главную
    if (isAuthenticated) {
      router.push('/');
    }
  }, [isAuthenticated, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      if (isCustomerLogin) {
        await loginByCard(cardNumber, code);
        router.push('/customer');
      } else if (isRegister) {
        await register(email, password);
        router.push('/');
      } else {
        await login(email, password);
        router.push('/');
      }
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Ошибка при входе/регистрации');
    } finally {
      setLoading(false);
    }
  };

  const handleRequestCode = async () => {
    if (!cardNumber) {
      setError('Введите номер дисконтной карты');
      return;
    }
    
    try {
      await auth.requestCode(cardNumber);
      setCodeSent(true);
      setError(null);
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message || 'Ошибка при запросе кода');
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <div>
          <h2 className="mt-6 text-center text-3xl font-extrabold text-gray-900">
            {isCustomerLogin ? 'Вход для покупателей' : isRegister ? 'Регистрация' : 'Вход в систему'}
          </h2>
        </div>

        {/* Вкладки */}
        <div className="flex border-b border-gray-200">
          <button
            type="button"
            onClick={() => {
              setIsCustomerLogin(false);
              setIsRegister(false);
              setError(null);
            }}
            className={`flex-1 py-2 px-4 text-center text-sm font-medium ${
              !isCustomerLogin && !isRegister
                ? 'border-b-2 border-pink-500 text-pink-600'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            Вход
          </button>
          <button
            type="button"
            onClick={() => {
              setIsCustomerLogin(true);
              setIsRegister(false);
              setError(null);
            }}
            className={`flex-1 py-2 px-4 text-center text-sm font-medium ${
              isCustomerLogin
                ? 'border-b-2 border-pink-500 text-pink-600'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            Для покупателей
          </button>
          <button
            type="button"
            onClick={() => {
              setIsCustomerLogin(false);
              setIsRegister(true);
              setError(null);
            }}
            className={`flex-1 py-2 px-4 text-center text-sm font-medium ${
              isRegister
                ? 'border-b-2 border-pink-500 text-pink-600'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            Регистрация
          </button>
        </div>

        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <p className="text-sm text-red-800">{error}</p>
            </div>
          )}
          
          {isCustomerLogin ? (
            <div className="space-y-4">
              <div>
                <label htmlFor="cardNumber" className="block text-sm font-medium text-gray-700 mb-1">
                  Номер дисконтной карты (телефон)
                </label>
                <input
                  id="cardNumber"
                  name="cardNumber"
                  type="tel"
                  required
                  value={cardNumber}
                  onChange={(e) => setCardNumber(e.target.value)}
                  className="appearance-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-pink-500 focus:border-pink-500 sm:text-sm"
                  placeholder="79787450654"
                />
              </div>
              <div>
                <label htmlFor="code" className="block text-sm font-medium text-gray-700 mb-1">
                  Код подтверждения
                </label>
                <div className="flex gap-2">
                  <input
                    id="code"
                    name="code"
                    type="text"
                    required
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    className="flex-1 appearance-none relative block px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-pink-500 focus:border-pink-500 sm:text-sm"
                    placeholder="Последние 4 цифры карты"
                  />
                  <button
                    type="button"
                    onClick={handleRequestCode}
                    disabled={!cardNumber || codeSent}
                    className="px-4 py-2 text-sm font-medium text-pink-600 bg-pink-50 border border-pink-300 rounded-md hover:bg-pink-100 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {codeSent ? 'Отправлено' : 'Запросить код'}
                  </button>
                </div>
                <p className="mt-1 text-xs text-gray-500">
                  Введите последние 4 цифры номера карты или код из SMS
                </p>
              </div>
            </div>
          ) : (
            <div className="rounded-md shadow-sm -space-y-px">
              <div>
                <label htmlFor="email" className="sr-only">
                  Email
                </label>
                <input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-t-md focus:outline-none focus:ring-pink-500 focus:border-pink-500 focus:z-10 sm:text-sm"
                  placeholder="Email адрес"
                />
              </div>
              <div>
                <label htmlFor="password" className="sr-only">
                  Пароль
                </label>
                <input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-b-md focus:outline-none focus:ring-pink-500 focus:border-pink-500 focus:z-10 sm:text-sm"
                  placeholder="Пароль"
                />
              </div>
            </div>
          )}

          <div>
            <button
              type="submit"
              disabled={loading}
              className="group relative w-full flex justify-center py-2 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-pink-600 hover:bg-pink-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-pink-500 disabled:opacity-50"
            >
              {loading ? 'Загрузка...' : isRegister ? 'Зарегистрироваться' : 'Войти'}
            </button>
          </div>

          {!isCustomerLogin && (
            <div className="text-center">
              <button
                type="button"
                onClick={() => setIsRegister(!isRegister)}
                className="text-sm text-pink-600 hover:text-pink-700"
              >
                {isRegister ? 'Уже есть аккаунт? Войти' : 'Нет аккаунта? Зарегистрироваться'}
              </button>
            </div>
          )}
        </form>
      </div>
    </div>
  );
}
