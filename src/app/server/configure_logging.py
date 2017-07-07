import logging
import os

from utils import get_package_dir


def configure_logging():
    package_dir = get_package_dir()
    logconf_path = os.path.join(package_dir, "logging.cfg")
    if not os.path.exists(logconf_path):
        print("Warning: log config file %s does not exist." % logconf_path)
    else:
        logging.config.fileConfig(logconf_path)


configure_logging()
