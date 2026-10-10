#!/bin/sh
set -eu

# Match deploy/helm/bridgecart/values.yaml when deliberately changing versions.
for image in \
  docker.io/library/wordpress:7.1.2-php8.3-apache \
  docker.io/library/wordpress:cli-2.12.0-php8.3 \
  docker.io/library/mariadb:11.8.9; do
  docker pull "$image"
  k3d image import "$image" --cluster bridgecart
done
