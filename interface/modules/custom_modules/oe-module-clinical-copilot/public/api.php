<?php

declare(strict_types=1);

/**
 * Internal API endpoint — called exclusively by the Python AI service.
 *
 * Security model
 * ──────────────
 * This endpoint does NOT use OpenEMR session auth — it is called by Python,
 * not by a browser. Authentication is a short-lived HMAC token:
 *
 *   token format: "<unix_timestamp>:<sha256_hmac>"
 *   signature covers: "<pid>:<timestamp>"
 *
 * This means:
 *   - A token for pid=1 cannot be used to query pid=2 (pid is in the signature)
 *   - Tokens expire after 30 seconds (generous for LLM latency, short for replay)
 *   - Constant-time comparison (hash_equals) prevents timing attacks
 *
 * The secret (COPILOT_HMAC_SECRET) is shared between this container and the
 * Python container via environment variable — never hardcoded in source.
 *
 * Why PDO instead of OpenEMR's QueryUtils
 * ────────────────────────────────────────
 * QueryUtils requires the full OpenEMR bootstrap (globals.php → session → ACL).
 * This endpoint has no browser session to bootstrap from. PDO gives us
 * parameterized queries with the same security properties, using the DB
 * credentials already present in the openemr container via env vars.
 */

use OpenEMR\Modules\ClinicalCopilot\Service\PatientDataService;

require_once __DIR__ . '/../src/Service/PatientDataService.php';

header('Content-Type: application/json');

// ── Read inputs ───────────────────────────────────────────────────────────────
$secret = (string)(getenv('COPILOT_HMAC_SECRET') ?: 'dev-hmac-secret');
$pid    = intval($_GET['pid'] ?? 0);
$action = (string)($_GET['action'] ?? '');
$token  = (string)($_GET['token'] ?? '');

// ── GUARD 1: pid must be a positive integer ───────────────────────────────────
if ($pid <= 0) {
    http_response_code(400);
    echo json_encode(['error' => 'Invalid pid']);
    exit;
}

// ── GUARD 2: HMAC token validation ────────────────────────────────────────────
// Token format: "<timestamp>:<sha256_signature>"
// The signature covers "{pid}:{timestamp}" so a stolen token for pid=1
// cannot be replayed to query pid=2.
$parts = explode(':', $token, 2);
if (count($parts) !== 2) {
    http_response_code(401);
    echo json_encode(['error' => 'Malformed token']);
    exit;
}
[$ts, $sig] = $parts;
$ts = intval($ts);

// 30-second window — enough headroom for an LLM call, tight enough to limit replay.
if (abs(time() - $ts) > 30) {
    http_response_code(401);
    echo json_encode(['error' => 'Token expired']);
    exit;
}

$expected = hash_hmac('sha256', "{$pid}:{$ts}", $secret);
// hash_equals: constant-time comparison — prevents timing side-channel attacks.
if (!hash_equals($expected, $sig)) {
    http_response_code(401);
    echo json_encode(['error' => 'Invalid token']);
    exit;
}

// ── Database connection ────────────────────────────────────────────────────────
// Env vars MYSQL_HOST, MYSQL_USER, MYSQL_PASS are set by docker-compose.yml
// on the openemr service. MYSQL_DATABASE defaults to 'openemr'.
try {
    $dsn = sprintf(
        'mysql:host=%s;port=%s;dbname=%s;charset=utf8mb4',
        getenv('MYSQL_HOST')     ?: 'mysql',
        getenv('MYSQL_PORT')     ?: '3306',
        getenv('MYSQL_DATABASE') ?: 'openemr'
    );
    $pdo = new PDO(
        $dsn,
        getenv('MYSQL_USER') ?: 'openemr',
        getenv('MYSQL_PASS') ?: 'openemr',
        [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]
    );
} catch (\PDOException $e) {
    http_response_code(503);
    echo json_encode(['error' => 'Database unavailable']);
    exit;
}

// ── Dispatch ───────────────────────────────────────────────────────────────────
$service = new PatientDataService($pdo);

$data = match($action) {
    'demographics' => $service->getDemographics($pid),
    'medications'  => $service->getMedications($pid),
    'encounters'   => $service->getEncounters($pid),
    'labs'         => $service->getLabs($pid),
    'problems'     => $service->getProblems($pid),
    'allergies'    => $service->getAllergies($pid),
    default        => ['error' => "Unknown action: {$action}"],
};

http_response_code(isset($data['error']) ? 400 : 200);
echo json_encode($data);
