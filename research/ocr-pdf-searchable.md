# Proceso: Convertir PDFs escaneados en PDFs buscables (searchable)

## Problema

Los PDFs generados por escaneo (CamScanner, escaner fisico, fotos de documentos) contienen solo imagenes. No se puede buscar texto, seleccionar ni copiar contenido. Esto aplica a apuntes universitarios, documentos legales, libros escaneados, etc.

## Solucion

Agregar una **capa de texto invisible** (text layer) sobre las imagenes del PDF usando OCR (Optical Character Recognition). El PDF resultante se ve identico al original pero es completamente buscable y seleccionable.

## Archivos de ejemplo

| Archivo | Descripcion |
|---|---|
| `ejemplo_original.pdf` | PDF escaneado original (27 paginas, sin texto buscable) |
| `ejemplo_searchable.pdf` | PDF procesado con capa de texto OCR |

---

## Herramientas necesarias

### 1. ocrmypdf (herramienta principal)

Toma un PDF escaneado y produce un PDF con capa de texto OCR. Internamente usa Tesseract para el reconocimiento y Ghostscript para la manipulacion del PDF.

**Instalacion en macOS:**

```bash
# Opcion 1: via pipx (recomendada - evita conflictos de dependencias)
pipx install ocrmypdf

# Opcion 2: via Homebrew
brew install ocrmypdf
```

**Instalacion en Linux (Debian/Ubuntu):**

```bash
apt install ocrmypdf
```

**Dependencias que se instalan automaticamente:**
- Tesseract OCR (motor de reconocimiento)
- Ghostscript (manipulacion de PDFs)
- Unpaper (limpieza de imagenes, opcional)

### 2. Paquetes de idioma de Tesseract

Por defecto Tesseract solo incluye ingles. Para otros idiomas:

```bash
# macOS
brew install tesseract-lang

# Linux
apt install tesseract-ocr-spa   # espanol
apt install tesseract-ocr-por   # portugues
apt install tesseract-ocr-fra   # frances
# etc.
```

**Verificar idiomas disponibles:**

```bash
tesseract --list-langs
```

### 3. Herramientas auxiliares (opcionales, para diagnostico)

```bash
# Verificar si un PDF ya tiene texto extraible
# Si no devuelve nada o muy poco, es un PDF de imagenes
pdftotext input.pdf - | head -20

# Ver cantidad de paginas
pdfinfo input.pdf | grep Pages

# Convertir paginas a imagenes (util para inspeccion visual)
# Requiere poppler: brew install poppler
pdftoppm -png -r 300 input.pdf output_prefix
```

---

## Proceso paso a paso

### Paso 1: Diagnosticar el PDF

Antes de procesar, verificar que el PDF realmente necesita OCR:

```bash
pdftotext "documento.pdf" - | head -50
```

- Si devuelve texto coherente y completo: el PDF ya tiene texto, no necesita OCR.
- Si devuelve muy poco texto, texto basura, o nada: es un PDF de imagenes, necesita OCR.

Tambien verificar el tamano del trabajo:

```bash
pdfinfo "documento.pdf" | grep Pages
```

### Paso 2: Ejecutar ocrmypdf

**Comando basico:**

```bash
ocrmypdf -l spa "entrada.pdf" "salida_searchable.pdf"
```

**Comando completo (recomendado para escaneos):**

```bash
ocrmypdf \
  -l spa \
  --force-ocr \
  --output-type pdf \
  "entrada.pdf" \
  "salida_searchable.pdf"
```

**Parametros explicados:**

| Parametro | Descripcion |
|---|---|
| `-l spa` | Idioma del texto. Usar codigo ISO 639-3: `spa` (espanol), `eng` (ingles), `por` (portugues), `fra` (frances). Para multiples idiomas: `-l spa+eng` |
| `--force-ocr` | Fuerza OCR en todas las paginas, incluso si alguna ya tiene texto. Util para PDFs mixtos o con texto parcial incorrecto |
| `--output-type pdf` | Genera PDF estandar (no PDF/A). Usar `pdfa` si se necesita archivado a largo plazo |
| `--skip-text` | Alternativa a `--force-ocr`: salta paginas que ya tienen texto, solo procesa las que no tienen |
| `--deskew` | Corrige inclinacion de paginas torcidas |
| `--clean` | Limpia la imagen antes del OCR (elimina ruido) |
| `--rotate-pages` | Auto-detecta y corrige paginas rotadas |
| `-j N` | Numero de workers paralelos (default: numero de CPUs) |

### Paso 3: Verificar el resultado

```bash
# Verificar que el texto es extraible
pdftotext "salida_searchable.pdf" - | head -50

# Comparar tamanos
ls -lh "entrada.pdf" "salida_searchable.pdf"
```

### Paso 4 (opcional): Extraer texto a Markdown

Si ademas del PDF searchable se quiere un archivo de texto/markdown:

```bash
# Paso 4a: Convertir paginas a imagenes de alta resolucion
mkdir temp_pages
pdftoppm -png -r 300 "entrada.pdf" temp_pages/page

# Paso 4b: Aplicar Tesseract a cada imagen
for f in temp_pages/page-*.png; do
    tesseract "$f" stdout -l spa
done > texto_crudo.txt

# Paso 4c: Limpiar y formatear manualmente el texto a Markdown
# (este paso requiere revision humana o un LLM para formatear)

# Paso 4d: Limpiar archivos temporales
rm -rf temp_pages texto_crudo.txt
```

---

## Ejemplo real ejecutado

### Contexto

- **Archivo:** `Unidad 1 y 2 Geometria I.pdf` (apuntes universitarios de geometria)
- **Paginas:** 27
- **Origen:** Escaneado con CamScanner (cada pagina es una imagen)
- **Idioma:** Espanol

### Comandos ejecutados

```bash
# 1. Diagnostico
pdftotext "Unidad 1 y 2 Geometria I.pdf" - | head -50
# Resultado: solo una linea de texto -> confirma que es PDF de imagenes

pdfinfo "Unidad 1 y 2 Geometria I.pdf" | grep Pages
# Resultado: Pages: 27

# 2. Verificar Tesseract tiene espanol
tesseract --list-langs | grep spa
# Resultado: spa

# 3. Ejecutar OCR
ocrmypdf -l spa --force-ocr \
  "Unidad 1 y 2 Geometria I.pdf" \
  "Unidad 1 y 2 Geometria I_searchable.pdf"

# 4. Verificar
pdftotext "Unidad 1 y 2 Geometria I_searchable.pdf" - | head -20
# Resultado: texto completo y coherente
```

### Resultado

- El PDF original no permitia buscar ni seleccionar texto
- El PDF resultante es visualmente identico pero completamente buscable
- Reduccion de tamano del 16.4% en imagenes
- Tiempo de procesamiento: ~2 minutos para 27 paginas

---

## Problemas conocidos y soluciones

### ocrmypdf falla con error de expat/XML en macOS

```
ImportError: No module named expat; use SimpleXMLTreeBuilder instead
```

**Causa:** Conflicto entre la version de Python de Homebrew (3.14) y la libreria del sistema `libexpat`.

**Solucion:** Instalar ocrmypdf con `pipx` en vez de `brew`, que usa Python 3.13:

```bash
pipx install ocrmypdf
# Usar: ~/.local/bin/ocrmypdf en vez de /opt/homebrew/bin/ocrmypdf
```

### DPI bajo en escaneos de CamScanner

Los escaneos de CamScanner suelen tener DPI variable (~91 DPI promedio). ocrmypdf muestra warnings pero procesa correctamente. Para mejorar la calidad del OCR en estos casos:

```bash
ocrmypdf -l spa --force-ocr --oversample 300 "entrada.pdf" "salida.pdf"
```

El flag `--oversample 300` re-renderiza las imagenes a 300 DPI antes del OCR.

### Paginas torcidas o con ruido

```bash
ocrmypdf -l spa --force-ocr --deskew --clean "entrada.pdf" "salida.pdf"
```

### PDF muy grande (muchas paginas)

Para PDFs de cientos de paginas, considerar:

```bash
# Limitar workers para no saturar la memoria
ocrmypdf -l spa --force-ocr -j 4 "entrada.pdf" "salida.pdf"

# O procesar por rangos de paginas con qpdf
qpdf --pages "entrada.pdf" 1-50 -- temp_1.pdf
ocrmypdf -l spa --force-ocr temp_1.pdf salida_1.pdf
```

---

## Para automatizacion

### Comando minimo para un script

```bash
ocrmypdf -l spa --force-ocr --skip-text "$INPUT" "$OUTPUT"
```

### Procesamiento en lote

```bash
#!/bin/bash
# Procesar todos los PDFs en una carpeta
INPUT_DIR="./pdfs_escaneados"
OUTPUT_DIR="./pdfs_searchable"
mkdir -p "$OUTPUT_DIR"

for pdf in "$INPUT_DIR"/*.pdf; do
    filename=$(basename "$pdf")
    echo "Procesando: $filename"
    ocrmypdf -l spa --force-ocr "$pdf" "$OUTPUT_DIR/$filename"
done
```

### Deteccion automatica de idioma

Si se procesan documentos en multiples idiomas, usar varios idiomas:

```bash
ocrmypdf -l spa+eng+por --force-ocr "$INPUT" "$OUTPUT"
```

### Codigo de salida

| Codigo | Significado |
|---|---|
| 0 | Exito |
| 1 | Error de argumentos |
| 2 | El archivo de entrada no es un PDF valido |
| 4 | El PDF tiene texto y se uso el modo por defecto (no --force-ocr ni --skip-text) |
| 6 | El archivo ya fue procesado con OCR |
| 15 | Error interno (ver logs) |

### Validacion del resultado

Para verificar programaticamente que el OCR funciono:

```bash
# Contar palabras extraidas
WORD_COUNT=$(pdftotext "$OUTPUT" - | wc -w)
if [ "$WORD_COUNT" -gt 100 ]; then
    echo "OK: $WORD_COUNT palabras extraidas"
else
    echo "WARN: Solo $WORD_COUNT palabras, revisar resultado"
fi
```
