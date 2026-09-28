import types
import sys

def new_module(name):
    return types.ModuleType(name)

def get_tag():
    return sys.implementation.cache_tag
