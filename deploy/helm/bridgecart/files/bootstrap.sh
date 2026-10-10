#!/bin/sh
set -eu

cd /var/www/html

attempt=0
until [ -f wp-config.php ]; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 60 ]; then
    echo "Bootstrap failed: WordPress files were not available after 300 seconds" >&2
    exit 1
  fi
  sleep 5
done

attempt=0
until php -r '
  mysqli_report(MYSQLI_REPORT_OFF);
  $parts = explode(":", getenv("WORDPRESS_DB_HOST"), 2);
  try {
    $db = @mysqli_connect($parts[0], getenv("WORDPRESS_DB_USER"), getenv("WORDPRESS_DB_PASSWORD"), getenv("WORDPRESS_DB_NAME"), isset($parts[1]) ? (int) $parts[1] : 3306);
    exit($db ? 0 : 1);
  } catch (Throwable $error) {
    exit(1);
  }
'; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 60 ]; then
    echo "Bootstrap failed: MariaDB was not available after 300 seconds" >&2
    exit 1
  fi
  sleep 5
done

if wp core is-installed --quiet; then
  echo "WordPress already installed; preserving existing admin and content"
else
  echo "Installing WordPress"
  php /bootstrap/install.php
fi

wp option update home "$STORE_URL" --quiet
wp option update siteurl "$STORE_URL" --quiet
wp option update timezone_string Asia/Kolkata --quiet
wp rewrite structure '/%postname%/' --hard --quiet
wp rewrite flush --hard --quiet

if wp plugin is-installed woocommerce; then
  installed_version="$(wp plugin get woocommerce --field=version)"
  if [ "$installed_version" != "$WOOCOMMERCE_VERSION" ]; then
    if [ "$ALLOW_PLUGIN_UPGRADE" != "true" ]; then
      echo "Bootstrap failed: WooCommerce is $installed_version, requested $WOOCOMMERCE_VERSION. Review backup and set allowPluginUpgrade explicitly." >&2
      exit 1
    fi
    if ! php -r 'exit(version_compare($argv[1], $argv[2], ">") ? 0 : 1);' "$WOOCOMMERCE_VERSION" "$installed_version"; then
      echo "Bootstrap failed: automatic WooCommerce downgrade is not supported" >&2
      exit 1
    fi
    echo "Upgrading WooCommerce from $installed_version to $WOOCOMMERCE_VERSION"
    wp plugin install woocommerce --version="$WOOCOMMERCE_VERSION" --force --activate
  else
    wp plugin activate woocommerce --quiet || wp plugin is-active woocommerce
  fi
else
  echo "Installing WooCommerce $WOOCOMMERCE_VERSION"
  wp plugin install woocommerce --version="$WOOCOMMERCE_VERSION" --activate
fi

wp eval-file /bootstrap/configure.php
echo "BridgeCart store bootstrap complete"
