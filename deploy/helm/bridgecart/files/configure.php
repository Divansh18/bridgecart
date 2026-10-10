<?php

if (!class_exists('WooCommerce')) {
    throw new RuntimeException('WooCommerce is not active');
}

update_option('woocommerce_currency', 'INR');
update_option('woocommerce_default_country', 'IN:MH');

if (getenv('ENABLE_DEMO_SHIPPING') === 'true') {
    update_option('woocommerce_allowed_countries', 'specific');
    update_option('woocommerce_specific_allowed_countries', array('IN'));
    update_option('woocommerce_ship_to_countries', 'specific');
    update_option('woocommerce_specific_ship_to_countries', array('IN'));
    update_option('woocommerce_calc_shipping', 'yes');

    $zone = null;
    foreach (WC_Shipping_Zones::get_zones() as $candidate) {
        if ($candidate['zone_name'] === 'BridgeCart Demo India') {
            $zone = new WC_Shipping_Zone($candidate['zone_id']);
            break;
        }
    }
    if ($zone === null) {
        $zone = new WC_Shipping_Zone();
        $zone->set_zone_name('BridgeCart Demo India');
        $zone->set_zone_order(0);
        $zone->add_location('IN', 'country');
        $zone->save();
        echo "Created demo India shipping zone\n";
    }
    $free_shipping = null;
    foreach ($zone->get_shipping_methods() as $method) {
        if ($method->id === 'free_shipping') {
            $free_shipping = $method;
            break;
        }
    }
    if ($free_shipping === null) {
        $instance_id = $zone->add_shipping_method('free_shipping');
        if (!$instance_id) {
            throw new RuntimeException('Could not create free shipping method');
        }
        update_option('woocommerce_free_shipping_' . $instance_id . '_settings', array(
            'title' => 'Free shipping',
            'enabled' => 'yes',
            'requires' => '',
            'min_amount' => '0',
        ));
        echo "Created demo free shipping method\n";
    }
}

if (getenv('ENABLE_COD') === 'true') {
    $cod = (array) get_option('woocommerce_cod_settings', array());
    $cod['enabled'] = 'yes';
    $cod['title'] = 'Cash on delivery';
    $cod['enable_for_methods'] = array();
    update_option('woocommerce_cod_settings', $cod);
    update_option('woocommerce_enable_guest_checkout', 'yes');
}

foreach (array(
    array('woocommerce_cart_page_id', 'Cart', 'cart', '[woocommerce_cart]'),
    array('woocommerce_checkout_page_id', 'Checkout', 'checkout', '[woocommerce_checkout]'),
    array('woocommerce_myaccount_page_id', 'My account', 'my-account', '[woocommerce_my_account]'),
) as $page) {
    list($option, $title, $slug, $content) = $page;
    $existing_id = (int) get_option($option, 0);
    if ($existing_id && get_post($existing_id)) {
        continue;
    }
    $existing = get_page_by_path($slug);
    $page_id = $existing ? $existing->ID : wp_insert_post(array(
        'post_title' => $title,
        'post_name' => $slug,
        'post_content' => $content,
        'post_status' => 'publish',
        'post_type' => 'page',
    ), true);
    if (is_wp_error($page_id)) {
        throw new RuntimeException('Could not create ' . $title . ' page: ' . $page_id->get_error_message());
    }
    update_option($option, $page_id);
}

if (getenv('SEED_DEMO_PRODUCT') === 'true') {
    $sku = 'BRIDGECART-DEMO-001';
    if (!wc_get_product_id_by_sku($sku)) {
        $product = new WC_Product_Simple();
        $product->set_name('BridgeCart Demo Mug');
        $product->set_sku($sku);
        $product->set_regular_price('499.00');
        $product->set_description('A clearly identified demo product for local checkout testing.');
        $product->set_status('publish');
        $product->set_catalog_visibility('visible');
        $product->set_stock_status('instock');
        $product->save();
        echo "Created demo product $sku\n";
    } else {
        echo "Demo product $sku already exists; preserving it\n";
    }
}
