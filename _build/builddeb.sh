#!/bin/bash
set -e
cd "$(dirname "$0")/.."

# create Python source distribution
[ ! -d _build/dist ] || rm -rf _build/dist
python3 setup.py sdist --dist-dir _build/dist

# Debianize source distribution
cd _build/dist
VERSION="$(find . -mindepth 1 -maxdepth 1 -name 'cron_notify-*.tar.gz' \
    | sed -e 's/^\.\/cron_notify-\(.*\)\.tar\.gz$/\1/g')"
ln -s "cron_notify-$VERSION.tar.gz" "cron-notify_$VERSION.orig.tar.gz"
tar xfz "cron_notify-$VERSION.tar.gz"
cp -R ../debian "cron_notify-$VERSION"

# build package
cd "cron_notify-$VERSION"
dpkg-buildpackage -rfakeroot -uc -us

# success
cd ../../..
PACKAGE="$(find _build/dist -mindepth 1 -maxdepth 1 -name 'cron-notify_*_all.deb')"

echo
echo "Success! Run \`dpkg -i \"$PACKAGE\"\` to install the package..."
