# -*- coding: utf-8 -*-
"""Готовит конспект к публикации на сайте.

Берёт свёрстанную страницу конспекта и делает из неё две вещи:

  lectures/имя.html — одним файлом: картинки вшиты внутрь, поэтому страница
                      открывается с диска и без интернета;
  lectures/имя.pdf  — то же самое, разбитое по страницам, для скачивания.

Страница всегда светлая: конспект читают как лист бумаги, тёмная тема тут
только мешает. На экране текст разложен по листам A4 с номерами страниц —
ровно так же, как он ляжет в PDF и на печать.

Запуск:

    python build_lecture.py "путь/к/конспекту.html" lectures/statmodel.html

PDF собирается тем же Chrome, что стоит в системе. Если его нет, HTML всё
равно будет готов, а PDF можно сделать из браузера: Печать → Сохранить в PDF.
"""

import base64
import io
import os
import re
import subprocess
import sys

try:
    from PIL import Image
except ImportError:
    Image = None

SITE = "https://lockerbig007.github.io/rea-board"

# Фотографии слайдов снимают на телефон, они приходят на несколько мегабайт.
# Тысячи точек по длинной стороне хватает, чтобы читался текст на слайде.
MAX_IMAGE_SIDE = 1000
JPEG_QUALITY = 72

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

PAGE_CSS = """
<style>
/* Лист бумаги вместо бесконечной ленты: конспект читается как документ. */
body{background:#e5e8e4}
.sitebar{display:flex;gap:16px;flex-wrap:wrap;align-items:center;
  max-width:794px;margin:0 auto;padding:14px 16px 10px;
  font-family:var(--sans);font-size:13px}
.sitebar a{color:var(--muted);text-decoration:none}
.sitebar a:hover{color:var(--accent)}
.sitebar .get{margin-left:auto;color:var(--accent);font-weight:500}

.wrap.paged{max-width:none;padding:0}
.pages{display:flex;flex-direction:column;align-items:center;gap:20px;padding-bottom:40px}
.page{position:relative;width:794px;height:1122px;padding:60px 60px 72px;
  background:var(--surface);border-radius:2px;
  box-shadow:0 1px 3px rgba(24,29,28,.16),0 12px 30px rgba(24,29,28,.10)}
.page.tall{height:auto;padding-bottom:72px}
.page-num{position:absolute;left:0;right:0;bottom:26px;text-align:center;
  font-family:var(--sans);font-size:11px;color:var(--muted)}
.page > .page-body > :first-child{margin-top:0}

/* На телефоне листы A4 нечитаемы — там обычная лента. */
@media (max-width:899px){
  body{background:var(--bg)}
  .pages{gap:0;padding-bottom:0}
  .page{width:auto;height:auto;padding:18px 16px;box-shadow:none;border-radius:0}
  .page-num{display:none}
  .sitebar{max-width:none}
}

@media print{
  @page{size:A4;margin:0}
  body{background:#fff}
  .sitebar{display:none}
  .pages{gap:0;padding:0}
  .page{width:210mm;height:auto;min-height:0;padding:16mm 16mm 18mm;
    box-shadow:none;border-radius:0;break-after:page}
  .page:last-child{break-after:auto}
}
</style>
"""

PAGE_JS = """
<script>
(function () {
  "use strict";

  // Лист A4 при 96 точках на дюйм — 1122 точки. В MAX_H заложен запас: без
  // него лист, набитый под завязку, выдавливает в PDF лишнюю пустую страницу.
  var MAX_H = 950;
  var MIN_WIDTH = 900;

  var wrap = document.querySelector(".wrap");
  if (!wrap) return;
  var original = Array.prototype.slice.call(wrap.children);

  // Лекция, не поместившаяся на лист, продолжается на следующем такой же
  // оболочкой <section>: без неё поехали бы отступы и стили заголовков.
  function unpage() {
    var pages = wrap.querySelector(".pages");
    if (!pages) return;
    original.forEach(function (el) {
      if (el.shells) {
        el.shells.forEach(function (shell) {
          while (shell.firstChild) el.appendChild(shell.firstChild);
        });
        el.shells = null;
      }
      wrap.appendChild(el);
    });
    pages.remove();
    wrap.classList.remove("paged");
  }

  function paginate() {
    unpage();
    if (document.documentElement.clientWidth < MIN_WIDTH) return;

    var pages = document.createElement("div");
    pages.className = "pages";
    wrap.classList.add("paged");
    wrap.appendChild(pages);

    var body = null;

    function newPage() {
      var page = document.createElement("div");
      page.className = "page";
      body = document.createElement("div");
      body.className = "page-body";
      page.appendChild(body);
      pages.appendChild(page);
      return body;
    }

    function overflows() { return body.scrollHeight > MAX_H; }

    newPage();

    original.forEach(function (el) {
      if (el.tagName !== "SECTION") {
        body.appendChild(el);
        if (overflows() && body.children.length > 1) {
          body.removeChild(el);
          newPage();
          body.appendChild(el);
        }
        return;
      }

      // Каждая лекция начинается с нового листа, как глава в книге.
      if (body.children.length) newPage();

      var shells = [];
      el.shells = shells;

      function addShell(first) {
        var shell = el.cloneNode(false);
        if (!first) shell.removeAttribute("id");  // якорь — на первом листе лекции
        shell.owner = el;
        shells.push(shell);
        return shell;
      }

      var shell = addShell(true);
      body.appendChild(shell);

      Array.prototype.slice.call(el.children).forEach(function (block) {
        shell.appendChild(block);
        if (!overflows()) return;
        if (shell.children.length === 1) return; // блок сам выше листа — пусть будет
        shell.removeChild(block);
        shell = addShell(false);
        newPage().appendChild(shell);
        shell.appendChild(block);
      });

      el.remove(); // опустевшая исходная секция, иначе торчит пустой полосой
    });

    // Заголовок, оставшийся внизу листа без текста под ним, переносим дальше —
    // но только внутри своей лекции, иначе он уедет в чужую.
    Array.prototype.slice.call(pages.children).forEach(function (page, i, all) {
      if (i === all.length - 1) return;
      var host = page.querySelector(".page-body > section");
      var next = all[i + 1].querySelector(".page-body > section");
      if (!host || !next || host.owner !== next.owner) return;
      var last = host.lastElementChild;
      if (!last || !/^H[23]$/.test(last.tagName) || host.children.length < 2) return;
      next.insertBefore(last, next.firstChild);
    });

    Array.prototype.slice.call(pages.children).forEach(function (page, i) {
      if (page.firstChild.scrollHeight > MAX_H) page.classList.add("tall");
      var num = document.createElement("div");
      num.className = "page-num";
      num.textContent = i + 1;
      page.appendChild(num);
    });
  }

  function run() {
    // Шрифты меняют высоту текста, поэтому раскладываем после их загрузки.
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(paginate);
    else paginate();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run);
  else run();

  var t;
  window.addEventListener("resize", function () {
    clearTimeout(t);
    t = setTimeout(paginate, 250);
  });
})();
</script>
"""


def inline_images(html, base_dir):
    """Заменяет ссылки на картинки их содержимым, попутно ужимая."""
    def repl(m):
        src = m.group(1)
        if src.startswith(("data:", "http:", "https:", "//")):
            return m.group(0)
        path = os.path.join(base_dir, src.replace("/", os.sep))
        if not os.path.exists(path):
            print("  ! картинка не найдена:", src)
            return m.group(0)
        before = os.path.getsize(path)
        if Image is None:
            data = io.open(path, "rb").read()
            mime = "image/png" if path.lower().endswith(".png") else "image/jpeg"
        else:
            img = Image.open(path).convert("RGB")
            img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
            data = buf.getvalue()
            mime = "image/jpeg"
        print("  %-28s %5d KB -> %4d KB" % (src, before / 1024, len(data) / 1024))
        return 'src="data:%s;base64,%s"' % (mime, base64.b64encode(data).decode())

    return re.sub(r'src="([^"]+)"', repl, html)


def head_tags(title, page_name):
    """Значок во вкладке и картинка, которую покажет Телеграм на ссылку.

    Адреса абсолютные: файл скачивают и открывают с диска, относительные пути
    там вести будет некуда.
    """
    return (
        '<link rel="icon" href="%s/icon.svg" type="image/svg+xml">\n'
        '<link rel="apple-touch-icon" href="%s/icon-180.png">\n'
        '<meta property="og:type" content="article">\n'
        '<meta property="og:site_name" content="Борд 15.27Д">\n'
        '<meta property="og:title" content="%s">\n'
        '<meta property="og:image" content="%s/preview.png">\n'
        '<meta property="og:image:width" content="1200">\n'
        '<meta property="og:image:height" content="630">\n'
        '<meta property="og:url" content="%s/lectures/%s">\n'
        '<meta name="twitter:card" content="summary_large_image">\n'
        % (SITE, SITE, title.replace('"', "&quot;"), SITE, SITE, page_name)
    )


def sitebar(pdf_name):
    return (
        '<nav class="sitebar">\n'
        '  <a href="%s/">Борд 15.27Д</a>\n'
        '  <a href="%s/lectures.html">Все лекции</a>\n'
        '  <a class="get" href="%s/lectures/%s" download>Скачать PDF</a>\n'
        "</nav>\n" % (SITE, SITE, SITE, pdf_name)
    )


def make_pdf(html_path, pdf_path):
    chrome = next((p for p in CHROME_CANDIDATES if os.path.exists(p)), None)
    if not chrome:
        print("Chrome не найден — PDF не собран. Сделайте из браузера: Печать → Сохранить в PDF.")
        return False
    url = "file:///" + os.path.abspath(html_path).replace("\\", "/")
    cmd = [
        chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
        "--window-size=1200,1600",
        "--virtual-time-budget=20000",
        "--no-pdf-header-footer",
        "--print-to-pdf=" + os.path.abspath(pdf_path),
        url,
    ]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0 or not os.path.exists(pdf_path):
        print("Chrome вернул ошибку:", r.stderr.decode("utf-8", "replace")[:400])
        return False
    return True


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    src, dst = sys.argv[1], sys.argv[2]
    base_dir = os.path.dirname(os.path.abspath(src))

    html = io.open(src, encoding="utf-8").read()
    if "<body" not in html:
        print("Это не целая страница, а только её тело: нет <body>. "
              "Нужен файл с <!doctype html> и <head>.")
        return 1

    print("Картинки:")
    html = inline_images(html, base_dir)

    # Светлая тема принудительно: вёрстка конспекта её поддерживает.
    html = re.sub(r"<html\b([^>]*)>", r'<html\1 data-theme="light">', html, count=1)

    pdf_name = os.path.splitext(os.path.basename(dst))[0] + ".pdf"

    m = re.search(r"<title>(.*?)</title>", html, re.S)
    if m:
        html = (html[:m.end()] + "\n"
                + head_tags(m.group(1).strip(), os.path.basename(dst))
                + html[m.end():])

    html = html.replace("<body>", "<body>\n" + sitebar(pdf_name), 1)
    html = html.replace("</body>", PAGE_CSS + PAGE_JS + "</body>", 1)

    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    io.open(dst, "w", encoding="utf-8", newline="\n").write(html)
    print("HTML: %s — %d KB" % (dst, os.path.getsize(dst) / 1024))

    pdf_path = os.path.join(os.path.dirname(dst), pdf_name)
    if make_pdf(dst, pdf_path):
        print("PDF:  %s — %d KB" % (pdf_path, os.path.getsize(pdf_path) / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
