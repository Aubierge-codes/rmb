<?php
declare(strict_types=1);

foreach (['Routing', 'Db', 'Cases', 'Http', 'Auth', 'View'] as $c) {
    require __DIR__ . '/../src/' . $c . '.php';
}

$method = $_SERVER['REQUEST_METHOD'];
$path = rtrim(parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH) ?: '/', '/') ?: '/';
$e = [View::class, 'e'];

header('X-Content-Type-Options: nosniff');
header('X-Frame-Options: DENY');
header('Referrer-Policy: no-referrer');

try {
    // ---------- Service API (used by the chatbot API, protected by the shared service key) ----------
    if ($path === '/api/v1/health') {
        Db::pdo();
        Http::json(['status' => 'ok']);
        exit;
    }
    if ($path === '/api/v1/cases' && $method === 'POST') {
        Auth::requireServiceKey();
        try {
            Http::json(Cases::create(Http::body()), 201);
        } catch (InvalidArgumentException $ex) {
            Http::json(['error' => $ex->getMessage()], 422);
        }
        exit;
    }
    if (preg_match('#^/api/v1/cases/([A-Z0-9-]+)$#', $path, $m) && $method === 'GET') {
        Auth::requireServiceKey();
        $c = Cases::find($m[1]);
        $c ? Http::json(['reference' => $c['reference'], 'status' => $c['status'], 'routed_to' => $c['routed_to']]) : Http::json(['error' => 'not found'], 404);
        exit;
    }
    if ($path === '/api/v1/unanswered' && $method === 'POST') {
        Auth::requireServiceKey();
        $b = Http::body();
        $q = trim((string)($b['question'] ?? ''));
        if ($q === '') { Http::json(['error' => 'question is required'], 422); exit; }
        $st = Db::pdo()->prepare('INSERT INTO unanswered (question,best_score,reason,session_hash,created_at) VALUES (?,?,?,?,?)');
        $st->execute([Text::cut(Cases::redact($q), 0, 1000), (float)($b['best_score'] ?? 0), Text::cut((string)($b['reason'] ?? ''), 0, 200), Text::cut((string)($b['session_hash'] ?? ''), 0, 32), Db::now()]);
        Http::json(['ok' => true], 201);
        exit;
    }
    if ($path === '/api/v1/documents' && $method === 'PUT') {
        Auth::requireServiceKey();
        $b = Http::body();
        if (empty($b['doc_id']) || empty($b['title'])) { Http::json(['error' => 'doc_id and title are required'], 422); exit; }
        $st = Db::pdo()->prepare('INSERT INTO kb_register (doc_id,title,category,source_url,owner,version,effective_date,review_date,language,status,chunks,notes,updated_at)
            VALUES (:doc_id,:title,:category,:source_url,:owner,:version,:effective_date,:review_date,:language,:status,:chunks,:notes,:updated_at)
            ON CONFLICT(doc_id) DO UPDATE SET title=excluded.title,category=excluded.category,source_url=excluded.source_url,owner=excluded.owner,
            version=excluded.version,effective_date=excluded.effective_date,review_date=excluded.review_date,language=excluded.language,
            status=excluded.status,chunks=excluded.chunks,notes=excluded.notes,updated_at=excluded.updated_at');
        $st->execute([
            ':doc_id' => (string)$b['doc_id'], ':title' => (string)$b['title'], ':category' => $b['category'] ?? null, ':source_url' => $b['source_url'] ?? null,
            ':owner' => $b['owner'] ?? null, ':version' => $b['version'] ?? null, ':effective_date' => $b['effective_date'] ?? null, ':review_date' => $b['review_date'] ?? null,
            ':language' => $b['language'] ?? 'en', ':status' => $b['status'] ?? 'unverified', ':chunks' => (int)($b['chunks'] ?? 0), ':notes' => $b['notes'] ?? null, ':updated_at' => Db::now(),
        ]);
        Http::json(['ok' => true]);
        exit;
    }

    // ---------- Admin portal ----------
    if ($path === '/admin/login') {
        $err = '';
        if ($method === 'POST') {
            if (Auth::login(trim((string)($_POST['username'] ?? '')), (string)($_POST['password'] ?? ''))) {
                header('Location: /admin/cases');
                exit;
            }
            $err = '<p style="color:#b00020"><strong>Sign-in failed.</strong></p>';
        }
        echo View::page('Sign in', $err . '<form method="post" class="card"><p><label>Username<br><input name="username" autocomplete="username" required></label></p>'
            . '<p><label>Password<br><input type="password" name="password" autocomplete="current-password" required></label></p><button>Sign in</button></form>', null);
        exit;
    }
    if ($path === '/admin/logout') {
        Auth::startSession();
        if (!empty($_SESSION['user'])) { Db::audit($_SESSION['user']['username'], 'logout'); }
        session_destroy();
        header('Location: /admin/login');
        exit;
    }
    if ($path === '/admin' || $path === '/') {
        header('Location: /admin/cases');
        exit;
    }

    if ($path === '/admin/cases') {
        $u = Auth::require();
        $status = $_GET['status'] ?? '';
        $sql = 'SELECT * FROM cases' . (in_array($status, Cases::STATUSES, true) ? ' WHERE status = :s' : '') . ' ORDER BY id DESC LIMIT 200';
        $st = Db::pdo()->prepare($sql);
        $st->execute(in_array($status, Cases::STATUSES, true) ? [':s' => $status] : []);
        $rows = '';
        foreach ($st->fetchAll() as $r) {
            $rows .= '<tr><td><a href="/admin/case?ref=' . $e($r['reference']) . '">' . $e($r['reference']) . '</a></td><td>' . $e(Routing::for($r['type'])[0]) . '</td><td><span class="tag">'
                . $e($r['status']) . '</span></td><td>' . $e($r['routed_to']) . '</td><td>' . ($r['anonymous'] ? 'Anonymous' : ($r['contact'] ? 'Contact given' : 'No contact')) . '</td><td>' . $e($r['created_at']) . '</td></tr>';
        }
        $filters = '<p>Filter: <a href="/admin/cases">all</a>';
        foreach (Cases::STATUSES as $s) { $filters .= ' | <a href="/admin/cases?status=' . $s . '">' . $s . '</a>'; }
        echo View::page('Cases', $filters . '</p><table><tr><th>Reference</th><th>Type</th><th>Status</th><th>Routed to (placeholder)</th><th>Contact</th><th>Created (UTC)</th></tr>'
            . ($rows ?: '<tr><td colspan="6">No cases yet.</td></tr>') . '</table>', $u);
        exit;
    }
    if ($path === '/admin/case') {
        $u = Auth::require();
        $c = Cases::find((string)($_GET['ref'] ?? ''));
        if (!$c) { http_response_code(404); echo View::page('Not found', '<p>Case not found.</p>', $u); exit; }
        Db::audit($u['username'], 'case_viewed', $c['reference']);
        $opts = '';
        foreach (Cases::STATUSES as $s) { $opts .= '<option' . ($s === $c['status'] ? ' selected' : '') . '>' . $s . '</option>'; }
        $log = Db::pdo()->prepare('SELECT * FROM audit_log WHERE ref = ? ORDER BY id DESC LIMIT 50');
        $log->execute([$c['reference']]);
        $lrows = '';
        foreach ($log->fetchAll() as $l) { $lrows .= '<tr><td>' . $e($l['at']) . '</td><td>' . $e($l['actor']) . '</td><td>' . $e($l['action']) . '</td><td>' . $e($l['detail']) . '</td></tr>'; }
        echo View::page('Case ' . $c['reference'],
            '<div class="card"><p><strong>Type:</strong> ' . $e(Routing::for($c['type'])[0]) . ' &nbsp; <strong>Routed to:</strong> ' . $e($c['routed_to']) . ' &nbsp; <strong>Expected response:</strong> ' . $e($c['expected_response']) . '</p>'
            . '<p><strong>Contact:</strong> ' . ($c['anonymous'] ? '<span class="tag ok">Anonymous: no contact stored</span>' : $e($c['contact'] ?: 'none given')) . '</p>'
            . '<h3>Summary</h3><pre>' . $e($c['summary']) . '</pre><h3>Conversation excerpt</h3><pre>' . $e($c['conversation_excerpt']) . '</pre>'
            . '<form method="post" action="/admin/case/status"><input type="hidden" name="csrf" value="' . $e(Auth::csrf()) . '"><input type="hidden" name="ref" value="' . $e($c['reference']) . '">'
            . '<label>Status <select name="status">' . $opts . '</select></label> <button>Update</button></form></div>'
            . '<h3>History</h3><table><tr><th>When (UTC)</th><th>Who</th><th>Action</th><th>Detail</th></tr>' . $lrows . '</table>', $u);
        exit;
    }
    if ($path === '/admin/case/status' && $method === 'POST') {
        $u = Auth::require();
        Auth::checkCsrf();
        $ref = (string)($_POST['ref'] ?? '');
        $s = (string)($_POST['status'] ?? '');
        if (Cases::find($ref) && in_array($s, Cases::STATUSES, true)) {
            Db::pdo()->prepare('UPDATE cases SET status=?, updated_at=? WHERE reference=?')->execute([$s, Db::now(), $ref]);
            Db::audit($u['username'], 'status_changed', $ref, "to=$s");
        }
        header('Location: /admin/case?ref=' . urlencode($ref));
        exit;
    }
    if ($path === '/admin/unanswered') {
        $u = Auth::require();
        $rows = '';
        foreach (Db::pdo()->query('SELECT * FROM unanswered ORDER BY id DESC LIMIT 200')->fetchAll() as $r) {
            $rows .= '<tr><td>' . $e($r['created_at']) . '</td><td>' . $e($r['question']) . '</td><td>' . $e($r['reason']) . '</td><td>' . $e($r['best_score']) . '</td></tr>';
        }
        echo View::page('Unanswered questions', '<p>Questions the chatbot could not answer from the loaded documents. Use this list to decide which content to add next.</p>'
            . '<table><tr><th>When (UTC)</th><th>Question</th><th>Reason</th><th>Best match score</th></tr>' . ($rows ?: '<tr><td colspan="4">None yet.</td></tr>') . '</table>', $u);
        exit;
    }
    if ($path === '/admin/review') {
        $u = Auth::require('admin');
        $rows = '';
        $today = gmdate('Y-m-d');
        foreach (Db::pdo()->query('SELECT * FROM kb_register ORDER BY doc_id')->fetchAll() as $r) {
            $flags = [];
            if (($r['status'] ?? '') !== 'approved') { $flags[] = 'not approved by owning department'; }
            if (empty($r['review_date'])) { $flags[] = 'no review date'; } elseif ($r['review_date'] < $today) { $flags[] = 'review overdue'; }
            if (stripos((string)$r['title'] . (string)$r['owner'], 'to be confirmed') !== false) { $flags[] = 'details to be confirmed'; }
            if (stripos((string)$r['notes'], 'WARNINGS') !== false) { $flags[] = 'ingestion warnings'; }
            $rows .= '<tr class="' . ($flags ? 'bad' : 'ok') . '"><td>' . $e($r['title']) . '<br><small>' . $e($r['doc_id']) . '</small></td><td>' . $e($r['owner']) . '</td><td>' . $e($r['version']) . '</td><td>'
                . $e($r['review_date'] ?: 'not set') . '</td><td>' . $e($r['status']) . '</td><td>' . $e($r['chunks']) . '</td><td>' . ($flags ? $e(implode('; ', $flags)) : 'OK') . '</td></tr>';
        }
        echo View::page('Content review list', '<p>Rule: only documents approved by the owning department should be published to the chatbot, and superseded versions retired.</p>'
            . '<table><tr><th>Document</th><th>Owner</th><th>Version</th><th>Review date</th><th>Status</th><th>Chunks</th><th>Needs attention</th></tr>'
            . ($rows ?: '<tr><td colspan="7">No documents registered yet. Run the ingestion script.</td></tr>') . '</table>', $u);
        exit;
    }
    if ($path === '/admin/audit') {
        $u = Auth::require('admin');
        $rows = '';
        foreach (Db::pdo()->query('SELECT * FROM audit_log ORDER BY id DESC LIMIT 200')->fetchAll() as $l) {
            $rows .= '<tr><td>' . $e($l['at']) . '</td><td>' . $e($l['actor']) . '</td><td>' . $e($l['action']) . '</td><td>' . $e($l['ref']) . '</td><td>' . $e($l['detail']) . '</td></tr>';
        }
        echo View::page('Audit log', '<table><tr><th>When (UTC)</th><th>Who</th><th>Action</th><th>Reference</th><th>Detail</th></tr>' . $rows . '</table>', $u);
        exit;
    }

    Http::json(['error' => 'not found'], 404);
} catch (Throwable $ex) {
    error_log('case-service error: ' . $ex->getMessage());
    Http::json(['error' => 'internal error'], 500);
}
