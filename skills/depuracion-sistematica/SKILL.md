---
name: depuracion-sistematica
description: Disciplina de depuración. Úsala ante cualquier bug, fallo de test, build roto o comportamiento inesperado, ANTES de proponer arreglos. Encuentra la causa raíz primero (4 fases), un fix a la vez; si fallan 3 fixes, cuestiona la arquitectura. Adaptada de obra/superpowers (MIT).
---

# Depuración sistemática

> Adaptada de [`obra/superpowers`](https://github.com/obra/superpowers) (Jesse Vincent, MIT),
> al español y condensada. Solo el prompt: ni hooks ni el framework.

Los arreglos al azar gastan tiempo y crean bugs nuevos; los parches rápidos tapan el problema de fondo.

**Principio:** SIEMPRE encuentra la causa raíz antes de tocar nada. Arreglar el síntoma es fallar.

## La regla de hierro

> **No hay fix sin investigar la causa raíz primero.**

Si no has cerrado la Fase 1, no puedes proponer un arreglo.

## Cuándo

Cualquier problema técnico: test rojo, bug en prod, comportamiento raro, rendimiento, build roto,
integración. **Sobre todo** cuando hay prisa, cuando "un arreglo rápido y ya" parece obvio, cuando
ya probaste varios fixes o no entiendes del todo el problema. **No te lo saltes** porque "parece
simple" (los bugs simples también tienen causa raíz) ni porque "hay que arreglarlo YA" (sistemático
es más rápido que dar palos de ciego).

## Las 4 fases (cada una antes de la siguiente)

**1 · Causa raíz** — antes de ningún fix:
- Lee el error ENTERO (stack trace, líneas, códigos — a menudo trae la solución).
- Reprodúcelo de forma fiable; si no es reproducible, reúne más datos, no adivines.
- ¿Qué cambió? (`git diff`, commits recientes, deps nuevas, config, entorno).
- En sistemas multi-componente (CI→build→deploy, API→servicio→DB): **instrumenta cada frontera**
  (qué dato entra / qué sale / propagación de env) en una corrida para ver DÓNDE rompe; luego
  investiga ese componente. Traza el dato hacia atrás hasta su origen y arregla en el origen, no
  en el síntoma.

**2 · Patrón** — encuentra el patrón antes de arreglar:
- Busca código similar que SÍ funciona en el repo.
- Si sigues una referencia, léela **entera**, no en diagonal.
- Lista TODA diferencia entre lo que funciona y lo que no ("eso no puede importar" es la trampa).

**3 · Hipótesis** — método científico:
- Una sola hipótesis, explícita: "creo que X es la causa porque Y".
- Pruébala con el cambio MÁS pequeño posible, una variable a la vez.
- ¿Funcionó? → Fase 4. ¿No? → hipótesis NUEVA, no apiles más fixes encima.
- Si no lo sabes, dilo ("no entiendo X") y busca más; no finjas saberlo.

**4 · Implementación** — arregla la causa, no el síntoma:
- Primero un **test que falle** (la reproducción más simple); tenerlo ANTES de arreglar.
- UN solo fix, a la causa raíz. Sin "ya que estoy" ni refactors de paso.
- Verifica: ¿pasa el test? ¿no rompiste otros? ¿está resuelto de verdad?
- Si el fix no funciona: PARA y cuenta cuántos llevas. Con <3 → vuelve a Fase 1 con lo nuevo.
  **Con ≥3 fixes fallidos → para y cuestiona la ARQUITECTURA** (no es hipótesis fallida, es diseño
  equivocado): ¿el patrón es sano o seguimos por inercia? Decídelo con el humano antes de un fix nº4.

## Banderas rojas — PARA y vuelve a Fase 1

"Un arreglo rápido y luego investigo" · "prueba a cambiar X a ver" · "varios cambios y corro los
tests" · "me salto el test, verifico a mano" · "seguro que es X, lo arreglo" · proponer soluciones
sin trazar el flujo de datos · "un fix más" (con 2+ ya probados) · cada fix revela un problema nuevo
en otro sitio.

Señales del humano de que vas mal: "¿eso no está pasando?" (asumiste sin verificar) · "para de
adivinar" · "ultra-think esto" (cuestiona los fundamentos, no el síntoma) · "¿estamos atascados?".

## Si la investigación dice "no hay causa raíz"

El 95% de esos casos es investigación incompleta. Si de verdad es ambiental / de timing / externo:
documenta qué investigaste, implementa el manejo adecuado (retry, timeout, mensaje de error) y añade
logging/monitorización para la próxima.
