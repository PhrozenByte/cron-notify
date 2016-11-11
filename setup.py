from distutils.core import setup

with open("README.md") as f:
    readme = f.read()

with open("LICENSE") as f:
    license = f.read()

setup(
    name="borg_notify",
    version="1.0.0",
    description="FreeDesktop.org-compatible notification service for Borg Backup.",
    long_description=readme,
    author="Daniel Rudolf",
    url="https://github.com/PhrozenByte/borg-notify",
    license=license,
    py_modules=[ "backup_notify", "borg_notify" ],
    scripts=[ "borg-notify", "borg-notify-conf" ]
)
