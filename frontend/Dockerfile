# Build the dashboard, then serve it with nginx. Build context: ./frontend
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# The app calls the API on its own address; nginx forwards /api to the backend.
ENV VITE_API_BASE=/api/v1
RUN npm run build

FROM nginx:1.27-alpine
# The image renders templates/*.template into conf.d at start, filling in ${AUTH_BASIC} (see docker/15-auth.envsh).
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --chmod=0755 docker/15-auth.envsh /docker-entrypoint.d/15-auth.envsh
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
