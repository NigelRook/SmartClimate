import sys
from os import path

# pylint: disable=invalid-name
test_path = path.dirname(path.realpath(__file__))
mod_path = path.join(test_path, "../smartclimate")
sys.path.append(mod_path)
