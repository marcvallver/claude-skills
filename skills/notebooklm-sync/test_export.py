#!/usr/bin/env python3
"""Tests de notebooklm-sync. Unit (sin dependencias) + integración (requiere pandoc + typst).

    python3 test_export.py
"""
import importlib.util, os, sys, json, time, tempfile, shutil, subprocess

HERE = os.path.dirname(os.path.realpath(__file__))
spec = importlib.util.spec_from_file_location("exp", os.path.join(HERE, "export.py"))
exp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exp)

ok = 0
fail = 0


def chk(cond, msg):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  FAIL: {msg}")


def touch(base, *parts, body="x"):
    p = os.path.join(base, *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w", encoding="utf-8").write(body)
    return p


# --------------------------------------------------------------- config / merge
d = exp.deep_merge(exp.DEFAULTS, {"layout": {"nuevos": "Pendientes"}, "base": "/x"})
chk(d["layout"]["nuevos"] == "Pendientes", "deep_merge sobreescribe hoja anidada")
chk(d["layout"]["externos"] == "Externos", "deep_merge conserva hermanas no tocadas")
chk(d["base"] == "/x", "deep_merge top-level")
chk(exp.DEFAULTS["layout"]["nuevos"] == "Nuevos", "deep_merge no muta DEFAULTS")

cfg, _ = exp.load_config(None)            # sin fichero → defaults (asumiendo que no hay cwd config)
chk(isinstance(cfg.get("sources"), list), "load_config sin fichero → defaults")

ef = exp.resolve_ext_fmt(exp.deep_merge(exp.DEFAULTS, {"conversion": {"formatOverrides": {".txt": "gfm"}}}))
chk(ef[".txt"] == "gfm", "formatOverrides aplicado")
ef2 = exp.resolve_ext_fmt(exp.deep_merge(exp.DEFAULTS, {"files": {"convertExtensions": [".md"]}}))
chk(set(ef2) == {".md"}, "convertExtensions filtra el mapa")

# --------------------------------------------------------------- sanitize
chk(exp.sanitize('a:b?c*"<>|.pdf') == "abc.pdf", f"sanitize reservados Windows → {exp.sanitize(chr(34)+'a:b?.pdf')}")
chk(exp.sanitize("a/b\\c.pdf") == "a-b-c.pdf", "sanitize / y \\ → -")
chk(exp.sanitize("CON.pdf") == "_CON.pdf", "sanitize nombre de dispositivo reservado")
chk(exp.sanitize("trailing... .pdf").startswith("trailing"), "sanitize recorta puntos/espacios finales")
chk(exp.sanitize("\x00\x01.pdf") == "documento.pdf", "sanitize control chars → fallback")
chk(len(exp.sanitize("z" * 300 + ".pdf")) <= 155, "sanitize acota longitud")
chk(exp.sanitize_component("a:b/c") == "ab-c", f"sanitize_component (':' se elimina, '/'→'-') → {exp.sanitize_component('a:b/c')}")

# --------------------------------------------------------------- sha256_source: EOL-agnóstico solo para texto
_eol = tempfile.mkdtemp()
_lf, _crlf = os.path.join(_eol, "lf.md"), os.path.join(_eol, "crlf.md")
open(_lf, "wb").write(b"# T\n\na\nb\n")
open(_crlf, "wb").write(b"# T\r\n\r\na\r\nb\r\n")
chk(exp.sha256_source(_lf, "gfm") == exp.sha256_source(_crlf, "gfm"), "sha256_source(texto): CRLF y LF → MISMO hash (portable cross-plataforma)")
chk(exp.sha256_source(_lf, "docx") != exp.sha256_source(_crlf, "docx"), "sha256_source(binario docx): NO normaliza, bytes crudos")
chk(exp.sha256_source(_lf, None) == exp.sha256_file(_lf), "sha256_source(None) == sha256_file (copia directa, crudo)")
chk(exp.sha256_source(_lf, "gfm") == exp.sha256_file(_lf), "sha256_source(LF, texto) == sha256_file(LF) (normalizado = LF)")
shutil.rmtree(_eol, ignore_errors=True)
chk(exp.bump("Externo - X.pdf", 2, ".pdf") == "Externo - X (2).pdf", "bump inserta sufijo antes de ext")

# --------------------------------------------------------------- title helpers
root = tempfile.mkdtemp()
touch(root, "docs", "con-h1.md", body="# Título Real\n\ncuerpo")
touch(root, "docs", "sin-h1-aqui.md", body="cuerpo sin encabezado")
chk(exp.title_for(os.path.join(root, "docs", "con-h1.md"), "h1") == "Título Real", "title_for h1")
chk(exp.title_for(os.path.join(root, "docs", "con-h1.md"), "filename") == "Con h1", "title_for filename ignora h1")
chk(exp.title_for(os.path.join(root, "docs", "sin-h1-aqui.md"), "h1") == "Sin h1 aqui", "title_for fallback de-kebabiza")

# --------------------------------------------------------------- build_plan
touch(root, "docs", "decisions", "0001-primera.md", body="# La primera decisión")
touch(root, "src", "ya.pdf")                       # fuente .pdf → copiar
touch(root, "docs", "imagen.png")                  # no convertible → ignorar en sources
sources = [
    {"glob": "docs/decisions/*.md", "label": "ADR", "title": "h1", "priority": "alta"},
    {"glob": "docs/**/*.md", "label": "", "title": "h1"},
    {"glob": "src/*.pdf", "label": "Bin"},
]
plan = exp.build_plan(sources, root, exp.EXT_FMT, ".pdf")
names = {n for _s, n, _f, _p in plan}
chk("ADR - La primera decisión.pdf" in names, f"build_plan label+h1 → {names}")
chk("Título Real.pdf" in names, "build_plan sin label usa h1")
chk(not any("0001-primera" in n for n in names if n.startswith("Título") is False and "ADR" not in n),
    "build_plan: una fuente captada por regla previa no se repite")
pdf_rule = [(s, n, f, pr) for s, n, f, pr in plan if n.startswith("Bin -")]
chk(pdf_rule and pdf_rule[0][2] is None, "build_plan .pdf source → from_fmt None (copiar)")
adr = [(s, n, f, pr) for s, n, f, pr in plan if n.startswith("ADR -")][0]
chk(adr[3] == "alta", "build_plan propaga priority")
chk(not any("imagen" in n.lower() for n in names), "build_plan ignora no convertible")
chk(all(n.endswith(".pdf") for n in names), "build_plan respeta out_ext")

# out_ext distinto
plan_html = exp.build_plan([{"glob": "docs/decisions/*.md", "label": "ADR"}], root, exp.EXT_FMT, ".html")
chk(plan_html and plan_html[0][1].endswith(".html"), "build_plan respeta outputExtension != pdf")

# --------------------------------------------------------------- scan_externos
d2 = tempfile.mkdtemp()
ext = os.path.join(d2, "Externos")
nuevos = os.path.join(d2, "Nuevos")
os.makedirs(nuevos)
touch(ext, "top.pdf")
touch(ext, "note.md")
touch(ext, ".hidden.pdf")
touch(ext, "Sub", "a.pdf")
touch(ext, "Sub", "b.docx")
touch(ext, "Sub", ".DS_Store")
touch(ext, "Sub", "deep", "c.pdf")
touch(ext, "ConSkip", "data.xlsx")
touch(ext, "ConSkip", ".secret")          # dotfile no-junk en carpeta que se conservará
touch(ext, "_originales", "archived.docx")

scan = exp.scan_externos(ext, nuevos, set(), exp.EXT_FMT, ".pdf", "_originales", False, set())
by_rel = {os.path.relpath(p, ext).replace(os.sep, "/"): (dest, kind) for p, dest, kind, _ in scan}
chk("top.pdf" in by_rel and by_rel["top.pdf"][1] == "pdf", "scan top pdf")
chk("note.md" in by_rel and by_rel["note.md"][1] == "convert", "scan md convert")
chk("Sub/a.pdf" in by_rel, "scan recursión subcarpeta")
chk("Sub/deep/c.pdf" in by_rel, "scan recursión anidada")
chk(by_rel.get("ConSkip/data.xlsx", (None, None))[1] == "skip", "scan xlsx skip")
chk(".hidden.pdf" not in by_rel, "scan ignora oculto")
chk(not any("_originales" in r for r in by_rel), "scan ignora _originales")
chk(all("/" not in dest for _p, dest, kind, _ in scan if kind != "skip"), "flatten: destinos planos")

# preserveSubdirs
scan_p = exp.scan_externos(ext, nuevos, set(), exp.EXT_FMT, ".pdf", "_originales", True, set())
dests_p = {os.path.relpath(p, ext).replace(os.sep, "/"): dest for p, dest, kind, _ in scan_p if kind != "skip"}
chk(dests_p.get("Sub/a.pdf") == "Sub/Externo - A.pdf", f"preserveSubdirs conserva subruta → {dests_p.get('Sub/a.pdf')}")
chk(dests_p.get("Sub/deep/c.pdf") == "Sub/deep/Externo - C.pdf", "preserveSubdirs anidado")

# anticolisión: dos ficheros que de-kebabizan al mismo nombre, aplanados
d3 = tempfile.mkdtemp()
ext3 = os.path.join(d3, "Externos")
nuevos3 = os.path.join(d3, "Nuevos")
os.makedirs(nuevos3)
touch(ext3, "s1", "Tres-pilares.pdf")
touch(ext3, "s2", "Tres pilares.pdf")
scan3 = exp.scan_externos(ext3, nuevos3, set(), exp.EXT_FMT, ".pdf", "_originales", False, set())
dests3 = sorted(dest for _p, dest, _k, _f in scan3)
chk(len(dests3) == len(set(dests3)), f"anticolisión: destinos únicos → {dests3}")
chk(any("(2)" in d for d in dests3), "anticolisión: sufijo aplicado")
# anticolisión contra existing (nombre ya en base/Nuevos)
scan3b = exp.scan_externos(ext3, nuevos3, {"Externo - Tres pilares.pdf"}, exp.EXT_FMT, ".pdf", "_originales", False, set())
chk(all(d != "Externo - Tres pilares.pdf" for _p, d, _k, _f in scan3b), "anticolisión vs existing")

# dedup del buzón por contenido (fix: copy idempotente). Marca dup si (basename, sha) ya procesado.
sha_top = exp.sha256_file(os.path.join(ext, "top.pdf"))
scan_dup = exp.scan_externos(ext, nuevos, set(), exp.EXT_FMT, ".pdf", "_originales", False, {("top.pdf", sha_top)})
kinds_top = [k for p, _d, k, _f in scan_dup if os.path.basename(p) == "top.pdf"]
chk(kinds_top == ["dup"], f"dedup: fichero ya procesado (mismo sha) → dup → {kinds_top}")
# mismo nombre pero distinto contenido NO es dup
scan_nodup = exp.scan_externos(ext, nuevos, set(), exp.EXT_FMT, ".pdf", "_originales", False, {("top.pdf", "otrohash")})
kinds_top2 = [k for p, _d, k, _f in scan_nodup if os.path.basename(p) == "top.pdf"]
chk(kinds_top2 == ["pdf"], "dedup: mismo nombre, sha distinto → NO dup")

# build_plan: dos fuentes que colapsan al mismo nombre → anticolisión por nombre (no se pisan)
droot = tempfile.mkdtemp()
touch(droot, "a", "README.md", body="sin h1")        # → "Readme.pdf"
touch(droot, "b", "README.md", body="sin h1")         # → colisiona → "Readme (2).pdf"
plan_col = exp.build_plan([{"glob": "**/README.md", "title": "filename"}], droot, exp.EXT_FMT, ".pdf")
col_names = sorted(n for _s, n, _f, _p in plan_col)
chk(len(plan_col) == 2, f"build_plan: ambas fuentes presentes (no pérdida silenciosa) → {col_names}")
chk(len(set(col_names)) == 2 and any("(2)" in n for n in col_names), f"build_plan: anticolisión por nombre → {col_names}")
shutil.rmtree(droot, ignore_errors=True)

# --------------------------------------------------------------- lock de concurrencia
lkd = tempfile.mkdtemp()
lp = exp.acquire_lock(lkd, ".t.lock")
chk(os.path.isfile(lp), "lock: se crea en la base")
chk(json.load(open(lp, encoding="utf-8")).get("host"), "lock: lleva el host titular")
try:
    exp.acquire_lock(lkd, ".t.lock")
    chk(False, "lock: uno fresco debería abortar la segunda corrida")
except SystemExit as e:
    chk("otra corrida" in str(e), f"lock: aborta explicando el titular → {e}")
old = time.time() - exp.LOCK_STALE_SECONDS - 60
os.utime(lp, (old, old))
lp2 = exp.acquire_lock(lkd, ".t.lock")          # huérfano → se reemplaza
chk(os.path.isfile(lp2) and time.time() - os.path.getmtime(lp2) < 60,
    "lock: huérfano (mtime viejo) se reemplaza (mtime vuelve a ser fresco)")
exp.release_lock(lp2)
chk(not os.path.exists(lp2), "lock: release lo elimina")
exp.release_lock(lp2)                           # idempotente: no peta si ya no existe
chk(True, "lock: release idempotente")
# lock ILEGIBLE (0 bytes = corrida muerta entre el O_EXCL y el dump): la EDAD decide igualmente
open(lp, "w", encoding="utf-8").close()
os.utime(lp, (old, old))
lp3 = exp.acquire_lock(lkd, ".t.lock")          # vacío + viejo → también se recupera
chk(json.load(open(lp3, encoding="utf-8")).get("pid") == os.getpid(),
    "lock: huérfano ILEGIBLE (0 bytes, viejo) se reemplaza — la edad manda")
exp.release_lock(lp3)
open(lp, "w", encoding="utf-8").write('{"host": "otra-maquina", "pid"')   # JSON truncado, FRESCO
try:
    exp.acquire_lock(lkd, ".t.lock")
    chk(False, "lock: ilegible pero FRESCO debe seguir abortando")
except SystemExit as e:
    chk("otra corrida" in str(e), "lock: ilegible+fresco aborta (titular '?')")
os.utime(lp, (old, old))
lp4 = exp.acquire_lock(lkd, ".t.lock")          # truncado + viejo → se recupera
chk(os.path.isfile(lp4) and time.time() - os.path.getmtime(lp4) < 60,
    "lock: huérfano TRUNCADO (JSON parcial, viejo) se reemplaza")
exp.release_lock(lp4)
shutil.rmtree(lkd, ignore_errors=True)

# --------------------------------------------------------------- prune_empty_subdirs
for p, dest, kind, _ in scan:
    if kind != "skip":
        os.remove(p)                       # simula consumo
borradas, conservadas = exp.prune_empty_subdirs(ext, "_originales")
chk("Sub" in borradas, f"prune borra subcarpeta vaciada → {borradas}")
chk("Sub/deep" in borradas, "prune borra anidada")
chk("ConSkip" in conservadas, f"prune conserva subcarpeta con no-convertible → {conservadas}")
chk(os.path.isfile(os.path.join(ext, "ConSkip", ".secret")), "prune NO borra dotfiles no-junk en carpetas conservadas")
chk(os.path.isdir(os.path.join(ext, "_originales")), "prune no toca _originales")
chk(os.path.isdir(ext), "prune no borra la raíz del buzón")

# --------------------------------------------------------------- integración (pandoc + typst)
if shutil.which("pandoc") and shutil.which("typst"):
    iroot = tempfile.mkdtemp()
    ibase = tempfile.mkdtemp()            # base FUERA de root
    touch(iroot, "docs", "uno.md", body="# Documento Uno\n\n| a | b |\n| - | - |\n| 1 | 2 |\n")
    touch(iroot, "docs", "dos.md", body="# Documento Dos\n\ntexto")
    os.makedirs(os.path.join(ibase, "Externos", "Carpeta"))
    # un externo .md en subcarpeta (se convierte y la subcarpeta se borra). El nombre lo pone el
    # script de forma mecánica desde el FICHERO ("mi-nota" → "Mi nota"), no desde el H1.
    touch(ibase, "Externos", "Carpeta", "mi-nota.md", body="# Suelto\n\nhola")
    cfg_path = os.path.join(iroot, "nlm.config.json")
    json.dump({"base": ibase, "root": iroot,
               "notebook": {"name": "KB Test", "url": "https://notebooklm.google.com/notebook/abc"},
               "sources": [{"glob": "docs/*.md", "label": "Doc", "title": "h1"}]},
              open(cfg_path, "w"))
    r = subprocess.run([sys.executable, os.path.join(HERE, "export.py"), "--config", cfg_path],
                       capture_output=True, text=True)
    chk(r.returncode == 0, f"integración: exit 0 (stderr={r.stderr[:200]})")
    nv = os.path.join(ibase, "Nuevos")
    pdfs = sorted(f for f in os.listdir(nv) if f.endswith(".pdf")) if os.path.isdir(nv) else []
    chk("Doc - Documento Uno.pdf" in pdfs, f"integración: fuente con label+h1 → {pdfs}")
    chk("Doc - Documento Dos.pdf" in pdfs, "integración: segunda fuente")
    chk("Externo - Mi nota.pdf" in pdfs, f"integración: externo convertido (nombre por fichero) → {pdfs}")
    chk(all(open(os.path.join(nv, f), "rb").read(4) == b"%PDF" for f in pdfs), "integración: PDFs válidos")
    man = json.load(open(os.path.join(ibase, ".notebooklm-sync.json")))
    chk(man["items"]["Doc - Documento Uno.pdf"]["origin"] == "source", "integración: manifiesto origin source")
    chk(man["items"]["Externo - Mi nota.pdf"]["origin"] == "externo", "integración: manifiesto origin externo")
    chk(man.get("notebook", {}).get("name") == "KB Test", "integración: notebook del config en el manifiesto")
    chk(not os.path.isdir(os.path.join(ibase, "Externos", "Carpeta")), "integración: subcarpeta del buzón borrada")
    chk(os.path.isfile(os.path.join(nv, "_INDICE.md")), "integración: _INDICE.md generado")
    idx = open(os.path.join(nv, "_INDICE.md"), encoding="utf-8").read()
    chk("KB Test" in idx, "integración: notebook en la cabecera del índice")
    chk(not os.path.exists(os.path.join(ibase, ".notebooklm-sync.lock")), "integración: lock liberado tras la corrida")
    # idempotencia: segundo run no reconvierte (sin cambios) y no falla
    r2 = subprocess.run([sys.executable, os.path.join(HERE, "export.py"), "--config", cfg_path],
                        capture_output=True, text=True)
    chk(r2.returncode == 0 and "sin cambios: 0" not in r2.stdout, "integración: segundo run idempotente OK")
    # lock fresco de "otra máquina" → la corrida aborta; el dry-run (no escribe) pasa igualmente
    ilock = os.path.join(ibase, ".notebooklm-sync.lock")
    open(ilock, "w", encoding="utf-8").write('{"host": "otra-maquina", "pid": 1}')
    r3 = subprocess.run([sys.executable, os.path.join(HERE, "export.py"), "--config", cfg_path],
                        capture_output=True, text=True)
    chk(r3.returncode != 0 and "otra corrida" in (r3.stdout + r3.stderr), "integración: lock fresco aborta la corrida")
    chk(os.path.isfile(ilock), "integración: el lock ajeno no se toca al abortar")
    r4 = subprocess.run([sys.executable, os.path.join(HERE, "export.py"), "--config", cfg_path, "--dry-run"],
                        capture_output=True, text=True)
    chk(r4.returncode == 0, f"integración: dry-run corre sin lock (stderr={r4.stderr[:120]})")
    shutil.rmtree(iroot); shutil.rmtree(ibase)
else:
    print("  (SKIP integración: falta pandoc o typst)")

for tmp in (root, d2, d3):
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{ok} OK, {fail} FAIL")
sys.exit(1 if fail else 0)
