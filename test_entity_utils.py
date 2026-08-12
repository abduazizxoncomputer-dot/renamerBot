from aiogram.types import MessageEntity

from entity_utils import replace_preserving_entities


def utf16_offset(text, substr):
    idx = text.index(substr)
    return len(text[:idx].encode("utf-16-le")) // 2, len(substr.encode("utf-16-le")) // 2


def chunk_of(text, entity):
    b = text.encode("utf-16-le")
    return b[entity.offset * 2 : (entity.offset + entity.length) * 2].decode("utf-16-le")


# Case 1: real-world style caption, replacing space with a dot, bold + text_link preserved
caption = (
    "SUICIDE SQUAD 2016 \U0001F3AC \U0001F3AD\n\n"
    "Telegram bot to order \U0001F916\n"
    "@orderMovies_bot\n\n"
    "ORDERED MOVIES \U0001F3AC\U0001F39E"
)
bold_off, bold_len = utf16_offset(caption, "SUICIDE SQUAD 2016")
link_off, link_len = utf16_offset(caption, "ORDERED MOVIES")
entities = [
    MessageEntity(type="bold", offset=bold_off, length=bold_len),
    MessageEntity(type="text_link", offset=link_off, length=link_len, url="http://t.me/Cart_In_Eng"),
]
assert chunk_of(caption, entities[0]) == "SUICIDE SQUAD 2016"
assert chunk_of(caption, entities[1]) == "ORDERED MOVIES"

new_text, new_entities = replace_preserving_entities(caption, entities, " ", ".")
assert new_text == caption.replace(" ", ".")
assert chunk_of(new_text, new_entities[0]) == "SUICIDE.SQUAD.2016"
assert chunk_of(new_text, new_entities[1]) == "ORDERED.MOVIES"
assert new_entities[1].url == "http://t.me/Cart_In_Eng"
print("case1 OK ->", repr(new_text))

# Case 2: filename-style replace, "U" -> "m" (no entities)
fname = "Suicide.Squad.2016.720p.BluRay.x264-[YTS.AG].mp4"
new_fname, _ = replace_preserving_entities(fname, None, "U", "m")
assert new_fname == fname.replace("U", "m")
print("case2 OK ->", new_fname)

# Case 3: replacement lands inside link display text, url stays untouched, length changes
text3 = "Bold word and a [ORDERED MOVIES] link tail"
b_off, b_len = utf16_offset(text3, "Bold")
l_off, l_len = utf16_offset(text3, "ORDERED MOVIES")
ent3 = [
    MessageEntity(type="bold", offset=b_off, length=b_len),
    MessageEntity(type="text_link", offset=l_off, length=l_len, url="http://t.me/Cart_In_Eng"),
]
nt3, ne3 = replace_preserving_entities(text3, ent3, "O", "00")
assert nt3 == text3.replace("O", "00")
assert ne3[1].url == "http://t.me/Cart_In_Eng"
assert chunk_of(nt3, ne3[1]) == "00RDERED M00VIES"
print("case3 OK ->", repr(nt3), "link text:", repr(chunk_of(nt3, ne3[1])))

# Case 4: entity fully deleted (replacement empties it out) is dropped, not left as zero-length
text4 = "prefix XX suffix"
e_off, e_len = utf16_offset(text4, "XX")
ent4 = [MessageEntity(type="bold", offset=e_off, length=e_len)]
nt4, ne4 = replace_preserving_entities(text4, ent4, "XX", "")
assert nt4 == "prefix  suffix"
assert ne4 == []
print("case4 OK ->", repr(nt4), ne4)

print("ALL TESTS PASSED")
