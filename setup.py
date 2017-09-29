from distutils.core import setup

with open("README.md") as f:
    readme = f.read()

with open("LICENSE") as f:
    license = f.read()

setup(
    name="cron_notify",
    version="1.0.0",
    description="FreeDesktop.org-compatible notification service to periodically ask for " +
        "acknowledgement before executing a cronjob. It is often used for backup software.",
    long_description=readme,
    author="Daniel Rudolf",
    author_email="cron-notify@daniel-rudolf.de",
    url="https://github.com/PhrozenByte/cron-notify",
    license=license,
    py_modules=[ "cron_notify" ],
    scripts=[ "cron-notify" ]
)
