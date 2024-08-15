from dataclasses import dataclass
from enum import Enum
import re
from lsprotocol.types import Position
from pygls.workspace.text_document import TextDocument

STRING_CHARS = "'\""
BRACKET_CHARS = "<>"
PROPS_RE = re.compile(r"""(:?)\w+=(["'])\w*\2""")
INCOMLETE_PROG_PROPS_RE = re.compile(r""":\w+=["'](.*)""")


class TokenType(Enum):
    IDENT = 1
    PROPS = 2
    PROG_PROPS = 3
    BRACKET = 4


class ParseState(Enum):
    NONE = 0
    STRING = 1
    IDENT = 2
    END = 3


@dataclass
class SuggestProps:
    component: str
    cursor: str


@dataclass
class SuggestComponent:
    cursor: str


@dataclass
class SuggestPython:
    cursor: str


@dataclass
class Token:
    type: TokenType
    value: str
    line: int
    column: int

    @property
    def length(self):
        return len(self.value)

    @property
    def finalized(self):
        return self.value.endswith(" ")


LSPAction = SuggestProps | SuggestComponent | SuggestPython | None


class Tokenizer:
    def __init__(
        self, document: TextDocument, position: Position, cursor_position: Position
    ):
        self.document = document
        self.position = position
        self.max_position = cursor_position

    def __iter__(self):
        return self

    def __next__(self) -> Token:
        start_line = self.position.line
        start_col = self.position.character

        buf = ""
        state = ParseState.NONE

        while self.position.line < len(self.document.lines) and state != ParseState.END:
            if self.position >= self.max_position:
                state = ParseState.END
                continue

            current_line = self.document.lines[self.position.line]

            if (
                self.position.character >= len(current_line)
                or current_line[self.position.character] == "\n"
            ):
                self.position.line += 1
                self.position.character = 0
                if buf:
                    state = ParseState.END
                else:
                    start_line = self.position.line
                    start_col = 0
                continue

            current_char = current_line[self.position.character]
            if buf and current_char in BRACKET_CHARS and state != ParseState.STRING:
                state = ParseState.END
                continue

            buf += current_char
            if state != ParseState.STRING:
                if current_char in BRACKET_CHARS:
                    state = ParseState.END
                else:
                    state = ParseState.IDENT

            if current_char in STRING_CHARS:
                if state == ParseState.STRING:
                    state = ParseState.END
                else:
                    state = ParseState.STRING

            if current_char == " ":
                state = ParseState.END

            if state != ParseState.NONE:
                self.position.character += 1

        # NOTE: buf includes the ending space!!
        if buf == "":
            raise StopIteration()

        if buf in ("<", ">"):
            return Token(TokenType.BRACKET, buf, start_line, start_col)

        if result := PROPS_RE.match(buf):
            if result.group(1) == ":":
                return Token(TokenType.PROG_PROPS, buf, start_line, start_col)
            return Token(TokenType.PROPS, buf, start_line, start_col)

        return Token(TokenType.IDENT, buf, start_line, start_col)


# TODO: In the future, we'll change this to string start
MAGIC = "<!-- liku -->"


def find_liku_areas(document: TextDocument):
    start = -1
    end = -1

    while True:
        start = end + 1
        while start < len(document.lines):
            if MAGIC in document.lines[start]:
                break

            start += 1
        else:
            return

        end = start + 1
        while end < len(document.lines):
            if MAGIC in document.lines[end]:
                break

            end += 1
        else:
            return

        yield (start, end)


def action_at_cursor(document: TextDocument, position: Position) -> LSPAction:
    start_line = position.line
    while start_line >= 0:
        if MAGIC in document.lines[start_line]:
            break

        start_line -= 1

    if start_line == -1:
        return None

    start_column = document.lines[start_line].find(MAGIC) + len(MAGIC)
    tokenizer = Tokenizer(document, Position(start_line, start_column), position)

    is_inside_tag = False
    component_token: Token | None = None
    last_token: Token | None = None

    for token in tokenizer:
        if is_inside_tag and token.type == TokenType.BRACKET and token.value == ">":
            is_inside_tag = False
            component_token = None
        elif (
            not is_inside_tag and token.type == TokenType.BRACKET and token.value == "<"
        ):
            is_inside_tag = True

        if token.type == TokenType.BRACKET and token.value == "<":
            try:
                # This must be the component name
                component_token = next(tokenizer)

                if component_token.finalized:
                    last_token = component_token
                else:
                    last_token = token
                continue
            except StopIteration:
                pass

        last_token = token

    if not is_inside_tag:
        return

    if last_token and component_token:
        if last_token.type == TokenType.IDENT:
            if match := INCOMLETE_PROG_PROPS_RE.match(last_token.value):
                return SuggestPython(match.group(1) or "")

            return SuggestProps(
                component_token.value.strip(),
                "" if last_token.value.endswith(" ") else last_token.value,
            )
        if last_token.type in (TokenType.PROPS, TokenType.PROG_PROPS):
            return SuggestProps(component_token.value.strip(), "")

    # TODO: need to suggest closing bracket based on stack
    if component_token and not component_token.value.endswith(" "):
        return SuggestComponent(component_token.value)

    if not component_token or (last_token and last_token.value == "<"):
        return SuggestComponent("")
