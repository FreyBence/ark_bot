"""SteamCMD progress parsed independently of Discord."""
from dataclasses import dataclass, field
import re
import time


@dataclass
class SteamProgress:
    stage: str = "Preparing"
    percent: float | None = None
    started: float = field(default_factory=time.monotonic)
    already_current: bool = False
    _pending: str = ""

    def feed(self, text):
        self._pending += text
        records = re.split(r"[\r\n]", self._pending)
        self._pending = records.pop()
        for record in records:
            self._parse(record)
        # Parse incomplete records too, so carriage-return and chunk boundaries
        # do not postpone progress until a newline arrives.
        self._parse(self._pending)
        self._pending = self._pending[-4096:]

    def _parse(self, line):
        lower = line.lower()
        self.already_current |= "already up to date" in lower
        stage = None
        if "update state" in lower:
            if "validat" in lower or "verif" in lower:
                stage = "Validating files"
            elif "download" in lower:
                stage = "Downloading files"
            elif "install" in lower or "commit" in lower:
                stage = "Installing files"
            else:
                stage = "Processing server files"
        elif "logging in" in lower or "waiting for user info" in lower:
            stage = "Connecting to Steam"
        elif "success!" in lower and "fully installed" in lower:
            stage = "Finishing validation"
        if stage is not None:
            if stage != self.stage:
                self.percent = None
            self.stage = stage
            match = re.search(r"progress:\s*(\d+(?:\.\d+)?)", line, re.I)
            if match:
                self.percent = max(0.0, min(100.0, float(match.group(1))))

    def render(self, title):
        elapsed = int(time.monotonic() - self.started)
        minutes, seconds = divmod(elapsed, 60)
        bar = "Progress percentage is not available yet."
        if self.percent is not None:
            filled = int(self.percent / 10)
            bar = "[" + "#" * filled + "-" * (10 - filled) + f"] {self.percent:.1f}%"
        return f"{title}\n{self.stage}\n{bar}\nElapsed: {minutes:02d}:{seconds:02d}"
