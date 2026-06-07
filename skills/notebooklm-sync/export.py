#!/usr/bin/env python3
"""Sincroniza una carpeta de Google Drive (montada con rclone) con fuentes locales + un buzón,
convirtiéndolas a PDF para NotebookLM y conservando el ID de Drive de cada fichero (autosync).

Modelo de TRES carpetas, todas bajo `base` (la carpeta de Drive montada):

- `base/`            Fuentes que YA están dadas de alta en NotebookLM. El script las **actualiza
                     in-place aquí** (mismo nombre/ruta → Drive conserva el ID → el autosync de
                     NotebookLM las refresca; nunca borra/recrea).
- `base/Nuevos/`     Pendientes de ALTA: fuentes locales que aún no están en la base + ficheros
                     del buzón ya procesados. Tú los das de alta a mano y los mueves a la base.
- `base/Externos/`   BUZÓN (recursivo): sueltas aquí ficheros que NO vienen de tus fuentes. El
                     script los renombra (y convierte), los deja en `Nuevos/` y borra las
                     subcarpetas vaciadas. PDF se mueven; no-PDF se convierten y el original se
                     archiva en `_originales/`.

TODO es configurable por `notebooklm-sync.config.json` (o `--config`): jerarquía de carpetas,
fuentes, conversión, tratado de ficheros y comportamiento del asistente en la clasificación. Ver
`notebooklm-sync.config.example.json` y SKILL.md.

Reglas:
- READ-ONLY sobre las fuentes locales. Detección de cambios por **hash de contenido** (no mtime).
- Obsoletos (fuente borrada cuyo PDF sigue en la base): solo se **reportan**.
- Añadir/quitar fuentes en NotebookLM es MANUAL. La clasificación fina del buzón la hace un
  asistente (Claude) como paso de la skill; el script solo deja un nombre provisional.

Uso:
    python3 export.py [--config notebooklm-sync.config.json] [--dry-run] [--force]
    python3 export.py --base "~/Drive/NotebookLM" --root . --dry-run
"""
import os
import re
import sys
import glob
import json
import copy
import shutil
import hashlib
import tempfile
import argparse
import datetime
import subprocess

# La consola de Windows suele ir en cp1252 y revienta (UnicodeEncodeError) al imprimir nombres
# con '→', '¿' o acentos. Forzamos UTF-8 en stdout/stderr (no-op en Linux/macOS).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

HERE = os.path.dirname(os.path.realpath(__file__))
CONFIG_NAME = "notebooklm-sync.config.json"

# Mapa por defecto extensión → formato de entrada de pandoc.
EXT_FMT = {
    ".md": "gfm", ".markdown": "gfm", ".txt": "markdown",
    ".docx": "docx", ".html": "html", ".htm": "html", ".rtf": "rtf",
    ".odt": "odt", ".epub": "epub", ".pptx": "pptx", ".rst": "rst",
    ".org": "org", ".tex": "latex", ".textile": "textile",
}

DEFAULTS = {
    "base": None,
    "root": None,
    "sources": [],
    "layout": {
        "nuevos": "Nuevos",
        "externos": "Externos",
        "originales": "_originales",
        "manifest": ".notebooklm-sync.json",
        "indexFile": "_INDICE.md",
        "preserveSubdirs": False,        # true: los externos mantienen su subruta dentro de Nuevos
    },
    "conversion": {
        "outputExtension": ".pdf",
        "pdfEngine": "typst",            # solo si outputExtension == .pdf
        "header": "pandoc-header.typ",   # cabecera typst (relativa al script); null para desactivar
        "extraArgs": [],                 # args extra a pandoc
        "formatOverrides": {},           # override del mapa ext→formato, p.ej. {".txt": "gfm"}
    },
    "files": {
        "externosPdf": "move",           # move | copy
        "archiveOriginals": True,        # archivar no-PDF originales en _originales/
        "deleteEmptySubdirs": True,      # borrar subcarpetas vaciadas del buzón
        "convertExtensions": None,       # null=todas las soportadas; o lista [".md", ".docx", …]
    },
    # Consumido por el ASISTENTE (Claude), no por el script. Documentado en SKILL.md.
    "classification": {
        "enabled": True,
        "language": "es",
        "categories": ["Revista", "Artículo", "Informe", "Apuntes", "Documento"],
        "nameTemplate": "Externo - {categoria} - {titulo}.pdf",
        "relevanceField": "relevante",
        "priorityBuckets": [],           # p.ej. ["proyecto", "tangencial"] (clasificación prioritaria)
        "lowConfidence": "flag",         # flag | skip
        "extraInstructions": "",
    },
}


# --------------------------------------------------------------------------- config

def expand(p):
    return os.path.realpath(os.path.expanduser(p)) if p else p


def deep_merge(base, override):
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_config(path):
    """Carga y fusiona el config sobre los DEFAULTS. Devuelve (cfg, config_dir). Si no se pasa
    `path`, busca ./notebooklm-sync.config.json; si tampoco está, usa solo defaults."""
    user, cfg_dir = {}, os.getcwd()
    if path is None:
        cand = os.path.join(os.getcwd(), CONFIG_NAME)
        path = cand if os.path.exists(cand) else None
    if path is not None:
        path = expand(path)
        try:
            with open(path, encoding="utf-8") as f:
                user = json.load(f)
        except (OSError, ValueError) as e:
            sys.exit(f"ABORTADO: no puedo leer el config {path}: {e}")
        cfg_dir = os.path.dirname(path)
    return deep_merge(DEFAULTS, user), cfg_dir


def resolve_ext_fmt(cfg):
    """Mapa efectivo ext→formato: EXT_FMT + overrides, filtrado por files.convertExtensions."""
    ext_fmt = dict(EXT_FMT)
    ext_fmt.update({k.lower(): v for k, v in (cfg["conversion"].get("formatOverrides") or {}).items()})
    keep = cfg["files"].get("convertExtensions")
    if keep:
        keep = {e.lower() for e in keep}
        ext_fmt = {k: v for k, v in ext_fmt.items() if k in keep}
    return ext_fmt


# --------------------------------------------------------------------------- helpers de nombre

_WIN_RESERVED = {"CON", "PRN", "AUX", "NUL",
                 *(f"COM{i}" for i in range(1, 10)),
                 *(f"LPT{i}" for i in range(1, 10))}
_MAX_STEM = 150   # margen bajo el límite de ruta de Windows (MAX_PATH 260) contando la carpeta de Drive


def sanitize(name):
    """Nombre de fichero válido en Windows, macOS y Linux (`name` incluye la extensión).
    Quita reservados de Windows `< > : " / \\ | ? *` (y '¿') y caracteres de control; '/' y '\\'
    → '-'; recorta puntos/espacios finales; evita nombres de dispositivo (CON, NUL, COM1…); y
    acota la longitud del tronco para no pasarse del límite de ruta de Windows."""
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    stem = stem.replace("/", "-").replace("\\", "-")
    stem = re.sub(r'["?¿*<>:|]', "", stem)
    stem = re.sub(r"[\x00-\x1f]", "", stem)
    stem = re.sub(r"\s+", " ", stem).strip().rstrip(". ").strip()
    if stem.upper() in _WIN_RESERVED:
        stem = "_" + stem
    if len(stem) > _MAX_STEM:
        stem = stem[:_MAX_STEM].rstrip(". ").strip()
    if not stem:
        stem = "documento"
    return f"{stem}.{ext}" if ext else stem


def sanitize_component(name):
    """Como sanitize pero para un componente de carpeta (sin extensión)."""
    return sanitize(name + ".x")[:-2]


def bump(name, n, out_ext):
    """Inserta un sufijo anticolisión ' (n)' antes de la extensión."""
    stem = name[:-len(out_ext)] if name.endswith(out_ext) else os.path.splitext(name)[0]
    return f"{stem} ({n}){out_ext}"


def h1(path):
    """Primer encabezado H1 (`# ...`), o None si no hay / no es texto."""
    try:
        for line in open(path, encoding="utf-8"):
            s = line.strip()
            if s.startswith("# "):
                return s[2:].strip()
    except (OSError, UnicodeDecodeError):
        pass
    return None


def deburr(stem):
    t = re.sub(r"[-_]+", " ", stem).strip()
    t = re.sub(r"\s+", " ", t)
    return (t[:1].upper() + t[1:]) if t else stem


def clean(t):
    if not t:
        return None
    t = t.replace("`", "").strip()
    t = re.sub(r"\s+", " ", t).strip().rstrip(".").strip()
    return t or None


def title_for(path, strategy):
    stem = os.path.splitext(os.path.basename(path))[0]
    if strategy != "filename":
        c = clean(h1(path))
        if c:
            return c
    return deburr(stem)


def titulo_externo(stem):
    """Título provisional para un fichero del buzón. Fallback trazable si queda vacío."""
    t = re.sub(r"[-_]+", " ", stem).strip()
    t = re.sub(r"\s+", " ", t)
    t = (t[:1].upper() + t[1:]) if t else ""
    probe = re.sub(r'["?¿*<>:|\\/]|[\x00-\x1f]', "", t).strip(". ").strip()
    if not probe:
        return "Documento " + hashlib.sha256(stem.encode("utf-8")).hexdigest()[:8]
    return t


# --------------------------------------------------------------------------- plan de fuentes

def build_plan(sources, root, ext_fmt, out_ext):
    """[(src_abs, pdf_name, from_fmt|None, priority)] desde las reglas `sources` (en orden).
    `from_fmt`=None → copiar tal cual (fuente con la misma extensión de salida)."""
    plan, seen, taken = [], set(), set()
    for rule in sources:
        pat = rule.get("glob")
        if not pat:
            continue
        label = (rule.get("label") or "").strip()
        strategy = rule.get("title", "h1")
        priority = rule.get("priority")
        for p in sorted(glob.glob(os.path.join(root, pat), recursive=True)):
            if not os.path.isfile(p):
                continue
            ap = os.path.realpath(p)
            if ap in seen:
                continue
            ext = os.path.splitext(p)[1].lower()
            if ext == out_ext:
                from_fmt = None            # misma extensión → copiar
            elif ext in ext_fmt:
                from_fmt = ext_fmt[ext]
            else:
                continue
            seen.add(ap)
            title = title_for(p, strategy)
            name = sanitize(f"{label} - {title}{out_ext}" if label else f"{title}{out_ext}")
            base_name = name                # anticolisión por nombre: dos fuentes con el mismo
            i = 2                           # nombre de salida no se pisan (pérdida silenciosa)
            while name in taken:
                name = bump(base_name, i, out_ext)
                i += 1
            taken.add(name)
            plan.append((ap, name, from_fmt, priority))
    return plan


# --------------------------------------------------------------------------- conversión / hash

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def convert_doc(src, dst, from_fmt, conv):
    """Convierte (o copia, si from_fmt es None) src → dst IN-PLACE (temp + copia de bytes, para no
    borrar/recrear el destino y conservar su ID en Drive). Fail-loud."""
    if from_fmt is None:
        shutil.copyfile(src, dst)
        return
    out_ext = conv["outputExtension"]
    fd, tmp = tempfile.mkstemp(suffix=out_ext)
    os.close(fd)
    try:
        cmd = ["pandoc", "-f", from_fmt]
        cmd += list(conv.get("extraArgs") or [])
        if out_ext == ".pdf":
            header = conv.get("header")
            if header:
                hp = header if os.path.isabs(header) else os.path.join(HERE, header)
                if os.path.exists(hp):
                    cmd += ["-H", hp]
            engine = conv.get("pdfEngine")
            if engine:
                cmd += [f"--pdf-engine={engine}"]
        cmd += [src, "-o", tmp]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not os.path.getsize(tmp):
            raise RuntimeError(f"pandoc falló en {os.path.basename(src)}:\n{r.stderr.strip()}")
        shutil.copyfile(tmp, dst)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


# --------------------------------------------------------------------------- guarda + manifiesto

def guard_base(base, root, lay, dry):
    if base == root or base.startswith(root + os.sep):
        sys.exit(f"ABORTADO: la base no puede estar dentro de la raíz de fuentes ({base}).")
    nuevos, externos, manifest = lay["nuevos"], lay["externos"], lay["manifest"]
    if os.path.isdir(base):
        has_manifest = os.path.exists(os.path.join(base, manifest))
        has_structure = os.path.isdir(os.path.join(base, nuevos)) or os.path.isdir(os.path.join(base, externos))
        if not has_manifest and not has_structure and os.listdir(base):
            sys.exit(
                f"ABORTADO: {base} existe pero no parece la carpeta de NotebookLM\n"
                f"  (sin manifiesto {manifest} ni subcarpetas {nuevos}/ o {externos}/).\n"
                f"  No la toco (¿ruta equivocada?). Crea {nuevos}/ y {externos}/ dentro si de verdad lo es."
            )
    if not dry:
        try:
            os.makedirs(os.path.join(base, nuevos), exist_ok=True)
            os.makedirs(os.path.join(base, externos), exist_ok=True)
        except OSError as e:
            sys.exit(f"ABORTADO: no puedo crear la estructura en {base}: {e}")
        probe = os.path.join(base, ".nlm-probe")
        try:
            with open(probe, "w", encoding="utf-8") as f:
                f.write("ok")
            with open(probe, encoding="utf-8") as f:
                assert f.read() == "ok"
            os.remove(probe)
        except (OSError, AssertionError) as e:
            sys.exit(f"ABORTADO: la base no es escribible ({base}): {e}\n"
                     f"  ¿Está montado el Drive (rclone)? Comprueba `mountpoint` / `systemctl --user status`.")


def load_manifest(base, manifest_name):
    try:
        with open(os.path.join(base, manifest_name), encoding="utf-8") as f:
            return json.load(f).get("items", {})
    except (OSError, ValueError):
        return {}


def save_manifest(base, manifest_name, items, today):
    data = {"version": 3, "updated_at": today, "items": items}
    with open(os.path.join(base, manifest_name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)


def list_pdfs(d, out_ext):
    if not os.path.isdir(d):
        return set()
    return {e for e in os.listdir(d) if e.endswith(out_ext) and os.path.isfile(os.path.join(d, e))}


# --------------------------------------------------------------------------- buzón

def scan_externos(externos_dir, nuevos_dir, existing, ext_fmt, out_ext, originales, preserve, processed):
    """Ficheros del buzón, **recursivos**. Devuelve [(ruta, dest_rel|display, kind, from_fmt)] con
    kind ∈ {pdf, convert, skip, dup}. `dest_rel` es la ruta destino relativa a Nuevos/ (plana, o
    con subcarpeta si preserve=True). Anticolisión contra `existing` (nombres planos ya presentes),
    contra lo elegido en esta corrida y contra el disco. `processed` = {(basename, sha)} de externos
    YA procesados (del manifiesto): un fichero con ese mismo contenido se marca `dup` y no se
    re-procesa (idempotencia con `externosPdf: copy`, donde el original no se consume)."""
    out = []
    if not os.path.isdir(externos_dir):
        return out
    taken = set()                                   # dest_rel ya elegidos esta corrida
    flat_existing = set(existing)                   # nombres planos ya presentes (base ∪ Nuevos)
    pnames = {n for n, _ in (processed or set())}   # basenames ya procesados (para no hashear de más)
    paths = []
    for root, dirs, files in os.walk(externos_dir):
        dirs[:] = sorted(d for d in dirs if d != originales and not d.startswith("."))
        paths += [os.path.join(root, fn) for fn in files]
    for p in sorted(paths):
        e = os.path.basename(p)
        if e.startswith(".") or not os.path.isfile(p):
            continue
        rel = os.path.relpath(p, externos_dir).replace(os.sep, "/")
        stem, ext = os.path.splitext(e)
        ext = ext.lower()
        kind = "pdf" if ext == out_ext else ("convert" if ext in ext_fmt else "skip")
        if kind == "skip":
            out.append((p, rel, "skip", None))
            continue
        if e in pnames and (e, sha256_file(p)) in processed:   # mismo nombre+contenido ya procesado
            out.append((p, rel, "dup", None))
            continue
        name = sanitize(f"Externo - {titulo_externo(stem)}{out_ext}")
        subdir = ""
        if preserve and os.path.dirname(rel):
            subdir = "/".join(sanitize_component(c) for c in os.path.dirname(rel).split("/"))
        base_name = name
        i = 2
        while True:
            dest_rel = f"{subdir}/{name}" if subdir else name
            collide = (dest_rel in taken
                       or os.path.exists(os.path.join(nuevos_dir, *dest_rel.split("/")))
                       or (not subdir and name in flat_existing))
            if not collide:
                break
            name = bump(base_name, i, out_ext)
            i += 1
        taken.add(dest_rel)
        out.append((p, dest_rel, kind, ext_fmt.get(ext)))
    return out


def prune_empty_subdirs(externos_dir, originales):
    borradas, conservadas = [], []
    if not os.path.isdir(externos_dir):
        return borradas, conservadas
    junk = {".DS_Store", "Thumbs.db", "desktop.ini"}
    for root, _dirs, _files in os.walk(externos_dir, topdown=False):
        rel = os.path.relpath(root, externos_dir)
        if rel == "." or rel == originales or rel.startswith(originales + os.sep):
            continue
        for fn in list(os.listdir(root)):
            if fn in junk:                  # solo basura conocida; NUNCA un dotfile cualquiera del usuario
                try:
                    os.remove(os.path.join(root, fn))
                except OSError:
                    pass
        try:
            os.rmdir(root)
            borradas.append(rel.replace(os.sep, "/"))
        except OSError:
            conservadas.append(rel.replace(os.sep, "/"))
    return borradas, conservadas


# --------------------------------------------------------------------------- índice

def write_index(nuevos_dir, index_file, externos_name, nuevos, actualizados, obsoletos, externos_skip, today):
    L = ["# Índice del export para NotebookLM", ""]
    L += [
        f"> Generado ({today}) por `notebooklm-sync`. **No editar a mano.**",
        "> `Nuevos/` = pendientes de ALTA (añádelos a NotebookLM y muévelos a la base).",
        "> La base se actualiza **in-place** (Drive conserva el ID → autosync de NotebookLM).",
        "> Añadir/quitar fuentes en NotebookLM es **manual**.",
        "",
        f"- **Nuevos** ({len(nuevos)}): añadir a NotebookLM y mover a la base.",
        f"- **Actualizados en la base** ({len(actualizados)}): el autosync los refresca, no tocar.",
        f"- **Obsoletos** ({len(obsoletos)}): la fuente ya no existe; **revisar/quitar a mano**.",
        f"- **Externos sin procesar** ({len(externos_skip)}): formato no convertible; siguen en `{externos_name}/`.",
        "",
    ]

    def section(title, rows):
        if not rows:
            return
        L.append(f"## {title} ({len(rows)})\n")
        L.append("| Nombre en NotebookLM | Origen |")
        L.append("| --- | --- |")
        for dst, origen in sorted(rows, key=lambda x: x[0]):
            L.append(f"| `{dst}` | `{origen}` |")
        L.append("")

    section("Nuevos — AÑADIR a NotebookLM", nuevos)
    section("Actualizados en la base (autosync)", actualizados)
    section("Obsoletos — revisar/quitar a mano", [(d, "—") for d in obsoletos])
    section("Externos sin procesar (formato no convertible)", externos_skip)
    os.makedirs(nuevos_dir, exist_ok=True)
    open(os.path.join(nuevos_dir, index_file), "w", encoding="utf-8").write("\n".join(L))


# --------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Export de fuentes a PDF para NotebookLM (configurable, in-place, autosync).")
    ap.add_argument("--config", default=None, help=f"ruta al config JSON (por defecto ./{CONFIG_NAME})")
    ap.add_argument("--base", default=None, help="carpeta base de NotebookLM (override del config)")
    ap.add_argument("--root", default=None, help="raíz de los globs de sources (override)")
    ap.add_argument("--dry-run", action="store_true", help="solo muestra el plan, no escribe")
    ap.add_argument("--force", action="store_true", help="reconvierte aunque el hash no haya cambiado")
    args = ap.parse_args()

    cfg, cfg_dir = load_config(args.config)
    lay, conv, files = cfg["layout"], cfg["conversion"], cfg["files"]
    out_ext = conv["outputExtension"]
    base = expand(args.base or cfg.get("base"))
    if not base:
        sys.exit("ABORTADO: falta 'base' (defínela en el config o pásala con --base).")
    root = expand(args.root or cfg.get("root") or cfg_dir or ".")
    ext_fmt = resolve_ext_fmt(cfg)

    for tool in ("pandoc", "typst"):
        if conv.get("pdfEngine") == "typst" and not shutil.which(tool):
            sys.exit(f"ABORTADO: falta '{tool}' en el PATH. Necesito pandoc + typst.")
    if not shutil.which("pandoc"):
        sys.exit("ABORTADO: falta 'pandoc' en el PATH.")

    guard_base(base, root, lay, args.dry_run)
    nuevos_dir = os.path.join(base, lay["nuevos"])
    externos_dir = os.path.join(base, lay["externos"])
    originales_dir = os.path.join(externos_dir, lay["originales"])
    manifest = load_manifest(base, lay["manifest"])

    plan = build_plan(cfg.get("sources", []), root, ext_fmt, out_ext)
    desired = {}  # pdf -> (src, from_fmt, sha, priority)
    for src, pdf, from_fmt, priority in plan:
        desired[pdf] = (src, from_fmt, sha256_file(src), priority)

    base_pdfs = list_pdfs(base, out_ext)
    nuevos_pdfs = list_pdfs(nuevos_dir, out_ext)
    existing = base_pdfs | nuevos_pdfs | set(desired.keys())
    processed = {(v.get("source"), v.get("sha")) for v in manifest.values() if v.get("origin") == "externo"}
    externos = scan_externos(externos_dir, nuevos_dir, existing, ext_fmt, out_ext,
                             lay["originales"], lay["preserveSubdirs"], processed)

    upd_base, new_src, sin_cambios = [], [], []
    for pdf, (src, from_fmt, sha, priority) in sorted(desired.items()):
        prev = manifest.get(pdf)
        changed = args.force or not prev or prev.get("sha") != sha
        if pdf in base_pdfs:
            (upd_base if changed else sin_cambios).append(pdf)
        else:
            new_src.append(pdf)

    obsoletos = sorted(p for p in base_pdfs
                       if manifest.get(p, {}).get("origin") == "source" and p not in desired)

    ext_process = [e for e in externos if e[2] not in ("skip", "dup")]
    ext_skip = [e for e in externos if e[2] == "skip"]
    ext_dup = [e for e in externos if e[2] == "dup"]

    if args.dry_run:
        print(f"[dry-run] base: {base}  ·  root: {root}")
        print(f"  Fuentes → actualizar EN LA BASE (in-place): {len(upd_base)}")
        for p in upd_base:
            print(f"    ~ {p}")
        print(f"  Fuentes → NUEVOS (pendiente de alta): {len(new_src)}")
        for p in sorted(new_src):
            print(f"    + {lay['nuevos']}/{p}")
        print(f"  Fuentes → sin cambios: {len(sin_cambios)}")
        print(f"  Externos → procesar (a {lay['nuevos']}/): {len(ext_process)}")
        for p, dest_rel, kind, _ in ext_process:
            origen = os.path.relpath(p, externos_dir)
            print(f"    + {lay['nuevos']}/{dest_rel}  ({'mover' if kind == 'pdf' else 'convertir'} ← {origen})")
        subdirs = sorted({os.path.dirname(os.path.relpath(p, externos_dir))
                          for p, _, _, _ in ext_process
                          if os.path.dirname(os.path.relpath(p, externos_dir))})
        if subdirs and files["deleteEmptySubdirs"]:
            print(f"  Externos → subcarpetas a vaciar y borrar (si no quedan no-convertibles): {subdirs}")
        if ext_skip:
            print(f"  Externos → sin procesar (formato no convertible): {len(ext_skip)}")
            for _p, disp, _, _ in ext_skip:
                print(f"    · {disp}  (se queda en {lay['externos']}/)")
        if ext_dup:
            print(f"  Externos → ya procesados (mismo contenido, se omiten): {len(ext_dup)}")
            for _p, disp, _, _ in ext_dup:
                print(f"    = {disp}")
        if obsoletos:
            print(f"  Obsoletos (reportar, no tocar): {len(obsoletos)}")
            for p in obsoletos:
                print(f"    ! {p}")
        return

    nuevos_idx, actualizados_idx, fallos = [], [], []

    # 1) Fuentes locales
    for pdf, (src, from_fmt, sha, priority) in sorted(desired.items()):
        prev = manifest.get(pdf)
        changed = args.force or not prev or prev.get("sha") != sha
        rel = os.path.relpath(src, root).replace(os.sep, "/")
        try:
            if pdf in base_pdfs:
                if changed:
                    convert_doc(src, os.path.join(base, pdf), from_fmt, conv)
                    actualizados_idx.append((pdf, rel))
            else:
                if changed or pdf not in nuevos_pdfs:
                    convert_doc(src, os.path.join(nuevos_dir, pdf), from_fmt, conv)
                nuevos_idx.append((pdf, rel))
            entry = {"origin": "source", "source": rel, "sha": sha}
            if priority is not None:
                entry["priority"] = priority
            manifest[pdf] = entry
        except Exception as e:                                       # noqa: BLE001 — fail-loud, seguimos
            fallos.append((pdf, str(e)))

    # 2) Buzón → SIEMPRE a Nuevos.
    for orig, dest_rel, kind, from_fmt in ext_process:
        try:
            sha = sha256_file(orig)
            target = os.path.join(nuevos_dir, *dest_rel.split("/"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if kind == "pdf":
                if files["externosPdf"] == "copy":
                    shutil.copyfile(orig, target)
                else:
                    shutil.move(orig, target)
            else:
                convert_doc(orig, target, from_fmt, conv)
                if files["archiveOriginals"]:
                    os.makedirs(originales_dir, exist_ok=True)
                    shutil.move(orig, os.path.join(originales_dir, os.path.basename(orig)))
                else:
                    os.remove(orig)
            manifest[dest_rel] = {"origin": "externo", "source": os.path.basename(orig), "sha": sha}
            nuevos_idx.append((dest_rel, f"{lay['externos']}/{os.path.basename(orig)}"))
        except Exception as e:                                       # noqa: BLE001
            fallos.append((dest_rel, str(e)))

    # 3) Limpia subcarpetas del buzón ya vaciadas (si está activado).
    borradas_dirs, conservadas_dirs = ([], [])
    if files["deleteEmptySubdirs"]:
        borradas_dirs, conservadas_dirs = prune_empty_subdirs(externos_dir, lay["originales"])

    keep = base_pdfs | nuevos_pdfs | {n for n, _ in nuevos_idx} | {a for a, _ in actualizados_idx}
    manifest = {k: v for k, v in manifest.items() if k in keep}

    today = datetime.date.today().isoformat()
    save_manifest(base, lay["manifest"], manifest, today)
    write_index(nuevos_dir, lay["indexFile"], lay["externos"], nuevos_idx, actualizados_idx, obsoletos,
                [(n, f"{lay['externos']}/{n}") for _, n, _, _ in ext_skip], today)

    print(f"Base: {base}")
    print(f"  Actualizados en la base (in-place, autosync): {len(actualizados_idx)}")
    print(f"  NUEVOS (pendientes de alta, en '{lay['nuevos']}/'): {len(nuevos_idx)}")
    print(f"  Externos procesados → '{lay['nuevos']}/': {len(ext_process)}  ·  sin procesar: {len(ext_skip)}"
          + (f"  ·  ya procesados (omitidos): {len(ext_dup)}" if ext_dup else ""))
    if borradas_dirs:
        print(f"  Subcarpetas de Externos vaciadas y borradas: {borradas_dirs}")
    if conservadas_dirs:
        print(f"  ⚠ Subcarpetas de Externos conservadas (aún con ficheros): {conservadas_dirs}")
    print(f"  Obsoletos (reportados, no tocados): {len(obsoletos)}")
    if ext_skip:
        print(f"  ⚠ Externos no convertibles (siguen en '{lay['externos']}/'): {[disp for _p, disp, _, _ in ext_skip]}")
    if fallos:
        print(f"  ⚠ FALLOS ({len(fallos)}):")
        for name, err in fallos:
            print(f"    · {name}: {err.splitlines()[0] if err else ''}")
        sys.exit(1)


if __name__ == "__main__":
    main()
