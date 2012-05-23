import subprocess
import re

class Mongorestore:
    def __init__(self, caller = None):
        self.cmd = ['mongorestore']
        self.matcherror = re.compile("ERROR:.*")
        if caller:
            self._set_caller(caller)

    def _set_caller(self, caller):
        self.caller = caller

    def _get_caller(self):
        if hasattr(self, "caller"):
            return self.caller
        else:
            return subprocess.check_output

    def run(self):
        caller = self._get_caller()
        self.output = caller(self.cmd)
        self.check_errors()

    def check_errors(self):
        match = self.matcherror.findall(self.output)
        if match:
            raise subprocess.CalledProcessError(255, " ".join(match))
