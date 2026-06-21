---
name: symbyosis
description: Disciplina del vault de coordinación symbyosis (repo b2c-mvms/symbyosis + Obsidian). Úsala al crear o sincronizar briefings, estudios de mercado/técnicos y análisis compartidos con Marc S, o al tocar la capa de coordinación (equipo/). Codifica taxonomía, frontmatter, la regla de frontera con Fulgor (enlaza, no recopies), nombres anti-conflicto y el modelo de git híbrido (notas directas a main con auto-sync; estructura por PR). Cero PII, source-honesty.
allowed-tools: Read, Write, Edit, Bash
---

# symbyosis — vault de coordinación compartido

Disciplina para trabajar el repo **`b2c-mvms/symbyosis`** (clon local
`~/Projects/symbyosis`), que es a la vez repo git y **vault de Obsidian**. Es el
espacio de coordinación entre **Marc V** (técnico) y **Marc S** (comercial) para
**Fulgor**: briefings, estudios de mercado/técnicos y análisis. El producto
vive en `b2c-mvms/Fulgor`.

Invócala cuando: redactes o sincronices un briefing o un estudio/análisis, o
toques la capa de coordinación (`equipo/`).

## Regla de frontera (lo primero)

- **Enlaza, no recopies.** Una nota referencia el commit / PR / ADR / entrada de
  session-log de `Fulgor` que resume; no duplica su contenido.
- Lo que **madura en decisión** se promociona a `Fulgor` (ADR vía
  `adr-writer`, o `docs/business/…`); la nota aquí queda como puntero.
- **Cero PII** (datos personales de proveedores, acuerdos firmados). Toda cifra de
  un estudio lleva **fuente + fecha** (source-honesty).
- Para leer el producto, Claude usa directamente `~/Projects/fulgor`
  (el filesystem MCP ya cubre todo `/home/marc`). El symlink `_links/fulgor`
  es solo para que el grafo de Obsidian lo abarque, y está gitignored.

## Taxonomía y nombres

| Tipo | Carpeta | Plantilla |
| --- | --- | --- |
| briefing | `briefings/AAAA/MM/` | `_templates/briefing.md` |
| estudio de mercado | `studies/market/` | `_templates/market-study.md` |
| estudio técnico | `studies/technical/` | `_templates/technical-study.md` |
| análisis | `analyses/` | `_templates/analysis.md` |
| coordinación | `equipo/` | (edición directa) |

- Nombre de nota: **`AAAA-MM-DD-<slug>-<autor>.md`**, `autor ∈ {marcv, marcs}`.
  Dos notas el mismo día = ficheros distintos → sin conflictos de merge.
- El índice `00-MOC.md` se genera con **Dataview**: no edites listas a mano.

## Frontmatter (YAML, lo lee Dataview)

Comunes: `type, title, date (AAAA-MM-DD), author (marcv|marcs), status
(draft|review|final), tags, related []`. Específicos por tipo en cada plantilla.
Al crear una nota tú (Claude), **rellena los valores**: no dejes tags `<% %>` de
Templater (esos solo se resuelven en la GUI de Obsidian).

## Cómo crear una nota (Claude)

1. Copia la plantilla correcta de `_templates/` al destino con el nombre
   `AAAA-MM-DD-<slug>-<autor>.md`.
2. Rellena frontmatter + cuerpo. Para un **briefing**, el cuerpo es el bloque de 5
   campos de `/cierre-sesion` (Foco / Avanzado / Bloqueos / Decisiones / Siguiente).
3. **Enlaza** (no recopies) lo que resumas de `Fulgor`.

## Modelo de git (híbrido — distinto a Fulgor)

- **Notas** (briefings/estudios/análisis) → **directo a `main`**. Obsidian Git hace
  pull al abrir + commit-and-sync ~90 s. Desde Claude:
  ```bash
  cd ~/Projects/symbyosis
  git pull --no-rebase
  git add <nota> && git commit -m "briefing: <fecha> <tema>" && git push
  ```
- **Estructura** (protocolo en `equipo/`, plantillas `_templates/`, `.obsidian/`,
  README/CLAUDE) → **rama → PR → merge** (que lo vea el otro antes).
- No hay `git-guard`. Sí `pre-commit` (secretos + > 2 MB, con excepción para
  `.obsidian/plugins/`). Conventional commits.

## Estudios: reutiliza, no inventes

- Para un estudio de mercado/técnico, usa la skill global **`deep-research`** y
  vuelca el resultado en una nota `market-study` / `technical-study` (con `sources`
  = url + fecha de consulta).
- Los agentes `business-analyst` / `architect` de `Fulgor` siguen valiendo.

## Sincronización con Marc S

Repo compartido: Marc S clona, abre en su Obsidian (plugins vendados) y su Obsidian
Git mantiene el sync con su PAT `SYMBYOSIS-VAULT` (R/W solo en este repo).
Notificaciones entre sesiones = app de GitHub + *Watch*. Ver
`equipo/handoff-marc-s.md` en el vault.
