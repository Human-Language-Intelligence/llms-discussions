import os
import configparser

config_path = os.path.join(os.path.dirname(__file__), "../config.ini")

CONFIG = configparser.ConfigParser()
with open(config_path, 'r', encoding='utf-8') as f:
    CONFIG.read_file(f)
