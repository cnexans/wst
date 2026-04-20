# Skill: wst CLI

CLI para organizar PDFs/libros con metadata generada por IA, búsqueda full‑text (SQLite FTS) y backups (iCloud/S3).

## Instalación

### pipx (recomendado)

```bash
pipx install wst-library
```

### pip

```bash
pip install wst-library
```

### Extras opcionales

- OCR:

```bash
pip install "wst-library[ocr]"
```

- S3 backup:

```bash
pip install "wst-library[s3]"
```

## Output para humanos vs máquinas

Todos los comandos aceptan `--format human|md|json|yaml` (default `human`).

- `--format human`: pensado para terminal (tablas, mensajes, progreso).
- `--format md|json|yaml`: pensado para automatización.
  - No hay prompts interactivos.
  - La salida es determinística (sin barras de progreso).
  - El payload es estable:
    - Éxito: `{ "ok": true, "data": ... }`
    - Error: `{ "ok": false, "error": { "code": ..., "message": ..., "details": ... } }`

## Comandos principales (no interactivos)

### Listar

```bash
wst list
wst list --format json
wst list --type paper --sort year --format yaml
```

### Buscar

```bash
wst search "machine learning"
wst search "cosmos" --author "Sagan" --format json
```

### Mostrar metadata completa

```bash
wst show 3
wst show 3 --format yaml
```

### Ingesta

```bash
wst ingest
wst ingest ~/Downloads/book.pdf
wst ingest --ocr --ocr-language spa
wst ingest --format json
```

Notas:
- `--confirm` es interactivo (pregunta por archivo). Evitar en pipelines.
- `-v/--verbose` imprime logs por archivo (útil para debugging humano).

### OCR

```bash
wst ocr scan.pdf --format json
wst ocr ~/scans -l spa+eng --format yaml
```

### Enriquecer metadata en lote

```bash
wst fix --dry-run --format json
wst fix -y --format yaml
```

## Comandos interactivos (y alternativas scriptables)

### `wst browse`

- Interactivo:

```bash
wst browse
```

- Scriptable (sin prompts):

```bash
wst browse --id 3 --action view --format json
wst browse --query "cosmos" --first --action view --format yaml
wst browse --id 3 --action open --no-launch --format json
wst browse --id 3 --action delete --dry-run --format md
wst browse --id 3 --action delete -y --format json
wst browse --id 3 --action edit --set title="New" --dry-run --format json
wst browse --id 3 --action edit --set title="New" -y --format json
```

### `wst edit`

- Interactivo por defecto:

```bash
wst edit 3
```

- No interactivo:

```bash
wst edit 3 --set title="New title" --dry-run --format json
wst edit 3 --set title="New title" -y --format yaml
wst edit 3 --enrich -y --format json
```

## Backup (consideraciones)

En general, el setup/configuración puede requerir modo humano.

```bash
# S3 configure: interactivo
wst backup s3 --configure --format human

# Backup por ID/título (scriptable)
wst backup s3 3 --format json
wst backup icloud "Cosmos" --format yaml
```

## Reglas para IA (operación segura y reproducible)

- Preferir **IDs** (`wst list`/`wst search`) para seleccionar documentos en vez de títulos aproximados.
- En `--format md|json|yaml`, evitar cualquier comando que requiera prompts; usar `-y`, `--dry-run`, `--set` según corresponda.
- Para acciones potencialmente destructivas:
  - usar `--dry-run` primero cuando exista
  - exigir `-y/--yes` para aplicar
- Para `open/find` desde automatización, usar `--no-launch` para no abrir apps.

