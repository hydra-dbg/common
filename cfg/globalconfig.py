from .frozenconfigparser import FrozenConfigParser
import sys, os

__CONFIG = None

def load_global_config(config_file=None, user_file=None, ignore_if_loaded=False):
    global __CONFIG
    if __CONFIG is not None:
        if ignore_if_loaded:
            return
        raise ValueError("The global configuration is already loaded.")
   
   
    # TODO This shouldn't be hardcoded!
    script_home = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.pardir

    if config_file is None:
        config_file = os.path.join(script_home, parent, "config", "global.cfg")

    if user_file is None:
        user_file = os.path.join(script_home, parent, "config", "user.cfg")

    __CONFIG = FrozenConfigParser(
            optionxform = str, 
            filename_of_defaults = config_file,
            filenames_of_potential_configs = [user_file])

def get_global_config():
    if __CONFIG is None:
        load_global_config()
    return __CONFIG 
