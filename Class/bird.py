import subprocess, json, re
from Class.templator import Templator

targets = []

class Bird:
    def __init__(self):
        global targets
        print("Loading config")
        with open('hosts.json') as handle:
            targets = json.loads(handle.read())

    def run(self):
        global targets
        
