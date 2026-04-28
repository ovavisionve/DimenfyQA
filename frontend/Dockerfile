FROM node:20-alpine AS builder
WORKDIR /app

# API URL baked into the client bundle at build time
ARG NEXT_PUBLIC_API_URL=http://localhost:1000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

COPY package*.json ./
RUN npm ci

COPY . .
RUN NODE_OPTIONS="--max-old-space-size=1536" npm run build

# Minimal production image using Next.js standalone output
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
