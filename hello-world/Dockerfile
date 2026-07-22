# Build the React UI
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

# Run API + static files
FROM node:20-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=test
ENV PORT=3000
COPY package.json package-lock.json* ./
RUN npm install --omit=dev
COPY server.js ./
COPY --from=build /app/dist ./dist
EXPOSE 3000
CMD ["node", "server.js"]
