<?php
// Suggest a site: receives the short form on contribute.html.
//
// Each submission is appended as one JSON line to an inbox OUTSIDE the web
// root (../pli-inbox/suggestions.jsonl), so rsync --delete never touches it
// and it is never served. tools/pull_suggestions.py copies it down and merges
// new entries into submissions/suggestions.json for research.
//
// If .suggest.ini sets a recipient, each submission is also emailed:
//   recipient = "you@example.org"
// (.suggest.ini is denied to the web by the dotfile rule in .htaccess and kept
// out of git by .gitignore.)

function back($status) {
    header('Location: contribute.html?suggest=' . $status . '#suggest', true, 303);
    exit;
}

function field($key, $max) {
    $v = isset($_POST[$key]) && is_string($_POST[$key]) ? trim($_POST[$key]) : '';
    $v = str_replace("\0", '', $v);
    return function_exists('mb_substr') ? mb_substr($v, 0, $max, 'UTF-8') : substr($v, 0, $max);
}

function one_line($v) {
    return trim(preg_replace('/[\r\n\t]+/', ' ', $v));
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    header('Location: contribute.html#suggest', true, 302);
    exit;
}

// Spam checks: hidden honeypot filled, or form sent faster than a person could.
// A missing timestamp (no JavaScript) is allowed through. Bots are told "sent".
if (field('website', 200) !== '') {
    back('sent');
}
$t = field('t', 20);
if ($t !== '' && ctype_digit($t)) {
    $elapsed = time() - intdiv((int)$t, 1000);
    if ($elapsed >= 0 && $elapsed < 3) {
        back('sent');
    }
}

$site  = one_line(field('site', 300));
$note  = field('note', 5000);
$email = one_line(field('email', 200));

if ($site === '') {
    back('invalid');
}
if ($email !== '' && !filter_var($email, FILTER_VALIDATE_EMAIL)) {
    $email = '';
}

$record = [
    'received' => gmdate('Y-m-d\TH:i:s\Z'),
    'site'     => $site,
    'note'     => $note,
    'email'    => $email,
];

// 1. Inbox file outside the web root
$saved = false;
$dir = dirname(__DIR__) . '/pli-inbox';
if (is_dir($dir) || @mkdir($dir, 0700, true)) {
    $line = json_encode($record, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) . "\n";
    $saved = @file_put_contents($dir . '/suggestions.jsonl', $line, FILE_APPEND | LOCK_EX) !== false;
}
if (!$saved) {
    error_log('suggest.php: could not write ' . $dir . '/suggestions.jsonl');
}

// 2. Optional email notice
$mailed = false;
$conf = @parse_ini_file(__DIR__ . '/.suggest.ini');
$to = is_array($conf) && isset($conf['recipient']) ? trim($conf['recipient']) : '';
if ($to !== '' && filter_var($to, FILTER_VALIDATE_EMAIL)) {
    $body  = "Site: $site\n\n";
    $body .= "Note:\n" . ($note !== '' ? $note : '(none)') . "\n\n";
    $body .= "Email: " . ($email !== '' ? $email : '(not given)') . "\n";
    $body .= "Received: " . $record['received'] . "\n";
    $body .= $saved ? "Saved to the inbox.\n" : "NOT saved to the inbox; add it by hand.\n";
    $subject = '=?UTF-8?B?' . base64_encode('PLI site suggestion: ' . $site) . '?=';
    $headers  = "From: Public Lands Institute <noreply@publiclandsinstitute.net>\r\n";
    if ($email !== '') {
        $headers .= "Reply-To: $email\r\n";
    }
    $headers .= "MIME-Version: 1.0\r\n";
    $headers .= "Content-Type: text/plain; charset=UTF-8\r\n";
    $headers .= "Content-Transfer-Encoding: 8bit\r\n";
    $mailed = mail($to, $subject, $body, $headers, '-fnoreply@publiclandsinstitute.net');
}

back(($saved || $mailed) ? 'sent' : 'error');
