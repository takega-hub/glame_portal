import type { Metadata } from 'next';
import Link from 'next/link';
import {
  ArrowRight,
  BadgeCheck,
  Coins,
  ExternalLink,
  Gift,
  HandCoins,
  Landmark,
  LockKeyhole,
  MapPin,
  ReceiptText,
  ShieldCheck,
  Smartphone,
  Store,
  UserPlus,
  Wallet,
} from 'lucide-react';

export const metadata: Metadata = {
  title: 'GLM Coin | CryptoGLAME',
  description:
    'GLM Coin - клубная utility-монета GLAME в сети TON для партнерской программы, GLM Store и обмена с бонусными баллами.',
};

const tokenStats = [
  ['Сеть', 'TON mainnet'],
  ['Стандарт', 'Jetton / TEP-74'],
  ['Выпуск', '10 000 000 GLM'],
  ['Связь', 'Баллы лояльности 1C'],
];

const utilityCards = [
  {
    icon: HandCoins,
    title: 'Партнерские начисления',
    text: 'Партнер может получать GLM за покупки приглашенных клиентов после подтверждения заказа и правил hold.',
  },
  {
    icon: Store,
    title: 'GLM Store',
    text: 'Монеты используются для покупки специальных брендированных товаров, доступов и сервисов внутри онлайн-витрины.',
  },
  {
    icon: Wallet,
    title: 'TON-кошелек',
    text: 'Фактический GLM-баланс хранится в подключенном TON-кошельке пользователя, а платформа ведет заявки и аудит.',
  },
  {
    icon: ReceiptText,
    title: 'Bridge с баллами',
    text: 'GLM связан с бонусной системой GLAME: баллы за реальные покупки можно переводить в GLM, а GLM - обратно в баллы.',
  },
];

const offlineStores = [
  {
    title: 'GLAME Ялта',
    subtitle: 'пространство у моря',
    address: 'Набережная им. Ленина, 18, Приморский пляж',
    text: 'Украшения подбирают как часть образа - спокойно, точно и без давления.',
    image: '/static/app_admin_media/store/glame_space_yalta_hero_photo.png',
  },
  {
    title: 'GLAME Симферополь',
    subtitle: 'пространство городского стиля и ритма',
    address: 'ул. Севастопольская, 62, 1 этаж',
    text: 'Ритм города, архитектура и украшения, которые собирают образ.',
    image: '/static/app_admin_media/store/glame_space_simferopol_hero_photo.png',
  },
];

const tokenomics = [
  ['Bank / treasury', 'Основной запас GLM хранится на банковском кошельке GLAME и распределяется по правилам программы.'],
  ['Hot-wallet', 'Операционный кошелек пополняется лимитированными партиями для быстрых выплат партнерам.'],
  ['Loyalty backing', 'GLM имеет utility-связь с реальными баллами лояльности, которые начисляются за покупки украшений в GLAME.'],
  ['Utility demand', 'Спрос формируется GLM Store, мобильным приложением, партнерскими механиками, онлайн-сервисами и bridge-сценариями.'],
  ['No promise', 'GLAME не обещает рост цены, buyback, листинг на бирже или фиксированный публичный курс.'],
];

const roadmap = [
  ['01', 'Mainnet launch', 'Выпуск GLM Jetton, публичная metadata, hot-wallet и прозрачная treasury-модель.'],
  ['02', 'Partner utility', 'Автоматические выплаты партнерам, GLM Store, история операций и Telegram-уведомления.'],
  ['03', 'Trust layer', 'Верификация токена в wallet asset lists, публичный audit journal и расширение правил bridge.'],
  ['04', 'Ecosystem', 'Новые товары, закрытые дропы, онлайн-сервисы и дополнительные партнерские сценарии.'],
];

export default function GlmLandingPage() {
  return (
    <main className="min-h-screen bg-[#08090a] text-white">
      <section className="relative overflow-hidden border-b border-white/10">
        <div
          className="absolute inset-0 bg-[length:520px_520px] bg-[position:85%_45%] bg-no-repeat opacity-10"
          style={{
            backgroundImage: "url('/static/glm_policy/glm-token-icon-v3.png')",
          }}
        />
        <div className="relative mx-auto grid min-h-[92vh] max-w-7xl gap-10 px-5 py-8 sm:px-8 lg:grid-cols-[1.05fr_.95fr] lg:items-center lg:py-10">
          <div>
            <div className="mb-10 flex items-center justify-between gap-4 text-sm">
              <Link href="https://glamejewelry.ru" className="font-semibold tracking-[0.35em] text-white/85">
                GLAME
              </Link>
              <Link
                href="https://partner.glamejewelry.ru/referral"
                className="inline-flex items-center gap-2 border border-white/20 px-4 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-white/80 transition hover:border-white/45 hover:text-white"
              >
                Партнерский сайт <ExternalLink className="h-3.5 w-3.5" />
              </Link>
            </div>
            <p className="mb-5 text-xs font-semibold uppercase tracking-[0.4em] text-[#c9b56a]">CryptoGLAME utility token</p>
            <h1 className="max-w-4xl text-5xl font-semibold leading-[0.95] tracking-normal text-white sm:text-6xl lg:text-7xl">
              GLM Coin
            </h1>
            <p className="mt-7 max-w-2xl text-lg leading-8 text-white/72">
              Клубная монета GLAME в сети TON для партнерских начислений, GLM Store, онлайн-сервисов и bridge-операций с бонусными баллами.
            </p>
            <div className="mt-9 flex flex-col gap-3 sm:flex-row">
              <Link
                href="https://partner.glamejewelry.ru/referral"
                className="inline-flex items-center justify-center gap-2 bg-white px-6 py-4 text-sm font-semibold uppercase tracking-[0.18em] text-black transition hover:bg-[#d8d8d8]"
              >
                Зарабатывать GLM <ArrowRight className="h-4 w-4" />
              </Link>
              <Link
                href="/static/glm_policy/jetton-metadata.json"
                className="inline-flex items-center justify-center gap-2 border border-white/20 px-6 py-4 text-sm font-semibold uppercase tracking-[0.18em] text-white transition hover:border-white/45"
              >
                Metadata <ExternalLink className="h-4 w-4" />
              </Link>
            </div>
          </div>

          <div className="relative mx-auto flex w-full max-w-[520px] items-center justify-center lg:justify-end">
            <div className="relative aspect-square w-full max-w-[440px] rounded-full border border-white/10 bg-white/[0.03] p-10 shadow-2xl shadow-black/60">
              <div className="absolute inset-8 rounded-full border border-white/10" />
              <img
                src="/static/glm_policy/glm-token-icon-v3.png"
                alt="GLM Coin token icon"
                className="absolute inset-0 h-full w-full object-contain p-4"
              />
            </div>
          </div>
        </div>
      </section>

      <section className="border-b border-white/10 bg-[#0d0f10]">
        <div className="mx-auto grid max-w-7xl gap-3 px-5 py-8 sm:px-8 md:grid-cols-4">
          {tokenStats.map(([label, value]) => (
            <div key={label} className="border border-white/10 bg-black/20 p-5">
              <div className="text-xs uppercase tracking-[0.24em] text-white/45">{label}</div>
              <div className="mt-3 text-xl font-semibold text-white">{value}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-16 sm:px-8 lg:py-24">
        <div className="grid gap-10 lg:grid-cols-[.8fr_1.2fr]">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.34em] text-[#c9b56a]">Что это</p>
            <h2 className="mt-4 text-3xl font-semibold tracking-normal text-white sm:text-4xl">Utility-монета, связанная с реальными сервисами GLAME</h2>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            {utilityCards.map((item) => {
              const Icon = item.icon;
              return (
                <article key={item.title} className="border border-white/10 bg-white/[0.03] p-6">
                  <Icon className="h-6 w-6 text-[#c9b56a]" />
                  <h3 className="mt-5 text-lg font-semibold text-white">{item.title}</h3>
                  <p className="mt-3 text-sm leading-6 text-white/62">{item.text}</p>
                </article>
              );
            })}
          </div>
        </div>
      </section>

      <section className="border-y border-white/10 bg-[#0c0d0e]">
        <div className="mx-auto grid max-w-7xl gap-10 px-5 py-16 sm:px-8 lg:grid-cols-[.92fr_1.08fr] lg:items-center lg:py-24">
          <div className="mx-auto w-full max-w-[360px] lg:order-2">
            <div className="rounded-[34px] border border-white/15 bg-black p-3 shadow-2xl shadow-black/70">
              <div className="overflow-hidden rounded-[26px] border border-white/10 bg-[#111]">
                <img
                  src="/static/glm_policy/glame-mobile-app-catalog.png"
                  alt="GLAME mobile app catalog"
                  className="h-auto w-full"
                />
              </div>
            </div>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.34em] text-[#c9b56a]">GLAME app</p>
            <h2 className="mt-4 text-3xl font-semibold tracking-normal text-white sm:text-4xl">
              Покупки, каталог и реферальные начисления в смартфоне
            </h2>
            <p className="mt-5 max-w-2xl text-base leading-8 text-white/64">
              У GLAME есть мобильное приложение: клиент может смотреть каталог украшений, сохранять понравившиеся позиции, возвращаться к бренду после визита в магазин и участвовать в онлайн-сценариях лояльности.
            </p>
            <div className="mt-7 grid gap-4 sm:grid-cols-2">
              <article className="border border-white/10 bg-white/[0.03] p-6">
                <Smartphone className="h-6 w-6 text-[#c9b56a]" />
                <h3 className="mt-5 text-lg font-semibold text-white">Клиентский контур</h3>
                <p className="mt-3 text-sm leading-6 text-white/62">
                  Приложение связывает каталог, покупки, баллы лояльности и будущие GLM-сценарии в одном привычном интерфейсе.
                </p>
              </article>
              <article className="border border-white/10 bg-white/[0.03] p-6">
                <UserPlus className="h-6 w-6 text-[#c9b56a]" />
                <h3 className="mt-5 text-lg font-semibold text-white">GLM за рефералов</h3>
                <p className="mt-3 text-sm leading-6 text-white/62">
                  Партнер приглашает клиента, клиент покупает украшения, а после подтверждения покупки партнер получает GLM по правилам программы.
                </p>
              </article>
            </div>
            <p className="mt-5 max-w-2xl text-sm leading-7 text-white/52">
              Такой сценарий делает GLM не отдельной "криптой ради крипты", а продолжением реального customer journey: приложение, каталог, покупка, реферал, баллы и TON-кошелек.
            </p>
          </div>
        </div>
      </section>

      <section className="border-y border-white/10 bg-[#111315]">
        <div className="mx-auto grid max-w-7xl gap-10 px-5 py-16 sm:px-8 lg:grid-cols-[1fr_1fr] lg:py-24">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.34em] text-[#c9b56a]">Tokenomics</p>
            <h2 className="mt-4 text-3xl font-semibold tracking-normal text-white sm:text-4xl">Ограниченный выпуск и управляемое распределение</h2>
            <p className="mt-5 max-w-xl text-base leading-8 text-white/64">
              GLM выпускается в ограниченном количестве и распределяется через банк GLAME, hot-wallet и правила партнерской программы. Экономика строится на использовании, реальных покупках и баллах лояльности, а не на обещании роста.
            </p>
          </div>
          <div className="divide-y divide-white/10 border border-white/10">
            {tokenomics.map(([title, text]) => (
              <div key={title} className="grid gap-3 p-5 sm:grid-cols-[180px_1fr]">
                <div className="text-sm font-semibold text-white">{title}</div>
                <div className="text-sm leading-6 text-white/62">{text}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-16 sm:px-8 lg:py-24">
        <div className="grid gap-10 lg:grid-cols-[.95fr_1.05fr] lg:items-end">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.34em] text-[#c9b56a]">Offline GLAME</p>
            <h2 className="mt-4 text-3xl font-semibold tracking-normal text-white sm:text-4xl">Монета связана с реальными покупками украшений</h2>
            <p className="mt-5 max-w-2xl text-base leading-8 text-white/64">
              В офлайн-магазинах GLAME покупатели получают и используют обычные бонусные баллы 1C. CryptoGLAME добавляет второй слой: баллы можно перевести в GLM в TON-кошельке, а перед покупкой вернуть GLM обратно в баллы по действующим правилам программы.
            </p>
            <p className="mt-4 max-w-2xl text-sm leading-7 text-white/52">
              Поэтому GLM поддержан не абстрактной идеей, а реальной операционной системой GLAME: магазинами, покупками украшений, начислением баллов и проверяемыми bridge-операциями. Это utility-связь, а не финансовая гарантия цены.
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            {offlineStores.map((store) => (
              <article key={store.title} className="overflow-hidden border border-white/10 bg-white/[0.03]">
                <div className="aspect-[4/3] bg-black">
                  <img src={store.image} alt={store.title} className="h-full w-full object-cover" />
                </div>
                <div className="p-5">
                  <div className="text-xs font-semibold uppercase tracking-[0.24em] text-[#c9b56a]">{store.subtitle}</div>
                  <h3 className="mt-3 text-xl font-semibold text-white">{store.title}</h3>
                  <p className="mt-3 flex gap-2 text-sm leading-6 text-white/60">
                    <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-[#c9b56a]" />
                    {store.address}
                  </p>
                  <p className="mt-3 text-sm leading-6 text-white/52">{store.text}</p>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-16 sm:px-8 lg:py-24">
        <div className="grid gap-5 md:grid-cols-3">
          <div className="border border-white/10 bg-white/[0.03] p-7">
            <Landmark className="h-7 w-7 text-[#c9b56a]" />
            <h3 className="mt-5 text-xl font-semibold">Чем поддержана</h3>
            <p className="mt-4 text-sm leading-7 text-white/62">
              Реальными магазинами GLAME, бонусными баллами за покупки украшений, партнерской программой, GLM Store и правилами bridge.
            </p>
          </div>
          <div className="border border-white/10 bg-white/[0.03] p-7">
            <Gift className="h-7 w-7 text-[#c9b56a]" />
            <h3 className="mt-5 text-xl font-semibold">Как заработать</h3>
            <p className="mt-4 text-sm leading-7 text-white/62">
              Подключиться к партнерской программе, приводить клиентов и получать GLM за подтвержденные покупки рефералов по действующим условиям CryptoGLAME.
            </p>
          </div>
          <div className="border border-white/10 bg-white/[0.03] p-7">
            <ShieldCheck className="h-7 w-7 text-[#c9b56a]" />
            <h3 className="mt-5 text-xl font-semibold">Что важно знать</h3>
            <p className="mt-4 text-sm leading-7 text-white/62">
              GLM не является инвестицией, электронными деньгами или гарантией выкупа. Внешние переводы необратимы, а операции могут проходить проверки.
            </p>
          </div>
        </div>
      </section>

      <section className="border-y border-white/10 bg-[#0d0f10]">
        <div className="mx-auto max-w-7xl px-5 py-16 sm:px-8 lg:py-24">
          <div className="flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.34em] text-[#c9b56a]">Roadmap</p>
              <h2 className="mt-4 text-3xl font-semibold tracking-normal text-white sm:text-4xl">Развитие CryptoGLAME</h2>
            </div>
            <Link href="https://partner.glamejewelry.ru/referral" className="inline-flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.18em] text-white/80 hover:text-white">
              Стать партнером <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
          <div className="mt-10 grid gap-4 md:grid-cols-4">
            {roadmap.map(([step, title, text]) => (
              <article key={step} className="border border-white/10 bg-black/20 p-6">
                <div className="text-sm font-semibold text-[#c9b56a]">{step}</div>
                <h3 className="mt-5 text-lg font-semibold">{title}</h3>
                <p className="mt-3 text-sm leading-6 text-white/60">{text}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-14 sm:px-8">
        <div className="grid gap-4 md:grid-cols-[1fr_auto] md:items-center">
          <div>
            <div className="flex flex-wrap items-center gap-3 text-xs uppercase tracking-[0.22em] text-white/45">
              <span className="inline-flex items-center gap-2"><BadgeCheck className="h-4 w-4 text-[#c9b56a]" /> GLM Coin</span>
              <span className="inline-flex items-center gap-2"><Coins className="h-4 w-4 text-[#c9b56a]" /> TON Jetton</span>
              <span className="inline-flex items-center gap-2"><LockKeyhole className="h-4 w-4 text-[#c9b56a]" /> Utility only</span>
            </div>
            <p className="mt-5 max-w-3xl text-sm leading-7 text-white/56">
              Вся открытая информация о правилах, рисках, metadata и bridge-процессах доступна в публичных документах GLAME. Условия программы могут меняться, если это требуется для безопасности, учета или защиты от злоупотреблений.
            </p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row md:flex-col">
            <Link href="/static/glm_policy/token-policy.md" className="border border-white/15 px-5 py-3 text-center text-sm font-semibold text-white/75 hover:border-white/40 hover:text-white">
              Token policy
            </Link>
            <Link href="/static/glm_policy/risk-disclosure.md" className="border border-white/15 px-5 py-3 text-center text-sm font-semibold text-white/75 hover:border-white/40 hover:text-white">
              Risk disclosure
            </Link>
          </div>
        </div>
      </section>
    </main>
  );
}
