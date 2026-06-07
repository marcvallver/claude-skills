// Cabecera typst inyectada por notebooklm-export (pandoc -H).
// pandoc envuelve cada tabla markdown en un #figure, y en typst los bloques de figure
// NO se parten entre páginas por defecto: una tabla más alta que el espacio restante se
// SOLAPA en vez de continuar en la página siguiente. Esto la hace divisible y arregla el
// solape en tablas largas.
#show figure: set block(breakable: true)
