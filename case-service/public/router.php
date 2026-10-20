<?php
// Router for PHP's built-in server (prototype). In production use php-fpm behind Nginx.
$path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
if ($path !== '/' && is_file(__DIR__ . $path) && !str_ends_with($path, '.php')) {
    return false;
}
require __DIR__ . '/index.php';
