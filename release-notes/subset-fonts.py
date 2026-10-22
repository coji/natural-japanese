# /// script
# requires-python = ">=3.10"
# dependencies = ["fonttools", "brotli"]
# ///
"""ページで使う文字だけを含む woff2 を release-notes/fonts/ に書き出す。

本文を書き換えたら、もう一度実行する。元の TTF は google/fonts から取って ~/.cache に置く。
  uv run release-notes/subset-fonts.py release-notes/index.html
"""
import html
import re
import sys
import urllib.request
from pathlib import Path

from fontTools import subset

SRC = "https://github.com/google/fonts/raw/main/ofl/"
FONTS = {
    "seed-400": "lineseedjp/LINESeedJP-Regular.ttf",
    "seed-700": "lineseedjp/LINESeedJP-Bold.ttf",
    "seed-800": "lineseedjp/LINESeedJP-ExtraBold.ttf",
    "mono-400": "jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf",
}
CACHE = Path.home() / ".cache" / "natural-japanese-fonts"


def page_text(path: Path) -> str:
    src = path.read_text(encoding="utf-8")
    src = re.sub(r"<(style|script)\b.*?</\1>", "", src, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", "", src))
    # 表から開く相談文の文字も入れる
    docs = path.parent / "data" / "docs.json"
    if docs.exists():
        text += docs.read_text(encoding="utf-8")
    # 版を足しても欠けにくいよう、ASCII と約物はいつも入れる
    return text + "".join(chr(c) for c in range(0x20, 0x7F)) + "、。・「」『』()()〜→⇒…—―"


def main() -> None:
    page = Path(sys.argv[1])
    out = page.parent / "fonts"
    out.mkdir(exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    text = page_text(page)
    for name, rel in FONTS.items():
        ttf = CACHE / Path(rel).name.replace("%5B", "[").replace("%5D", "]")
        if not ttf.exists():
            urllib.request.urlretrieve(SRC + rel, ttf)
        opts = subset.Options()
        opts.flavor = "woff2"
        opts.layout_features = ["*"]
        font = subset.load_font(str(ttf), opts)
        sub = subset.Subsetter(opts)
        sub.populate(text=text)
        sub.subset(font)
        dest = out / f"{name}.woff2"
        subset.save_font(font, str(dest), opts)
        print(f"{dest}  {dest.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
