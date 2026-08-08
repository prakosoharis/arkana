FROM node:22-alpine AS dependencies
WORKDIR /app
COPY package.json package-lock.json* ./
# Public registries occasionally reset long dependency downloads. Retry a bounded
# number of times so a transient reset does not invalidate an otherwise valid build.
RUN npm config set fetch-retries 5 \
  && npm config set fetch-retry-mintimeout 2000 \
  && npm config set fetch-retry-maxtimeout 30000 \
  && npm install --no-audit --no-fund

FROM dependencies AS build
COPY . .
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/package.json ./
COPY --from=build /app/package-lock.json* ./
RUN npm install --omit=dev
COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public
EXPOSE 3000
CMD ["npm", "run", "start"]
