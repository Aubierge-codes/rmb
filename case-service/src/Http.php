<?php
declare(strict_types=1);

final class Http
{
    public static function json(array $data, int $status = 200): void
    {
        http_response_code($status);
        header('Content-Type: application/json; charset=utf-8');
        echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    }

    /** @return array<string,mixed> */
    public static function body(): array
    {
        $raw = file_get_contents('php://input') ?: '';
        $d = json_decode($raw, true);
        return is_array($d) ? $d : [];
    }
}

/** UTF-8 safe truncation without requiring the mbstring extension. */
final class Text
{
    public static function cut(string $s, int $start, int $len): string
    {
        return preg_match('/^.{0,' . $len . '}/us', $s, $m) ? $m[0] : substr($s, 0, $len);
    }
}
