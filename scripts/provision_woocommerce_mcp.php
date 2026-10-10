<?php
// Executed inside the existing WordPress pod; input arrives on stdin and is never logged.
require '/var/www/html/wp-load.php';
if (!class_exists('WooCommerce')) {
    fwrite(STDERR, "WooCommerce is not active\n");
    exit(1);
}
$input = json_decode(stream_get_contents(STDIN), true);
if (!is_array($input) || !isset($input['key'], $input['secret'])) {
    fwrite(STDERR, "Credential input is invalid\n");
    exit(1);
}
$user = get_user_by('login', 'bridgecart-mcp');
if (!$user) {
    $id = wp_create_user('bridgecart-mcp', wp_generate_password(64, true, true), 'bridgecart-mcp@bridgecart.local');
    if (is_wp_error($id)) {
        fwrite(STDERR, "Could not create dedicated WooCommerce user\n");
        exit(1);
    }
    $user = get_user_by('id', $id);
    $user->set_role('shop_manager');
}
if (!in_array('shop_manager', $user->roles, true)) {
    fwrite(STDERR, "Dedicated user has an unexpected role\n");
    exit(1);
}
global $wpdb;
$table = $wpdb->prefix . 'woocommerce_api_keys';
$hashed = wc_api_hash($input['key']);
$existing = $wpdb->get_row($wpdb->prepare("SELECT user_id, permissions FROM {$table} WHERE consumer_key = %s", $hashed));
if ($existing) {
    if ((int) $existing->user_id !== (int) $user->ID || $existing->permissions !== 'read_write') {
        fwrite(STDERR, "Existing WooCommerce key has unexpected ownership or permissions\n");
        exit(1);
    }
    echo "existing\n";
    exit(0);
}
$ok = $wpdb->insert($table, array(
    'user_id' => $user->ID,
    'description' => 'BridgeCart WooCommerce MCP',
    'permissions' => 'read_write',
    'consumer_key' => $hashed,
    'consumer_secret' => $input['secret'],
    'truncated_key' => substr($input['key'], -7),
), array('%d', '%s', '%s', '%s', '%s', '%s'));
if ($ok !== 1) {
    fwrite(STDERR, "Could not attach WooCommerce key\n");
    exit(1);
}
echo "created\n";
