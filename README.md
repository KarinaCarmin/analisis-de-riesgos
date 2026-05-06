# 🔍 Agente de Análisis de Riesgo Reputacional

Script de Python que automatiza el análisis reputacional de personas o empresas usando la API de OpenAI con búsqueda web en tiempo real. A partir de un listado de entidades en CSV, el agente consulta múltiples fuentes (medios de comunicación, ONGs, redes sociales) y genera un reporte consolidado en Excel y JSON.

## ¿Qué hace?

- Recibe un archivo CSV con entidades (nombre, documento, país)
- Realiza búsquedas web segmentadas en:
  - **Medios confiables** (BBC, El Comercio, NYT, CNN, etc.)
  - **ONGs internacionales** (Greenpeace, Amnesty, Transparency, etc.)
  - **Redes sociales** (LinkedIn, X, Facebook, etc.)
- Clasifica hallazgos negativos por categoría: Corrupción, Lavado, Multas, Denuncias, entre otros
- Asigna nivel de riesgo: `Alto`, `Medio` o `Bajo`
- Elimina duplicados automáticamente
- Exporta resultados a **Excel** (4 hojas) y **JSON**

## Tecnologías

- Python · OpenAI API · Pandas · Web Search Tool

## Uso

```bash
python analisis-de-riesgos.py "sk-xxxxx" "entidades.csv" "carpeta_salida/"
```

### Formato del CSV de entrada

```csv
nombre,doi_ruc_dni,pais
Empresa Ejemplo S.A.,201111111,Peru
```

## Output

| Archivo | Contenido |
|---|---|
| `resultados_riesgo.xlsx` | Hallazgos por fuente en 4 hojas |
| `medios.json` | Hallazgos en medios de comunicación |
| `ongs.json` | Menciones en organizaciones internacionales |
| `social.json` | Presencia en redes sociales |
| `info.json` | Información general de la entidad |
