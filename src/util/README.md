# Watchdog

The watchdog is a cron job that runs on a server that is running Aquamark. It
assumes that the web server is running in a Docker container. If that container
is restarted (see [main deployment docs]), the watchdog will send an email to
the system administrator. It will send another email when the server has
successfully restarted (when the container has been running for a certain amount
of time).

Installation:

1. Copy `watchdog.yaml.SAMPLE` to `watchdog.yaml`.
1. Edit `watchdog.yaml` to have your email credentials.
1. Run `./watchdog.py --test` to send a test email.
1. Verify that you received the test email.
1. Run `./watchdog.sh` to install the cron job.
