---
name: notebooklm-export
description: Sincroniza una carpeta de Google Drive (montada con rclone) con tus fuentes locales + un buzón de entrada, convirtiéndolas a PDF para NotebookLM y conservando el ID de Drive de cada fichero (autosync). Determinista, idempotente (hash de contenido), read-only sobre las fuentes. Requiere pandoc + typst + un mount de rclone. Configurable por notebooklm-export.config.json.
allowed-tools: Bash, Read
---

# notebooklm-export

Mantiene las fuentes de **NotebookLM** a partir de **dos orígenes** — un conjunto de **fuentes
locales** que configuras (Markdown, docx, html…) y un **buzón `Externos/`** para ficheros sueltos —
convirtiéndolas a **PDF** en una carpeta de **Google Drive montada con rclone**. La lógica vive en
un script determinista (`export.py`); esta skill = configurarlo y ejecutarlo.

**Por qué existe:** NotebookLM **auto-sincroniza** una fuente importada de Drive cuando su
contenido cambia **si conservas el mismo file ID**. Sobrescribir un PDF *en su sitio* a través de
un mount de rclone conserva el ID (`files.update`, nueva revisión) → NotebookLM re-ingiere el
contenido sin re-importar. Este tool automatiza ese flujo.

## Modelo de tres carpetas (todas bajo `base`)

`base` (en el config) apunta a la carpeta de Drive montada (p.ej. `~/Drive/NotebookLM`):

| Carpeta | Rol | Quién escribe |
| --- | --- | --- |
| **`base/`** | Fuentes **ya dadas de alta** en NotebookLM. El script las **actualiza in-place aquí** → Drive conserva el ID → autosync de NotebookLM las refresca. Nunca borra/recrea. | script (update) + tú (mueves de `Nuevos/`) |
| **`base/Nuevos/`** | **Pendientes de alta**: fuentes nuevas + ficheros del buzón ya procesados. Tú los das de alta a mano y los mueves a la base. El script **nunca vacía** esta carpeta. | script → tú vacías |
| **`base/Externos/`** | **Buzón** (recursivo): sueltas ahí ficheros que **no** vienen de tus fuentes, también en subcarpetas. El script los renombra (y convierte), los deja **aplanados** en `Nuevos/` y **borra las subcarpetas** vaciadas. PDF → se mueven; no-PDF → se convierten y el original se archiva en `Externos/_originales/`. | tú (sueltas) → script (consume) |

## Configuración

`notebooklm-export.config.json` (o `--config`); todo tiene defaults sensatos salvo `base`. Ver
`notebooklm-export.config.example.json` y la **tabla completa en el [README](README.md)**. Bloques:

```jsonc
{
  "base": "~/Drive/NotebookLM",      // (obligatorio) carpeta de Drive montada; fuera de root
  "root": ".",                        // raíz de los globs (def: carpeta del config)
  "sources": [                        // reglas en orden; sources:[] = solo buzón
    { "glob": "docs/**/*.md", "label": "", "title": "h1", "priority": "alta" }
  ],
  "layout":         { /* nuevos, externos, originales, manifest, indexFile, preserveSubdirs */ },
  "conversion":     { /* outputExtension, pdfEngine, header, extraArgs, formatOverrides */ },
  "files":          { /* externosPdf(move|copy), archiveOriginals, deleteEmptySubdirs, convertExtensions */ },
  "classification": { /* enabled, language, categories, nameTemplate, priorityBuckets, … */ }
}
```

- **`sources[]`**: `glob` (relativo a `root`, soporta `**`), `label` (prefijo del nombre; vacío =
  sin prefijo), `title` (`h1` = primer encabezado Markdown con fallback al nombre; `filename`),
  `priority` (metadato libre que se guarda en el manifiesto). Una fuente captada por una regla
  anterior no se repite.
- **`layout`**: jerarquía/nombres de carpetas y ficheros de estado; `preserveSubdirs` conserva la
  subruta del buzón dentro de `Nuevos/` (por defecto se aplana).
- **`conversion`**: formato de salida, motor PDF, cabecera typst, args extra y overrides del mapa
  extensión→formato de pandoc. Las fuentes con la misma extensión de salida se **copian**.
- **`files`**: tratado del buzón (mover/copiar PDFs, archivar originales, borrar subcarpetas
  vaciadas, restringir extensiones convertibles).
- **`classification`**: lo consume el **asistente** (Claude), no el script (ver siguiente sección).

## Flujo en cada corrida

1. **Fuentes** ya en la base → si cambió el contenido (hash), reconvierte y **sobreescribe en la
   base** (mismo ID → autosync). Si no cambió, no toca nada.
2. **Fuentes** que no están en la base → convierte a **`Nuevos/`** (alta pendiente).
3. **Buzón `Externos/`** (recursivo) → mueve/convierte a **`Nuevos/`** con nombre provisional
   `Externo - <nombre>.pdf` y **borra las subcarpetas** vaciadas.
4. **Asistente** (paso opcional, no del script) → lee el contenido de los `Externo - *` recién
   dejados y los **reclasifica y renombra con precisión** (ver abajo).
5. **Tú, a mano** (NotebookLM no tiene API): das de alta lo de `Nuevos/`, los mueves a la base y
   dejas `Nuevos/`/`Externos/` vacías para el próximo export.

## Clasificación de externos (paso del asistente)

El script renombra los externos de forma **mecánica** (de-kebabiza el nombre). La clasificación
fina la hace un asistente (Claude) porque requiere leer el contenido con criterio:

1. Para cada `Externo - *.pdf` en `Nuevos/`, lee las primeras páginas
   (`pdftotext -f 1 -l 3 "<pdf>" -`; si es escaneado sin texto, `pdfinfo` + el nombre).
2. Honra el bloque **`classification`** del config: asigna una **categoría** de
   `classification.categories`, un **título limpio** en `classification.language`, y renombra según
   `classification.nameTemplate` (placeholders `{categoria}` y `{titulo}`). Re-mapea la clave del
   manifiesto y regenera el índice.
3. Si hay `classification.priorityBuckets`, etiqueta cada externo en `classification.relevanceField`
   del manifiesto (clasificación prioritaria). Marca los de baja confianza según
   `classification.lowConfidence` (`flag` o `skip`). Aplica `classification.extraInstructions`.

Si la skill se corre **sin asistente** (el script a pelo en CI) o con `classification.enabled:false`,
los externos se quedan con el nombre provisional `Externo - <nombre>.pdf`: correcto, solo menos fino.

## Requisitos

`pandoc` **y** `typst` en el PATH + un **mount de rclone** de la carpeta de Drive con
`--vfs-cache-mode writes`. El script aborta si falta pandoc o typst. Para clasificar externos:
`pdftotext`/`pdfinfo` (poppler).

```bash
python3 export.py                       # usa ./notebooklm-export.config.json
python3 export.py --config ruta.json
python3 export.py --base "~/Drive/NotebookLM" --root . --dry-run
python3 export.py --force               # reconvierte todo (ignora hash)
```

## Garantías y notas

- **Read-only sobre las fuentes**: solo las lee; nunca las modifica. (El buzón vive en Drive.)
- **PDF** vía `pandoc --pdf-engine=typst`; `pandoc-header.typ` hace divisibles los `#figure` →
  las tablas largas se parten entre páginas sin solaparse.
- **Autosync in-place**: sobreescribir un PDF en su sitio (`shutil.copyfile`) a través del mount
  de rclone **conserva el file ID de Drive**. El patrón "atomic save" (temp + rename) lo **rompe**
  (rclone replica delete+create → ID nuevo): el script NO lo usa.
- **Idempotente por hash de contenido** (no por mtime). Solo reconvierte lo que cambió.
- **Multiplataforma**: nombres válidos en Windows/macOS/Linux (sin `< > : " / \ | ? *` ni de
  control, sin nombres de dispositivo `CON`/`NUL`…, longitud acotada) + salida UTF-8.
- **Seguridad**: aborta si `base` cae dentro de `root`, o si la carpeta no parece la de NotebookLM
  (sin manifiesto ni `Nuevos/`/`Externos/`) y no está vacía. Solo toca lo que gestiona.
- **Subcarpetas del buzón**: las que conserven ficheros no convertibles —o **compartidos desde
  otra cuenta** que no puedas borrar (`Error 403`)— se dejan y se reportan. El mount de rclone
  **colapsa nombres duplicados** de Drive (uno queda huérfano → `rclone dedupe`). `_originales/`
  nunca se toca.
