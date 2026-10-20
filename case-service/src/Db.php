<?php
declare(strict_types=1);

/**
 * Database access. Postgres in the Docker stack (DB_DSN=pgsql:...), SQLite for laptop testing.
 * Tables are created on first connection so the service starts with no manual migration step.
 */
final class Db
{
    private static ?PDO $pdo = null;

    public static function pdo(): PDO
    {
        if (self::$pdo !== null) {
            return self::$pdo;
        }
        $dsn = getenv('DB_DSN') ?: 'sqlite:' . __DIR__ . '/../data/cases.sqlite';
        $pdo = new PDO($dsn, getenv('DB_USER') ?: null, getenv('DB_PASSWORD') ?: null, [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        ]);
        self::$pdo = $pdo;
        self::ensureSchema($pdo);
        return $pdo;
    }

    public static function now(): string
    {
        return gmdate('Y-m-d H:i:s');
    }

    private static function ensureSchema(PDO $pdo): void
    {
        $pg = $pdo->getAttribute(PDO::ATTR_DRIVER_NAME) === 'pgsql';
        $id = $pg ? 'BIGSERIAL PRIMARY KEY' : 'INTEGER PRIMARY KEY AUTOINCREMENT';
        $pdo->exec("CREATE TABLE IF NOT EXISTS users (
            id $id, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL)");
        $pdo->exec("CREATE TABLE IF NOT EXISTS cases (
            id $id, reference TEXT UNIQUE NOT NULL, type TEXT NOT NULL, summary TEXT NOT NULL,
            contact TEXT, anonymous INTEGER NOT NULL DEFAULT 0, conversation_excerpt TEXT,
            routed_to TEXT NOT NULL, expected_response TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'new',
            placeholder_routing INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)");
        $pdo->exec("CREATE TABLE IF NOT EXISTS unanswered (
            id $id, question TEXT NOT NULL, best_score REAL, reason TEXT, session_hash TEXT, created_at TEXT NOT NULL)");
        $pdo->exec("CREATE TABLE IF NOT EXISTS kb_register (
            doc_id TEXT PRIMARY KEY, title TEXT NOT NULL, category TEXT, source_url TEXT, owner TEXT, version TEXT,
            effective_date TEXT, review_date TEXT, language TEXT, status TEXT, chunks INTEGER, notes TEXT, updated_at TEXT NOT NULL)");
        $pdo->exec("CREATE TABLE IF NOT EXISTS audit_log (
            id $id, at TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, ref TEXT, detail TEXT)");
        self::seedUsers($pdo);
    }

    /** Two demo accounts, one per role. Passwords come from the environment. */
    private static function seedUsers(PDO $pdo): void
    {
        if ((int)$pdo->query('SELECT COUNT(*) FROM users')->fetchColumn() > 0) {
            return;
        }
        $ins = $pdo->prepare('INSERT INTO users (username, password_hash, role) VALUES (?,?,?)');
        $ins->execute(['admin', password_hash(getenv('DEMO_ADMIN_PASSWORD') ?: 'change-me-admin', PASSWORD_DEFAULT), 'admin']);
        $ins->execute(['officer', password_hash(getenv('DEMO_OFFICER_PASSWORD') ?: 'change-me-officer', PASSWORD_DEFAULT), 'officer']);
    }

    public static function audit(string $actor, string $action, ?string $ref = null, ?string $detail = null): void
    {
        $st = self::pdo()->prepare('INSERT INTO audit_log (at, actor, action, ref, detail) VALUES (?,?,?,?,?)');
        $st->execute([self::now(), $actor, $action, $ref, $detail]);
    }
}
