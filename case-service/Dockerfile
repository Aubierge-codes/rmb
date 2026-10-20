FROM php:8.3-cli-alpine
RUN apk add --no-cache postgresql-dev && docker-php-ext-install pdo_pgsql
WORKDIR /app
COPY public ./public
COPY src ./src
USER www-data
EXPOSE 8080
# PHP's built-in server is fine for the prototype. For production use php-fpm behind Nginx.
CMD ["php", "-S", "0.0.0.0:8080", "-t", "public", "public/router.php"]
