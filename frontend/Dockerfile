FROM node:20-alpine AS builder
WORKDIR /app

# INTERNAL_API_URL is the backend URL used by the Next.js server for rewrites.
# In Docker it must be the service name (http://api:1000).
ARG INTERNAL_API_URL=http://localhost:1000
ENV INTERNAL_API_URL=$INTERNAL_API_URL

COPY package*.json ./
RUN npm ci

COPY . .
RUN NODE_OPTIONS="--max-old-space-size=1536" npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
