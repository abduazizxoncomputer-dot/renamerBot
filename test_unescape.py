from bot import unescape, escape_for_display

assert unescape("\\b") == "\x08", repr(unescape("\\b"))
assert unescape("\\n") == "\n"
assert unescape("a\\bc") == "a\x08c"
assert unescape("\\x41") == "A"
assert unescape("\\u0008") == "\x08"
assert unescape("\\q") == "\\q"
assert unescape("salom") == "salom"
assert escape_for_display("\x08") == "\\b"
assert escape_for_display("salom dunyo") == "salom dunyo"
print("unescape helper OK")
