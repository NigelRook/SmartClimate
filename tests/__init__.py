'''test __init__'''
import os
from shutil import copy2, rmtree
from .common import get_test_config_dir

def setup_custom_components():
    '''put necessary files in test custom components dir'''
    config_path = get_test_config_dir()
    if os.path.isdir(config_path):
        rmtree(config_path)
    os.mkdir(config_path)
    custom_components_path = os.path.join(config_path, 'custom_components')
    os.mkdir(custom_components_path)
    copy2(os.path.join(os.path.dirname(__file__), '../smartclimate.py'), custom_components_path)
    copy2(os.path.join(os.path.dirname(__file__), '../__init__.py'), custom_components_path)
    binary_sensor_path = os.path.join(custom_components_path, 'binary_sensor')
    os.mkdir(binary_sensor_path)
    copy2(os.path.join(os.path.dirname(__file__), '../binary_sensor/smartclimate.py'), binary_sensor_path)
    copy2(os.path.join(os.path.dirname(__file__), '../binary_sensor/__init__.py'), binary_sensor_path)

def cleanup_custom_components():
    '''remove test leftovers'''
    rmtree(get_test_config_dir())
