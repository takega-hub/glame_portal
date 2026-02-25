FROM node:20-alpine

WORKDIR /app

# Переменные для Next.js при сборке (в prod API на том же хосте через nginx)
ARG NEXT_PUBLIC_API_URL=""
ARG NEXT_PUBLIC_WS_URL=""
ARG NEXT_PUBLIC_SKIP_APP_AUTH=""
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL
ENV NEXT_PUBLIC_SKIP_APP_AUTH=$NEXT_PUBLIC_SKIP_APP_AUTH

COPY package*.json ./
RUN npm ci

COPY . .

# Увеличить лимит памяти для сборки, если на сервере мало RAM
ENV NODE_OPTIONS="--max-old-space-size=4096"
RUN npm run build

CMD ["npm", "start"]
