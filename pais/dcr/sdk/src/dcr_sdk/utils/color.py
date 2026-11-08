from __future__ import annotations

from typing import ClassVar


class Color:
    # ANSI escape codes for terminal output
    # This is just for visualization / debugging the simulations :)

    RESET: ClassVar[str] = "\033[0m"
    BOLD: ClassVar[str] = "\033[1m"
    DIM: ClassVar[str] = "\033[2m"

    RED: ClassVar[str] = "\033[31m"
    GREEN: ClassVar[str] = "\033[32m"
    YELLOW: ClassVar[str] = "\033[33m"
    BLUE: ClassVar[str] = "\033[34m"
    MAGENTA: ClassVar[str] = "\033[35m"
    CYAN: ClassVar[str] = "\033[36m"
    GREY: ClassVar[str] = "\033[90m"

    @staticmethod
    def paint(text: object, *styles: str) -> str:
        return f"{''.join(styles)}{text}{Color.RESET}"

    @classmethod
    def red(cls, text: object) -> str:
        return cls.paint(text, cls.RED)

    @classmethod
    def green(cls, text: object) -> str:
        return cls.paint(text, cls.GREEN)

    @classmethod
    def yellow(cls, text: object) -> str:
        return cls.paint(text, cls.YELLOW)

    @classmethod
    def blue(cls, text: object) -> str:
        return cls.paint(text, cls.BLUE)

    @classmethod
    def magenta(cls, text: object) -> str:
        return cls.paint(text, cls.MAGENTA)

    @classmethod
    def cyan(cls, text: object) -> str:
        return cls.paint(text, cls.CYAN)

    @classmethod
    def grey(cls, text: object) -> str:
        return cls.paint(text, cls.GREY)

    @classmethod
    def bold(cls, text: object) -> str:
        return cls.paint(text, cls.BOLD)

    @classmethod
    def flag(cls, value: bool) -> str:
        return cls.green(value) if value else cls.red(value)

    @classmethod
    def header(cls, text: str) -> str:
        return cls.paint(f"\n==== {text} ====\n", cls.BOLD, cls.MAGENTA)
