import os
import configparser

config_path = os.path.join(os.path.dirname(__file__), "../config.ini")

CONFIG = configparser.ConfigParser()
CONFIG.read(config_path)
