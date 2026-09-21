"""Hidden acceptance tests for csvnorm. Every test pinned via PINS."""
from csvnorm import normalize_csv

PINS = {
    "test_c01_header_and_column_order": ["C01"],
    "test_c02_blank_lines_skipped": ["C02"],
    "test_c02_blank_before_header": ["C02"],
    "test_c03_bom_stripped": ["C03"],
    "test_c04_quoted_verbatim": ["C04"],
    "test_c04_unquoted_stripped": ["C04"],
    "test_c04_quote_not_first_char": ["C04"],
    "test_c05_row_and_column_order": ["C05"],
    "test_c06_quoted_comma": ["C06"],
    "test_c06_escaped_quotes": ["C06"],
    "test_c06_embedded_newline": ["C06"],
    "test_c07_no_trailing_newline": ["C07"],
    "test_c07_minimal_quoting": ["C07"],
    "test_c07_blank_input": ["C07"],
}


def test_c01_header_and_column_order():
    out = normalize_csv("b,a\n2,1\n")
    assert out.split("\n")[0] == "b,a"


def test_c02_blank_lines_skipped():
    out = normalize_csv("a,b\n1,2\n\n   \n3,4\n")
    assert out == "a,b\n1,2\n3,4"


def test_c02_blank_before_header():
    out = normalize_csv("\n  \na,b\n1,2\n")
    assert out.split("\n")[0] == "a,b"


def test_c03_bom_stripped():
    out = normalize_csv("\ufeffa,b\n1,2\n")
    assert out.split("\n")[0] == "a,b"
    assert "\ufeff" not in out


def test_c04_quoted_verbatim():
    # Inner content kept exactly (spaces preserved); re-quoted because the
    # content contains a comma (C07 minimal quoting).
    out = normalize_csv('a\n"  x,y  "\n')
    assert out == 'a\n"  x,y  "'


def test_c04_unquoted_stripped():
    out = normalize_csv("a\n  y  \n")
    assert out == "a\ny"


def test_c04_quote_not_first_char():
    # The quote is not the first character: not a quoted field, so the value
    # strips to `"z"` (quotes are literal content) and is then re-quoted.
    out = normalize_csv('a\n  "z"\n')
    assert out == 'a\n"""z"""'


def test_c05_row_and_column_order():
    out = normalize_csv("c,b,a\n3,2,1\n6,5,4\n")
    assert out == "c,b,a\n3,2,1\n6,5,4"


def test_c06_quoted_comma():
    out = normalize_csv('"a,b",c\n1,2\n')
    assert out == '"a,b",c\n1,2'


def test_c06_escaped_quotes():
    out = normalize_csv('a\n"b""c"\n')
    assert out == 'a\n"b""c"'


def test_c06_embedded_newline():
    out = normalize_csv('a,b\n"x\ny",2\n')
    assert out == 'a,b\n"x\ny",2'


def test_c07_no_trailing_newline():
    out = normalize_csv("a,b\n1,2\n")
    assert out == "a,b\n1,2"
    assert not out.endswith("\n")


def test_c07_minimal_quoting():
    out = normalize_csv("a,b\nplain,1\n")
    assert out == "a,b\nplain,1"  # no quotes added


def test_c07_blank_input():
    assert normalize_csv("") == ""
    assert normalize_csv("  \n \n") == ""
