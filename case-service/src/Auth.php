<?php
declare(strict_types=1);

final class Auth
{
    /** Service-to-service check: the chatbot API must present the shared key. */
    public static function requireServiceKey(): void
    {
        $expected = getenv('SERVICE_KEY') ?: 'dev-service-key';
        $given = $_SERVER['HTTP_X_SERVICE_KEY'] ?? '';
        if (!hash_equals($expected, $given)) {
            Http::json(['error' => 'unauthorized'], 401);
            exit;
        }
    }

    public static function startSession(): void
    {
        if (session_status() === PHP_SESSION_NONE) {
            session_name('rmb_admin');
            session_set_cookie_params(['httponly' => true, 'samesite' => 'Lax', 'secure' => !empty($_SERVER['HTTPS']), 'path' => '/']);
            session_start();
        }
    }

    public static function user(): ?array
    {
        self::startSession();
        return $_SESSION['user'] ?? null;
    }

    public static function require(?string $role = null): array
    {
        $u = self::user();
        if (!$u) {
            header('Location: /admin/login');
            exit;
        }
        if ($role !== null && $u['role'] !== $role) {
            http_response_code(403);
            echo View::page('Forbidden', '<p>Your role does not have access to this page.</p>', $u);
            exit;
        }
        return $u;
    }

    public static function login(string $username, string $password): bool
    {
        $st = Db::pdo()->prepare('SELECT * FROM users WHERE username = ?');
        $st->execute([$username]);
        $row = $st->fetch();
        $ok = $row && password_verify($password, $row['password_hash']);
        if (!$ok) {
            usleep(400000); // slow down guessing
            Db::audit($username !== '' ? Text::cut($username, 0, 40) : '?', 'login_failed');
            return false;
        }
        self::startSession();
        session_regenerate_id(true);
        $_SESSION['user'] = ['username' => $row['username'], 'role' => $row['role']];
        $_SESSION['csrf'] = bin2hex(random_bytes(16));
        Db::audit($row['username'], 'login');
        return true;
    }

    public static function csrf(): string
    {
        self::startSession();
        if (empty($_SESSION['csrf'])) {
            $_SESSION['csrf'] = bin2hex(random_bytes(16));
        }
        return $_SESSION['csrf'];
    }

    public static function checkCsrf(): void
    {
        self::startSession();
        if (!hash_equals($_SESSION['csrf'] ?? '', $_POST['csrf'] ?? '')) {
            http_response_code(400);
            echo 'Invalid form token. Go back and try again.';
            exit;
        }
    }
}
