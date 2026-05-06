import os
import random
import sys
import json
import re
import time
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

# ==============================
# 1. DEFINICIÍN DE VARIABLES
# ==============================


MODEL = "gpt-4o-mini"
MAX_HALLAZGOS = 10

# ==============================
# 2. LISTAS DE DOMINIOS
# ==============================

ALLOWED_SITES = [
    "bbc.com", "larepublica.pe", "elpais.com", "theguardian.com",
    "nytimes.com", "cnn.com", "elcomercio.pe", "gestion.pe"
]

ONGS = [
    "greenpeace.org", "amnesty.org", "transparency.org", "humanrights.org",
    "ecowatch.com", "banktrack.org", "peru.wcs.org", "reddearboles.org", "mongabay.com", "worldwildlife.org"
]

SOCIAL_SITES = [
    "facebook.com", "x.com", "twitter.com", "instagram.com", "linkedin.com", "tiktok.com"
]

OMITIR_SITIOS = [
    "wikipedia.com"
]

# ==============================
# 3. FUNCIÓN DE CONSULTA
# ==============================

def consultar_openai(user_prompt, max_retries=3, delay=5):
    """Consulta al modelo con búsqueda web y maneja estructuras mixtas de respuesta."""
    for intento in range(max_retries):
    
        try:
            response = client.responses.create(
                model=MODEL,
                input=user_prompt,
                tools=[{"type": "web_search"}],
                temperature=0.1,
                top_p=1.0,
            )
            

            if hasattr(response, "output_text") and response.output_text:
                return response.output_text.strip()

            output_parts = []
            if hasattr(response, "output") and response.output:
                for item in response.output:
                    content = getattr(item, "content", None)
                    if isinstance(content, list):
                        for c in content:
                            text_fragment = getattr(c, "text", None) or getattr(c, "content", None)
                            if text_fragment:
                                output_parts.append(str(text_fragment).strip())

            if output_parts:
                return " ".join(output_parts).strip()

            return str(response)
        except Exception as e:
            
            error_msg = str(e)
            print(f"[Intento {intento+1}/{max_retries}] Alerta consultando OpenAI: {error_msg}")
            
            if intento < max_retries - 1:
                wait_time = delay + random.uniform(0, 3)
                print(f"Reintentando en {wait_time:.1f} segundos...")
                time.sleep(wait_time)
            else:
                print("ERROR: No se pudo obtener respuesta tras varios intentos.")
                return None
            

# ==============================
# 4. PARSEO ROBUSTO DE JSON
# ==============================

def extraer_json_valido(texto):
    """Extrae el primer bloque JSON válido incluso si hay texto adicional."""
    if not texto:
        return []

    coincidencias = re.findall(r'\[.*\]', texto, flags=re.DOTALL)
    for bloque in coincidencias:
        try:
            data = json.loads(bloque)
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            continue
    return []

# ==============================
# 5. PROMPT REPUTACIONAL (GENÉRICO)
# ==============================

def generar_prompt(pais, doc, nombre, dominios, tipo):
    return f"""
Eres un analista de riesgo reputacional.

Tarea:
1) Usa BÚSQUEDA WEB SOLO en estos dominios {', '.join(dominios)}. Da PRIORIDAD a estos dominios. Si no encuentras nada allí, puedes usar otros medios confiables.
2) Busca noticias o reportes NEGATIVOS relacionados con la entidad (persona o empresa) relacionadas a una o más palabras: Corrupción, Denuncias, Quejas, Lavado, Multas, Discriminación, Violación o Abuso.
3) Para cada hallazgo, clasifica el riesgo (Alto, Medio o Bajo) según gravedad/relevancia/evidencia.
4) Devuelve SOLO JSON válido (una lista). Si no hay hallazgos, devuelve [] y NADA MÁS.

Campos por hallazgo (JSON):
- sitio (dominio, ej: "bbc.com")
- url (absoluta)
- título (breve)
- extracto (2–4 frases concisas con lo esencial del caso)
- nivel_riesgo ("Alto" | "Medio" | "Bajo")
- fecha (string ISO 'YYYY-MM-DD'; si no se conoce exacta, usa la más cercana o deja "")
- categorias (lista; usa SOLO valores de: ["Corrupción","Denuncias","Quejas","Lavado","Multas","Discriminación","Violación","Abuso"]; puede ser lista vacía [])

Reglas:
- Máximo {MAX_HALLAZGOS} hallazgos.
- No inventes; si dudas de la correspondencia con la entidad, exclúyelo.
- NO incluyas texto fuera del JSON.
- Responde ÚNICAMENTE con la lista JSON.

Entidad:
- País: {pais}
- DOI/RUC/DNI: {doc}
- Nombre: {nombre}
"""

# ==============================
# 5B. PROMPT ESPECÍFICO PARA ONGs
# ==============================

def generar_prompt_ongs(pais, doc, nombre, dominios):
    return f"""
Eres un analista reputacional.

Tu tarea es usar la BÚSQUEDA WEB exclusivamente en estos dominios de ONGs y fuentes internacionales: {', '.join(dominios)}.

Objetivo:
- Recupera **toda información relevante o verificable** relacionada con la entidad (persona o empresa), sin limitarte a categorías de riesgo específicas.
- Considera temas ambientales, sociales, de derechos humanos, sostenibilidad o gobernanza mencionados por las ONGs.
- No inventes información ni enlaces.

Formato de salida: SOLO JSON válido (lista de objetos), con los siguientes campos:
[
  {{
    "sitio": "[Dominio]",
    "url": "[Enlace completo]",
    "titulo": "[Título o resumen breve]",
    "resumen": "[Texto relevante encontrado]",
    "relevancia": "[Alta | Media | Baja]",
    "fecha_publicacion": "[YYYY-MM-DD o vacío]"
  }}
]

Reglas:
- Máximo {MAX_HALLAZGOS} resultados.
- Excluye duplicados o menciones sin evidencia.
- No incluyas texto fuera del JSON.
- Si no hay resultados, devuelve [].

Entidad:
- País: {pais}
- Documento: {doc}
- Nombre: {nombre}
"""

# ==============================
# 6. PROMPT INFORMACIÓN DETALLADA
# ==============================

def generar_prompt_informacion_entidad(pais, doc, nombre, sitios_omitir):
    sitios_omitir_texto = ", ".join(sitios_omitir) if sitios_omitir else "Ninguno"
    return f"""
Actúa como un asistente experto en investigación de entidades y entrega información **verificada y confiable** en formato **JSON plano tipo lista**. Recibirás como entrada:

- Nombre o razón social de la entidad: {nombre}
- Documento de identificación (DNI, RUC, DOI, etc.): {doc}
- País de la entidad: {pais}
- Sitios web a omitir durante la búsqueda (opcional): {sitios_omitir_texto}

Tu tarea es generar un **JSON tipo lista** con la siguiente estructura:
[
  {{
    "nombre_entidad": "[Nombre completo de la entidad]",
    "descripcion_breve": "[Texto completo y detallado sobre la entidad, incluyendo formación académica, experiencia profesional, logros y roles principales, al final añadir FUENTE: urls separadas por comas]",
    "lineas_negocio": "[Todas las actividades, responsabilidades, proyectos o áreas de operación relevantes, al final añadir FUENTE: urls separadas por comas]",
    "estructura_organizacional": "[Listado de cargos y, si se conoce, la persona que ocupa cada cargo, separados por punto y coma, al final añadir FUENTE: urls separadas por comas]",
    "principales_accionistas": "[Texto narrativo completo describiendo los principales accionistas, incluyendo % de participación y rol o influencia de cada uno, al final añadir FUENTE: urls separadas por comas]",
    "empresas_del_grupo": "[Texto narrativo completo describiendo las empresas que conforman el grupo, indicando su función o rol dentro del conglomerado; si la entidad no es un grupo, colocar 'No aplica'; al final añadir FUENTE: urls separadas por comas]",
    "mercado_valores": "[Texto resumen de la información de mercado, código/ticker y nombre de la empresa si aplica; al final añadir FUENTE: urls separadas por comas]",
    "geografia_sede": "[Ubicación de la sede principal de la entidad, ciudad y región; al final añadir FUENTE: urls separadas por comas]",
    "paises_operacion": "[Países en los que la entidad desarrolla actividades; al final añadir FUENTE: urls separadas por comas]",
    "sector_sensible": "[Texto resumen seguido de la explicación narrativa sobre la política aplicable y detalles de riesgos o regulaciones; al final añadir FUENTE: urls separadas por comas]"
  }}
]

Reglas:
- Mantén un lenguaje claro, conciso y profesional, adaptado para reportes automatizados.
- Detecta si es grupo empresarial (si no, coloca “No aplica” en empresas_del_grupo)
- Prioriza sitios oficiales (.gov, .edu, .org, sitios de la entidad, Bloomberg, Reuters, etc.)
- No uses sitios en la lista de omisión
- Si no hay información, coloca “No se encontró información”
- Responde SOLO con JSON válido y plano
- Para información de mercado de valores, usar MarketScreener, Bloomberg, Reuters, Yahoo Finance u otras confiables
"""

# ==============================
# PROMPT REDES SOCIALES
# ==============================

def generar_prompt_redes(pais, doc, nombre, dominios):
    return f"""
Eres un analista de riesgo reputacional.

Tarea:
1) Usa BÚSQUEDA WEB SOLO en estos dominios de Redes Sociales: {', '.join(dominios)}.
2) Busca menciones/denuncias/controversias relevantes vinculadas a la entidad (persona o empresa).
3) Para cada hallazgo, clasifica el riesgo (Alto, Medio o Bajo) según gravedad/relevancia/evidencia.
4) Devuelve SOLO JSON válido (una lista). Si no hay hallazgos, devuelve [] y NADA MÁS.

Campos por hallazgo (JSON):
- sitio (dominio, ej: "twitter.com")
- url (absoluta al post o página)
- título (si no hay título, usa un resumen muy breve del post)
- extracto (2–4 frases con la acusación o evidencia principal)
- nivel_riesgo ("Alto" | "Medio" | "Bajo")
- fecha (string ISO 'YYYY-MM-DD' si es posible; o "")
- categorias (lista; usa SOLO valores de: ["Corrupción","Denuncias","Quejas","Lavado","Multas","Discriminación","Violación","Abuso"]; puede ser lista vacía [])

Reglas:
- Máximo {MAX_HALLAZGOS} hallazgos.
- Evita duplicados y baja calidad (spam, sin evidencia).
- NO incluyas texto fuera del JSON.
- Responde ÚNICAMENTE con la lista JSON.

Entidad:
- País: {pais}
- DOI/RUC/DNI: {doc}
- Nombre: {nombre}
"""

# ==============================
# 7. CONSULTAS
# ==============================

def consultar_informacion_entidad(entidad, sitios_omitir=OMITIR_SITIOS):
    prompt = generar_prompt_informacion_entidad(
        pais=entidad["pais"],
        doc=entidad["doi_ruc_dni"],
        nombre=entidad["nombre"],
        sitios_omitir=sitios_omitir
    )
    respuesta = consultar_openai(prompt)
    return extraer_json_valido(respuesta)

def analizar_entidad(entidad, dominios, tipo):
    prompt = generar_prompt(
        pais=entidad["pais"],
        doc=entidad["doi_ruc_dni"],
        nombre=entidad["nombre"],
        dominios=dominios,
        tipo=tipo
    )
    respuesta = consultar_openai(prompt)
    return extraer_json_valido(respuesta)

def analizar_entidad_ongs(entidad, dominios):
    """Versión especializada para ONGs: usa el prompt dedicado."""
    prompt = generar_prompt_ongs(
        pais=entidad["pais"],
        doc=entidad["doi_ruc_dni"],
        nombre=entidad["nombre"],
        dominios=dominios
    )
    respuesta = consultar_openai(prompt)
    return extraer_json_valido(respuesta)


# ==============================
# FUNCIÓN PARA ANALIZAR REDES SOCIALES
# ==============================

def analizar_entidad_redes(entidad, dominios):
    prompt = generar_prompt_redes(
        pais=entidad["pais"],
        doc=entidad["doi_ruc_dni"],
        nombre=entidad["nombre"],
        dominios=dominios
    )
    respuesta = consultar_openai(prompt)
    return extraer_json_valido(respuesta)

# ==============================
# 8. EXPANDIR CATEGORÍAS
# ==============================

def expandir_categorias(df):
    """Expande las categorías a columnas binarias sin fallar si el formato varía."""
    categorias = ["Corrupción", "Denuncias", "Quejas", "Lavado", "Multas", "Discriminación","Violación","Abuso"]

    # Asegurar que df sea un DataFrame
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame(columns=categorias)

    # Si la columna no existe, crearla vacía
    if "categorias" not in df.columns:
        df["categorias"] = [[] for _ in range(len(df))]

    # Normalizar la columna a listas
    df["categorias"] = df["categorias"].apply(
        lambda x: x if isinstance(x, list)
        else ([x] if isinstance(x, str) and x.strip() else [])
    )

    # Crear columnas binarias
    for cat in categorias:
        df[cat] = df["categorias"].apply(lambda x: 1 if cat in x else 0)

    # 🔹 Limpiar comillas en títulos (dobles y simples)
    if "titulo" in df.columns:
        df["titulo"] = (
            df["titulo"]
            .astype(str)
            .str.replace(r"^[\"']|[\"']$", "", regex=True)
            .str.strip()
        )

    return df

# ==============================
# 9. PROCESAMIENTO PRINCIPAL
# ==============================

def analizar_entidades(csv_path):
    df_entidades = pd.read_csv(csv_path)
    resultados_medios, resultados_ongs, resultados_social, resultados_info = [], [], [], []

    for _, row in df_entidades.iterrows():
        entidad = {"pais": row["pais"], "doi_ruc_dni": row["doi_ruc_dni"], "nombre": row["nombre"]}
        print(f"Analizando: {entidad['nombre']}")

        medios = analizar_entidad(entidad, ALLOWED_SITES, "medios confiables")
        for item in medios:
            item.update(entidad)
        resultados_medios.extend(medios)

        # NUEVO: prompt especializado para ONGs
        ongs = analizar_entidad_ongs(entidad, ONGS)
        for item in ongs:
            item.update(entidad)
        resultados_ongs.extend(ongs)

        social = analizar_entidad_redes(entidad, SOCIAL_SITES)
        for item in social:
            item.update(entidad)
        resultados_social.extend(social)

        info = consultar_informacion_entidad(entidad)
        for item in info:
            item.update(entidad)
        resultados_info.extend(info)

    return resultados_medios, resultados_ongs, resultados_social, resultados_info

# ==============================
# 10B. EXPORTACIÓN A JSON
# ==============================
# guardar todos los resultados en un solo JSON
def guardar_json_consolidado(resultados, archivo_path):
    """Guarda todos los hallazgos en un solo archivo JSON"""
    folder = os.path.dirname(archivo_path)
    if folder and not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)
    with open(archivo_path, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=4)
    print(f"{len(resultados)} hallazgos guardados en '{archivo_path}'")


# ==============================
# 11. FILTRAR RESULTADOS DUPLICADOS
# ==============================

def eliminar_duplicados(resultados, campo_titulo="titulo", campo_fecha="fecha"):
    """
    Elimina elementos repetidos según el título y la fecha.
    - resultados: lista de diccionarios
    - campo_titulo: nombre de la clave que contiene el título del hallazgo
    - campo_fecha: nombre de la clave que contiene la fecha (ISO 'YYYY-MM-DD')
    Devuelve una lista filtrada sin duplicados.
    """
    vistos = set()
    resultados_filtrados = []

    for item in resultados:
        titulo = str(item.get(campo_titulo, "")).strip().lower()
        fecha = str(item.get(campo_fecha, "")).strip()
        key = (titulo, fecha)
        if key not in vistos:
            vistos.add(key)
            resultados_filtrados.append(item)

    return resultados_filtrados

# ==============================
# 10C. PROCESAMIENTO PRINCIPAL + JSON
# ==============================
if __name__ == "__main__":
    # ------- Leer argumentos -------
    if len(sys.argv) != 4:
        print("ERROR: Parámetros incorrectos")
        print("Uso: AgenteDeRiesgos.py <api_key> <ruta_csv_entrada> <ruta_carpeta_salida>")
        print("Ejemplo: AgenteDeRiesgos.py \"sk-xxxxx\" \"C:\\datos\\entidades.csv\" \"C:\\salidas\"")
        sys.exit(1)

    api_key = sys.argv[1]
    csv_file = sys.argv[2]
    output_dir = sys.argv[3]

    # Validar API Key
    if not api_key or not api_key.startswith("sk-"):
        raise ValueError("ERROR: API Key no válida o no proporcionada correctamente.")

    # Crear cliente con la API key recibida
    client = OpenAI(api_key=api_key)

    # Validar input
    if not os.path.exists(csv_file):
        raise FileNotFoundError(f"ERROR: No se encontró el archivo de entrada: {csv_file}")

    # Crear carpeta de salida si no existe
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        raise OSError(f"ERROR: No se pudo crear la carpeta de salida '{output_dir}': {e}")

    # ==============================
    # 1. Analizar entidades
    # ==============================
    medios, ongs, social, info = analizar_entidades(csv_file)

    # ==============================
    # 2️. Eliminar duplicados por título y fecha
    # ==============================
    medios = eliminar_duplicados(medios, campo_titulo="titulo", campo_fecha="fecha")
    social = eliminar_duplicados(social, campo_titulo="titulo", campo_fecha="fecha")
    ongs = eliminar_duplicados(ongs, campo_titulo="titulo", campo_fecha="fecha_publicacion")
    info = eliminar_duplicados(info, campo_titulo="nombre_entidad", campo_fecha="fecha_publicacion")

    # ==============================
    # 3️. Expandir categorías
    # ==============================
    df_medios = expandir_categorias(pd.DataFrame(medios))
    df_social = expandir_categorias(pd.DataFrame(social))
    df_ongs = pd.DataFrame(ongs)
    df_info = pd.DataFrame(info)

    # ==============================
    # 4️. Guardar Excel consolidado
    # ==============================
    excel_path = os.path.join(output_dir, "resultados_riesgo.xlsx")

    with pd.ExcelWriter(excel_path) as writer:
        df_medios.to_excel(writer, sheet_name="Medios_Allowed", index=False)
        df_ongs.to_excel(writer, sheet_name="ONGS", index=False)
        df_social.to_excel(writer, sheet_name="Redes_Sociales", index=False)
        df_info.to_excel(writer, sheet_name="Info_Entidad", index=False)

    print(f"Análisis completado y exportado a Excel: {excel_path}")

    # ==============================
    # 5️. Guardar JSON consolidados
    # ==============================
    guardar_json_consolidado(medios, os.path.join(output_dir, "medios.json"))
    guardar_json_consolidado(ongs, os.path.join(output_dir, "ongs.json"))
    guardar_json_consolidado(social, os.path.join(output_dir, "social.json"))
    guardar_json_consolidado(info, os.path.join(output_dir, "info.json"))

    print("Proceso finalizado.")