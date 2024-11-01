#!/bin/bash
# cron-notify
#
# FreeDesktop.org-compatible notification service to periodically ask for
# acknowledgement before executing a cronjob. It is often used for backup
# software.
#
# Copyright (C) 2016-2024 Daniel Rudolf
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, version 3 of the License only.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program. If not, see <http://www.gnu.org/licenses/>.

set -eu -o pipefail
cd "$(dirname "$0")/.."

# create Python source distribution
[ ! -e _build/dist ] || { [ -d _build/dist ] && rm -rf _build/dist ; }
python3 setup.py sdist --dist-dir _build/dist

# Debianize source distribution
cd _build/dist
VERSION="$(find . -mindepth 1 -maxdepth 1 -name 'cron_notify-*.tar.gz' \
    | sed -e '1 s/^\.\/cron_notify-\(.*\)\.tar\.gz$/\1/g')"
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
