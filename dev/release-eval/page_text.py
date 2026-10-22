"""リリースノートの HTML から、本文の文字だけを1要素1行で取り出す。lint と、流れを知らない AI に読ませるときに使う。
  python3 dev/release-eval/page_text.py release-notes/index.html > /tmp/page.txt"""
import html
import re
import sys

src = open(sys.argv[1], encoding="utf-8").read()
src = re.sub(r"<(style|script)\b.*?</\1>", "", src, flags=re.S)
src = re.sub(r"</(p|li|h1|h2|h3|div|tr|th|td|strong|a)>", "\n", src)
text = html.unescape(re.sub(r"<[^>]+>", "", src))
print("\n".join(line.strip() for line in text.splitlines() if line.strip()))
