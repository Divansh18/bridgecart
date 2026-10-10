<?php

// Read the credential inside the process. It never becomes a command argument or log line.
$password = trim(file_get_contents('/run/bridgecart-secrets/wordpress-admin-password'));
if ($password === '') {
    throw new RuntimeException('Admin password Secret is empty');
}

$url = getenv('STORE_URL');
$parts = parse_url($url);
if (!$parts || !isset($parts['host'])) {
    throw new RuntimeException('Invalid store URL');
}

$_SERVER['HTTP_HOST'] = $parts['host'];
$_SERVER['SERVER_NAME'] = $parts['host'];
$_SERVER['SERVER_PORT'] = (string) ($parts['port'] ?? ($parts['scheme'] === 'https' ? 443 : 80));
$_SERVER['REQUEST_URI'] = '/';
if ($parts['scheme'] === 'https') {
    $_SERVER['HTTPS'] = 'on';
}

define('WP_INSTALLING', true);
require '/var/www/html/wp-load.php';
require_once ABSPATH . 'wp-admin/includes/upgrade.php';

if (is_blog_installed()) {
    echo "WordPress was installed by another process; preserving it\n";
    return;
}

wp_install(
    getenv('STORE_TITLE'),
    getenv('STORE_ADMIN_USER'),
    getenv('STORE_ADMIN_EMAIL'),
    true,
    '',
    $password
);
echo "WordPress installation complete\n";
