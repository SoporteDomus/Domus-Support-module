import os
import asyncio
import httpx
from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import Optional

app = FastAPI()

SUBDOMAIN = os.getenv("ZD_SUBDOMAIN", "domustech")
EMAIL     = os.getenv("ZD_EMAIL", "soporte@domus.la")
API_TOKEN = os.getenv("ZD_API_TOKEN", "TU_TOKEN_AQUI")
BASE_URL  = f"https://{SUBDOMAIN}.zendesk.com/api/v2"
AUTH      = (f"{EMAIL}/token", API_TOKEN)

CUSTOM_FIELD_ID = 1500001726262


async def fetch_ticket_ids(client: httpx.AsyncClient, date_from: str, date_to: str, status_filter: str = "solved") -> list[int]:
    query      = f"type:ticket {status_filter}>={date_from} {status_filter}<={date_to}"
    search_url = f"{BASE_URL}/search.json"
    params     = {"query": query}
    ids        = []

    while search_url:
        r = await client.get(search_url, params=params)
        r.raise_for_status()
        data       = r.json()
        ids       += [t["id"] for t in data.get("results", [])]
        search_url = data.get("next_page")
        params     = None

    return ids


async def fetch_metrics(client: httpx.AsyncClient, ticket_id: int) -> Optional[dict]:
    r = await client.get(f"{BASE_URL}/tickets/{ticket_id}/metrics.json")
    if r.status_code != 200:
        return None
    m              = r.json().get("ticket_metric", {})
    frt_calendario = m.get("first_resolution_time_in_minutes", {}).get("calendar")
    frt_negocio    = m.get("first_resolution_time_in_minutes", {}).get("business")
    if frt_calendario is None:
        return None
    return {"ticket_id": ticket_id, "frt_min_calendario": frt_calendario, "frt_min_negocio": frt_negocio}


async def fetch_ticket_causa(client: httpx.AsyncClient, date_from: str, date_to: str) -> list[dict]:
    query      = f"type:ticket created>={date_from} created<={date_to}"
    search_url = f"{BASE_URL}/search.json"
    params     = {"query": query}
    rows       = []

    while search_url:
        r = await client.get(search_url, params=params)
        r.raise_for_status()
        data = r.json()

        for t in data.get("results", []):
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


@app.get("/api/resolution-metrics")
async def resolution_metrics(date_from: str = Query(...), date_to: str = Query(...)):
    async with httpx.AsyncClient(auth=AUTH, timeout=30) as client:
        ids = await fetch_ticket_ids(client, date_from, date_to)
        if not ids:
            return {"tickets": 0, "promedio": None, "mediana": None, "minimo": None, "maximo": None}

        tasks   = [fetch_metrics(client, tid) for tid in ids]
        results = await asyncio.gather(*tasks)
        data    = [r for r in results if r]

    if not data:
        return {"tickets": 0, "promedio": None, "mediana": None, "minimo": None, "maximo": None}

    valores = [d["frt_min_calendario"] for d in data]
    valores.sort()
    n       = len(valores)
    mid     = n // 2
    mediana = (valores[mid - 1] + valores[mid]) / 2 if n % 2 == 0 else valores[mid]

    return {
        "tickets":  n,
        "promedio": round(sum(valores) / n, 1),
        "mediana":  round(mediana, 1),
        "minimo":   round(min(valores), 1),
        "maximo":   round(max(valores), 1),
    }


@app.get("/api/causa-metrics")
async def causa_metrics(date_from: str = Query(...), date_to: str = Query(...)):
    async with httpx.AsyncClient(auth=AUTH, timeout=30) as client:
        rows = await fetch_ticket_causa(client, date_from, date_to)

    conteo: dict[str, int] = {}
    for r in rows:
        conteo[r["causa"]] = conteo.get(r["causa"], 0) + 1

    total    = sum(conteo.values())
    tabla    = sorted([{"causa": k, "cantidad": v} for k, v in conteo.items()], key=lambda x: -x["cantidad"])

    return {"total": total, "tabla": tabla}


@app.get("/api/tickets-by-causa")
async def tickets_by_causa(causa: str = Query(...), limit: int = Query(5, ge=1, le=50)):
    """
    Devuelve los últimos `limit` tickets cuyo campo personalizado CUSTOM_FIELD_ID
    coincida con el valor de `causa`, ordenados por fecha de creación descendente.
    """
    # Usamos la Search API de Zendesk con el campo personalizado
    query      = f"type:ticket fieldvalue:{causa}"
    search_url = f"{BASE_URL}/search.json"
    params     = {
        "query":   query,
        "sort_by": "created_at",
        "sort_order": "desc",
        "per_page": limit,
    }

    async with httpx.AsyncClient(auth=AUTH, timeout=30) as client:
        r = await client.get(search_url, params=params)
        r.raise_for_status()
        data = r.json()

    tickets = []
    for t in data.get("results", [])[:limit]:
        # Extraer descripción corta del primer comentario si está disponible
        description = t.get("description", "")
        if description and len(description) > 200:
            description = description[:200].rsplit(" ", 1)[0] + "…"

        tickets.append({
            "id":             t["id"],
            "subject":        t.get("subject", ""),
            "status":         t.get("status", ""),
            "created_at":     t.get("created_at", ""),
            "updated_at":     t.get("updated_at", ""),
            "requester_name": t.get("requester", {}).get("name") if t.get("requester") else None,
            "assignee_name":  t.get("assignee", {}).get("name") if t.get("assignee") else None,
            "description":    description,
        })

    return {"causa": causa, "total": len(tickets), "tickets": tickets}


app.mount("/", StaticFiles(directory="static", html=True), name="static")