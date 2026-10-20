<?php
declare(strict_types=1);

final class Cases
{
    private const ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'; // no look-alike characters

    public static function redact(string $text): string
    {
        $text = preg_replace('/[\w.+-]+@[\w-]+\.[\w.-]+/', '[email removed]', $text) ?? $text;
        return preg_replace('/\+?\d[\d\s().-]{7,}\d/', '[number removed]', $text) ?? $text;
    }

    private static function newReference(): string
    {
        $s = '';
        for ($i = 0; $i < 5; $i++) {
            $s .= self::ALPHABET[random_int(0, strlen(self::ALPHABET) - 1)];
        }
        return 'RMB-' . gmdate('ymd') . '-' . $s;
    }

    /** @param array<string,mixed> $in */
    public static function create(array $in): array
    {
        $type = Routing::normalise((string)($in['type'] ?? 'general_enquiry'));
        $summary = trim((string)($in['summary'] ?? ''));
        if ($summary === '') {
            throw new InvalidArgumentException('summary is required');
        }
        $anonymous = !empty($in['anonymous']);
        $contact = $anonymous ? null : (isset($in['contact']) && $in['contact'] !== '' ? Text::cut((string)$in['contact'], 0, 300) : null);
        $summary = Text::cut($summary, 0, 4000);
        $excerpt = Text::cut((string)($in['conversation_excerpt'] ?? ''), 0, 8000);
        if ($anonymous) { // anonymous means anonymous: strip contact details from every stored text field
            $summary = self::redact($summary);
            $excerpt = self::redact($excerpt);
        }
        [, $unit, $eta] = Routing::for($type);
        $pdo = Db::pdo();
        $now = Db::now();
        for ($try = 0; $try < 5; $try++) {
            $ref = self::newReference();
            try {
                $st = $pdo->prepare('INSERT INTO cases (reference,type,summary,contact,anonymous,conversation_excerpt,routed_to,expected_response,status,created_at,updated_at)
                                     VALUES (?,?,?,?,?,?,?,?,?,?,?)');
                $st->execute([$ref, $type, $summary, $contact, $anonymous ? 1 : 0, $excerpt, $unit, $eta, 'new', $now, $now]);
                Db::audit('chatbot', 'case_created', $ref, "type=$type anonymous=" . ($anonymous ? 'yes' : 'no'));
                return ['reference' => $ref, 'routed_to' => $unit, 'expected_response_time' => $eta, 'status' => 'new', 'placeholder_routing' => true];
            } catch (PDOException $e) {
                if ($try === 4) { throw $e; } // reference collision is the only expected cause; retry
            }
        }
        throw new RuntimeException('could not create case');
    }

    public static function find(string $ref): ?array
    {
        $st = Db::pdo()->prepare('SELECT * FROM cases WHERE reference = ?');
        $st->execute([$ref]);
        return $st->fetch() ?: null;
    }

    public const STATUSES = ['new', 'assigned', 'in_progress', 'closed'];
}
