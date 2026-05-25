import os
import asyncio
import httpx
from pathlib import Path
from dotenv import load_dotenv
from openai import AsyncOpenAI
from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

load_dotenv(Path(__file__).parent / ".env")

# ==========================================
# CONFIGURACIÓN Y VARIABLES DE ENTORNO
# ==========================================

app = FastAPI(title="Zendesk Metrics API", description="API para extraer métricas de tickets de Zendesk")

# Configuración de acceso a la API de Zendesk
SUBDOMAIN = os.getenv("ZD_SUBDOMAIN", "domustech")
EMAIL     = os.getenv("ZD_EMAIL", "soporte@domus.la")
API_TOKEN = os.getenv("ZD_API_TOKEN", "TU_TOKEN_AQUI")
BASE_URL  = f"https://{SUBDOMAIN}.zendesk.com/api/v2"
# Formato de autenticación requerido por Zendesk para API Tokens
AUTH      = (f"{EMAIL}/token", API_TOKEN)

# Configuración de la API de OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
openai_client  = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


class GenerateRequest(BaseModel):
    ticket_id: int
    tags: list[str]
    extra_context: Optional[str] = None

# ID del campo personalizado que define la "Causa" del ticket
CUSTOM_FIELD_ID = 1500001726262

# ==========================================
# FUNCIONES AUXILIARES (LÓGICA DE NEGOCIO)
# ==========================================

async def fetch_ticket_ids(client: httpx.AsyncClient, date_from: str, date_to: str, status_filter: str = "solved") -> list[int]:
    """
    Busca IDs de tickets en un rango de fechas y estado específico.
    Implementa paginación automática para obtener todos los resultados.
    """
    query      = f"type:ticket {status_filter}>={date_from} {status_filter}<={date_to}"
    search_url = f"{BASE_URL}/search.json"
    params     = {"query": query}
    ids        = []

    while search_url:
        r = await client.get(search_url, params=params)
        r.raise_for_status()
        data       = r.json()
        # Extraemos solo los IDs de la lista de resultados
        ids       += [t["id"] for t in data.get("results", [])]
        # Zendesk entrega una URL en 'next_page' si hay más de 100 resultados
        search_url = data.get("next_page")
        params     = None  # El link de 'next_page' ya incluye los parámetros

    return ids


async def fetch_metrics(client: httpx.AsyncClient, ticket_id: int, sem: asyncio.Semaphore) -> Optional[dict]:
    """
    Obtiene las métricas de tiempo de resolución para un ticket específico.
    Retorna el tiempo en minutos (calendario y negocio).
    Usa semáforo para respetar el rate limit de Zendesk.
    """
    try:
        async with sem:
            r = await client.get(f"{BASE_URL}/tickets/{ticket_id}/metrics.json")
        if r.status_code != 200:
            return None

        m         = r.json().get("ticket_metric", {})
        frt_first = m.get("first_resolution_time_in_minutes", {}).get("business")
        frt_full  = m.get("full_resolution_time_in_minutes",  {}).get("business")

        if frt_first is None and frt_full is None:
            return None

        return {"ticket_id": ticket_id, "frt_first": frt_first, "frt_full": frt_full}
    except Exception:
        return None


async def fetch_ticket_causa(client: httpx.AsyncClient, date_from: str, date_to: str) -> list[dict]:
    """
    Busca tickets creados en un rango de fechas y extrae el valor del 
    campo personalizado definido en CUSTOM_FIELD_ID.
    """
    query      = f"type:ticket created>={date_from} created<={date_to}"
    search_url = f"{BASE_URL}/search.json"
    params     = {"query": query}
    rows       = []

    while search_url:
        r = await client.get(search_url, params=params)
        r.raise_for_status()
        data = r.json()

        for t in data.get("results", []):
            # Buscamos el campo específico dentro de la lista de custom_fields
            causa = next(
                (f["value"] for f in t.get("custom_fields", []) if f["id"] == CUSTOM_FIELD_ID),
                None
            )
            rows.append({
                "id":     t["id"],
                "estado": t["status"],
                "causa":  causa or "sin_categoria"
            })

        search_url = data.get("next_page")
        params     = None

    return rows

async def fetch_full_ticket_detail(client: httpx.AsyncClient, ticket_id: int) -> Optional[dict]:
    """Fetches a ticket's complete data without truncation, for AI context building.
    Uses sideloading to resolve the requester's name in a single request."""
    r = await client.get(f"{BASE_URL}/tickets/{ticket_id}.json", params={"include": "users"})
    if r.status_code != 200:
        return None
    body          = r.json()
    t             = body.get("ticket", {})
    requester_id  = t.get("requester_id")
    users         = body.get("users", [])
    requester_name = next((u["name"] for u in users if u["id"] == requester_id), "")
    return {
        "id":             t.get("id"),
        "subject":        t.get("subject", ""),
        "status":         t.get("status", ""),
        "description":    t.get("description", ""),
        "requester_name": requester_name,
    }


async def fetch_historical_tickets_for_ai(client: httpx.AsyncClient, tags: list[str], limit: int = 10) -> list[dict]:
    """Fetches the last `limit` solved tickets matching any of the given tags, for AI context."""
    tag_clauses = " ".join(f"tags:{t}" for t in tags)
    r = await client.get(
        f"{BASE_URL}/search.json",
        params={
            "query":      f"type:ticket {tag_clauses} status:solved",
            "sort_by":    "created_at",
            "sort_order": "desc",
            "per_page":   limit,
        },
    )
    r.raise_for_status()
    tickets = []
    for t in r.json().get("results", [])[:limit]:
        tickets.append({
            "id":          t["id"],
            "subject":     t.get("subject", ""),
            "status":      t.get("status", ""),
            "description": t.get("description", ""),
            "tags":        t.get("tags", []),
        })
    return tickets


# ==========================================
# ENDPOINTS DE LA API (FASTAPI)
# ==========================================

@app.get("/api/resolution-metrics")
async def resolution_metrics(date_from: str = Query(...), date_to: str = Query(...)):
    """
    Calcula estadísticas (promedio, mediana, min, max) de tiempo de resolución
    para tickets resueltos en el rango de fechas proporcionado.
    """
    try:
        async with httpx.AsyncClient(auth=AUTH, timeout=60) as client:
            # 1. Obtener IDs
            ids = await fetch_ticket_ids(client, date_from, date_to)
            if not ids:
                return {"tickets": 0, "promedio": None, "mediana": None, "minimo": None, "maximo": None}

            # 2. Obtener métricas con concurrencia limitada a 10 para evitar rate limit
            sem     = asyncio.Semaphore(10)
            tasks   = [fetch_metrics(client, tid, sem) for tid in ids]
            results = await asyncio.gather(*tasks)
            data    = [r for r in results if r]

        if not data:
            return {"tickets": 0, "primera_resolucion": None, "resolucion_final": None}

        def calc_stats(valores: list) -> Optional[dict]:
            if not valores:
                return None
            v   = sorted(valores)
            n   = len(v)
            mid = n // 2
            med = (v[mid - 1] + v[mid]) / 2 if n % 2 == 0 else v[mid]
            return {
                "promedio": round(sum(v) / n, 1),
                "mediana":  round(med, 1),
                "minimo":   round(min(v), 1),
                "maximo":   round(max(v), 1),
            }

        reopened = [d for d in data if d["frt_first"] is not None and d["frt_full"] is not None and d["frt_full"] > d["frt_first"]]

        return {
            "tickets":            len(data),
            "primera_resolucion": calc_stats([d["frt_first"] for d in data if d["frt_first"] is not None]),
            "resolucion_final":   {
                **(calc_stats([d["frt_full"] for d in reopened]) or {"promedio": None, "mediana": None, "minimo": None, "maximo": None}),
                "tickets_reabiertos": len(reopened),
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/causa-metrics")
async def causa_metrics(date_from: str = Query(...), date_to: str = Query(...)):
    """
    Agrupa los tickets por su 'Causa' y devuelve un conteo ordenado de mayor a menor.
    """
    async with httpx.AsyncClient(auth=AUTH, timeout=30) as client:
        rows = await fetch_ticket_causa(client, date_from, date_to)

    # Conteo de frecuencias
    conteo: dict[str, int] = {}
    for r in rows:
        conteo[r["causa"]] = conteo.get(r["causa"], 0) + 1

    total    = sum(conteo.values())
    # Transformar a lista de objetos para facilitar el consumo en frontend (JSON)
    tabla    = sorted([{"causa": k, "cantidad": v} for k, v in conteo.items()], key=lambda x: -x["cantidad"])

    return {"total": total, "tabla": tabla}


@app.get("/api/tickets-by-tags")
async def tickets_by_tags(tags: list[str] = Query(...), limit: int = Query(5, ge=1, le=50)):
    """
    Devuelve los últimos `limit` tickets que tengan alguna de las etiquetas indicadas (OR).
    """
    try:
        if not tags:
            return {"success": False, "error": "Se requiere al menos una etiqueta."}

        tag_clauses = " ".join(f"tags:{t}" for t in tags)
        query       = f"type:ticket {tag_clauses}"

        async with httpx.AsyncClient(auth=AUTH, timeout=30) as client:
            r = await client.get(
                f"{BASE_URL}/search.json",
                params={"query": query, "sort_by": "created_at", "sort_order": "desc", "per_page": limit},
            )
            r.raise_for_status()
            data = r.json()

        tickets = []
        for t in data.get("results", [])[:limit]:
            description = t.get("description", "")
            if description and len(description) > 200:
                description = description[:200].rsplit(" ", 1)[0] + "…"
            tickets.append({
                "id":          t["id"],
                "subject":     t.get("subject", ""),
                "status":      t.get("status", ""),
                "created_at":  t.get("created_at", ""),
                "tags":        t.get("tags", []),
                "description": description,
            })

        return {"tags": tags, "total": len(tickets), "tickets": tickets}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/tags")
async def get_tags():
    """Returns all available tags from Zendesk sorted by usage count."""
    try:
        all_tags = []
        url      = f"{BASE_URL}/tags.json"
        params   = {"per_page": 100}
        async with httpx.AsyncClient(auth=AUTH, timeout=30) as client:
            while url:
                r = await client.get(url, params=params)
                r.raise_for_status()
                data = r.json()
                all_tags.extend(data.get("tags", []))
                url    = data.get("next_page")
                params = None
        all_tags.sort(key=lambda t: -t.get("count", 0))
        return {"tags": [t["name"] for t in all_tags]}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/ticket/{ticket_id}")
async def get_ticket(ticket_id: int):
    """
    Obtiene la información de un ticket específico.
    """
    url = f"{BASE_URL}/tickets/{ticket_id}.json"
    
    async with httpx.AsyncClient(auth=AUTH, timeout=30) as client:
        r = await client.get(url)
        if r.status_code != 200:
            return {"success": False, "error": "Ticket no encontrado"}
        data = r.json()
        
    t = data.get("ticket", {})
    description = t.get("description", "")
    if description and len(description) > 200:
        description = description[:200].rsplit(" ", 1)[0] + "…"

    ticket_data = {
        "id":             t.get("id"),
        "subject":        t.get("subject", ""),
        "status":         t.get("status", ""),
        "created_at":     t.get("created_at", ""),
        "updated_at":     t.get("updated_at", ""),
        "requester_name": t.get("requester", {}).get("name") if t.get("requester") else None,
        "assignee_name":  t.get("assignee", {}).get("name") if t.get("assignee") else None,
        "description":    description,
    }
    
    return {"success": True, "ticket": ticket_data}

@app.post("/api/generate-response")
async def generate_response(body: GenerateRequest):
    """
    Orchestrates fetching the main ticket + last 10 solved historical tickets by causa,
    builds a structured prompt and calls Gemini to generate a support response draft.
    """
    try:
        if not openai_client:
            return {"success": False, "error": "OPENAI_API_KEY no configurada en el servidor."}

        async with httpx.AsyncClient(auth=AUTH, timeout=30) as client:
            main_ticket, historical = await asyncio.gather(
                fetch_full_ticket_detail(client, body.ticket_id),
                fetch_historical_tickets_for_ai(client, body.tags),
            )

        if not main_ticket:
            return {"success": False, "error": f"Ticket #{body.ticket_id} no encontrado."}

        historical_context = "\n\n---\n\n".join(
            f"Ticket #{t['id']} — {t['subject']}\nEstado: {t['status']}\nEtiquetas: {', '.join(t.get('tags', []))}\nDescripción: {t['description']}"
            for t in historical
        ) or "No hay tickets históricos resueltos disponibles para estas etiquetas."

        system_prompt = (
            "Eres un agente de soporte técnico de un servicio SaaS. Te vamos a proporcionar los últimos "
            "10 tickets históricos asociados a una causa específica para que analices el contexto del caso "
            "y su respectiva solución. También recibirás un nuevo ticket entrante. Tu objetivo es generar "
            "una respuesta profesional y precisa para este nuevo ticket, tomando como referencia y "
            "manteniendo la consistencia con las soluciones dadas en los casos anteriores.\n\n"
            "IMPORTANTE: Todas tus respuestas deben seguir EXACTAMENTE esta estructura, sin agregar "
            "saludos adicionales ni cambiar el orden:\n\n"
            "Buen día\n\n"
            "[Tratamiento apropiado y nombre del cliente, ej: Sra. García / Sr. López]\n\n"
            "Saludos!\n\n"
            "Hemos recibido su reporte y le agradecemos por contactarnos.\n"
            "Queremos informarle que [contenido de la respuesta basado en el análisis de casos históricos]\n\n"
            "Quedamos atentos a cualquier otra consulta o requerimiento."
        )
        user_prompt = (
            f"Etiquetas del ticket: {', '.join(body.tags)}\n\n"
            f"Tickets históricos resueltos ({len(historical)} encontrados):\n\n"
            f"{historical_context}\n\n"
            "---\n\n"
            f"Nuevo ticket a responder:\n"
            f"ID: #{main_ticket['id']}\n"
            f"Nombre del cliente: {main_ticket['requester_name'] or 'No disponible'}\n"
            f"Asunto: {main_ticket['subject']}\n"
            f"Descripción: {main_ticket['description']}\n\n"
            "Genera la respuesta siguiendo la estructura indicada."
            + (f"\n\nInformación adicional del caso:\n{body.extra_context}" if body.extra_context else "")
        )

        completion = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
        )

        return {
            "success":          True,
            "response":         completion.choices[0].message.content,
            "tickets_analyzed": len(historical),
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


# ==========================================
# SERVICIO DE ARCHIVOS ESTÁTICOS
# ==========================================

# Monta la carpeta 'static' para servir el index.html y assets del frontend
app.mount("/", StaticFiles(directory="static", html=True), name="static")