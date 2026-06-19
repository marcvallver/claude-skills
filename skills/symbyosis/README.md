# symbyosis (skill)

Disciplina para el vault de coordinación **`b2c-mvms/symbyosis`** (repo git +
Obsidian), donde Marc V y Marc S comparten briefings y estudios/análisis de
project-beta. La definición está en [`SKILL.md`](SKILL.md).

## Qué hace

- Codifica la **taxonomía** del vault (briefings / studies / analyses / equipo),
  el **frontmatter** YAML (para Dataview) y los **nombres anti-conflicto**
  (`AAAA-MM-DD-<slug>-<autor>.md`).
- Impone la **regla de frontera** con `proyecto-beta`: *enlaza, no recopies*; lo
  maduro se promociona a producto; cero PII; source-honesty.
- Fija el **modelo de git híbrido**: notas directas a `main` (auto-sync de Obsidian
  Git); cambios estructurales por rama → PR.

## No duplica

Las **plantillas** viven en el propio repo (`_templates/`), un solo hogar: la skill
las referencia, no las copia. Para producir estudios reusa la skill global
**`deep-research`**; para briefings, el cuerpo es el de `/cierre-sesion`.

## Cableado

Contenido aquí (`~/Projects/claude-skills/skills/symbyosis/`), symlinkeado a
`~/dotfiles/.claude/skills/symbyosis` → resuelto en `~/.claude/skills/symbyosis`
(sistema híbrido). Ver `~/dotfiles/.claude/README.md`.
