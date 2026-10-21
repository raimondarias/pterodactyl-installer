"""Responsive terminal cards, menus, prompts and cancellable progress animation."""
import contextlib
import getpass
import os
import shutil
import sys
import textwrap
import threading
import time

from .i18n import Translator


class Literal(str):
    """Already-formatted user data: never translate credentials or addresses."""


class UI:
    def __init__(self, animate=True, language="en"):
        self.color = sys.stdout.isatty() and "NO_COLOR" not in os.environ
        self.animate = animate and self.color and os.environ.get("TERM") != "dumb"
        self.language = language
        self.tr = Translator(language)

    def set_language(self, language):
        self.language, self.tr = language, Translator(language)

    def paint(self, text, color="36"):
        return f"\033[{color}m{text}\033[0m" if self.color else text

    def say(self, text, kind="info"):
        colors = {"info": "36", "ok": "32", "warn": "33", "error": "31", "muted": "90"}
        print(self.paint(self.tr(str(text)), colors.get(kind, "36")), flush=True)

    def card(self, title, rows=(), subtitle=None):
        width = max(24, min(shutil.get_terminal_size((80, 24)).columns - 4, 78))
        print(self.paint("╭" + "─" * width + "╮", "36"))
        lines = [self.tr(title)]
        if subtitle:
            lines += [self.tr(subtitle)]
        lines += [str(row) if isinstance(row, Literal) else self.tr(str(row)) for row in rows]
        for line in lines:
            for part in textwrap.wrap(line, width - 4, replace_whitespace=False) or [""]:
                print(self.paint("│ ", "36") + part.ljust(width - 2) + self.paint(" │", "36"))
        print(self.paint("╰" + "─" * width + "╯", "36"), flush=True)

    def banner(self):
        self.card("P T E R O   /   I N S T A L L E R", [
            "Panel v2  ·  Wings  ·  Ubuntu / Debian",
            "Install. Configure. Maintain.",
        ], "A guided setup, from the first question to your first server.")

    def step(self, number, total, title):
        count = round(number / total * 20)
        self.say(f"[{number}/{total}] " + self.tr(title))
        self.say("  " + "━" * count + "─" * (20 - count), "muted")

    def ask(self, label, default=None, validator=None, secret=False):
        from .core import Cancelled
        while True:
            suffix = f" [{default}]" if default is not None and not secret else ""
            prompt = self.paint("  › ", "35") + self.tr(label) + suffix + ": "
            try:
                value = (getpass.getpass if secret else input)(prompt)
            except EOFError as exc:
                raise Cancelled("Input closed. The operation was not confirmed.") from exc
            if not secret:
                value = value.strip()
            if not value and default is not None:
                value = default
            if validator is None or validator(value):
                return value
            self.say("Invalid value. Please try again.", "warn")

    def yes(self, label, default=False):
        yes_letter = "y" if self.language == "en" else "s"
        default_value = yes_letter if default else "n"
        value = self.ask(self.tr(label) + f" ({yes_letter}/n)", default_value,
                         lambda s: s.lower() in ("y", "yes", "s", "si", "sí", "sim", "n", "no", "não", "nao"))
        return value.lower() in ("y", "yes", "s", "si", "sí", "sim")

    def confirm(self, phrase):
        from .core import Cancelled
        phrase = self.tr(phrase)
        prompt = self.tr("Type {phrase} to continue").format(phrase=phrase)
        if self.ask(prompt) != phrase:
            raise Cancelled("Operation cancelled.")

    def choice(self, title, options, default=0):
        """options = [(value, label, description), ...]. Keep numeric input accessible."""
        self.card(title, [f"{index}. {self.tr(label)}" +
                          (f" — {self.tr(note)}" if note else "")
                          for index, (_, label, note) in enumerate(options, 1)])
        answer = self.ask("Choose an option", str(default + 1),
                          lambda s: s.isdigit() and 1 <= int(s) <= len(options))
        return options[int(answer) - 1][0]

    @contextlib.contextmanager
    def busy(self, label):
        done = threading.Event()
        label = self.tr(label)
        def spin():
            frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
            started, index = time.monotonic(), 0
            while not done.wait(0.09):
                width = max(20, shutil.get_terminal_size((80, 24)).columns - 15)
                text = f"{frames[index % len(frames)]} {label[:width]}  {int(time.monotonic() - started)}s"
                print("\r\033[2K" + self.paint(text, "36"), end="", flush=True)
                index += 1
        thread = threading.Thread(target=spin, daemon=True) if self.animate else None
        if thread:
            thread.start()
        else:
            self.say("→ " + label)
        try:
            yield
        finally:
            done.set()
            if thread:
                thread.join()
                print("\r\033[2K", end="", flush=True)
