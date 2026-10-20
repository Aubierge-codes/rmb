<?php
declare(strict_types=1);

final class View
{
    public static function e(mixed $v): string
    {
        return htmlspecialchars((string)($v ?? ''), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
    }

    public static function page(string $title, string $body, ?array $user): string
    {
        $e = [self::class, 'e'];
        $nav = '';
        if ($user) {
            $nav = '<nav><a href="/admin/cases">Cases</a><a href="/admin/unanswered">Unanswered questions</a>'
                . ($user['role'] === 'admin' ? '<a href="/admin/review">Content review</a><a href="/admin/audit">Audit log</a>' : '')
                . '<span class="sp"></span><span>' . $e($user['username']) . ' (' . $e($user['role']) . ')</span><a href="/admin/logout">Sign out</a></nav>';
        }
        return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            . '<title>' . $e($title) . ' | RMB chatbot admin (prototype)</title><style>'
            . 'body{font:15px/1.5 system-ui,Segoe UI,Arial,sans-serif;margin:0;background:#f4f6f9;color:#1b2430}'
            . 'header{background:#1f3864;color:#fff;padding:12px 24px;font-weight:600}'
            . '.warn{background:#fff4ce;border-bottom:1px solid #e0c36a;padding:8px 24px;font-size:13px}'
            . 'nav{display:flex;gap:18px;background:#fff;border-bottom:1px solid #d7dde6;padding:10px 24px;align-items:center}'
            . 'nav a{color:#1f3864;text-decoration:none;font-weight:600}.sp{flex:1}'
            . 'main{padding:24px;max-width:1150px;margin:0 auto}'
            . 'table{border-collapse:collapse;width:100%;background:#fff}th,td{border:1px solid #d7dde6;padding:8px 10px;text-align:left;vertical-align:top;font-size:14px}'
            . 'th{background:#1f3864;color:#fff}.tag{display:inline-block;padding:1px 8px;border-radius:10px;background:#e6ecf5;font-size:12px}'
            . '.bad{background:#fde2e2}.ok{background:#e2f3e5}.card{background:#fff;border:1px solid #d7dde6;padding:16px;margin-bottom:16px}'
            . 'pre{white-space:pre-wrap;background:#f4f6f9;padding:10px;border:1px solid #d7dde6}'
            . 'input,select,button{font:inherit;padding:6px 10px}button{background:#1f3864;color:#fff;border:0;cursor:pointer}'
            . '</style></head><body><header>RMB AI Chatbot: case management (prototype)</header>'
            . '<div class="warn">Prototype data only. Routing units, response times and contacts are placeholders until confirmed by RMB. Do not enter real personal data.</div>'
            . $nav . '<main><h1>' . $e($title) . '</h1>' . $body . '</main></body></html>';
    }
}
