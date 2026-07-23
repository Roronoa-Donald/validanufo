import os
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from typing import List, Optional
import json
import io


app = FastAPI()

# Configuration from environment variables
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "anufo_db")

# Templates and Static files
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# MongoDB Client
client = AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]

class RowUpdate(BaseModel):
    collection: str
    index: int # We'll use an internal ID or a specific field like 'anufo'
    data: dict

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Lister toutes les collections (jeux de données) à valider."""
    try:
        col_names = await db.list_collection_names()
        collections = [str(name) for name in col_names]

        # On utilise la méthode manuelle de rendu pour contourner le bug de cache de Jinja2/Python 3.14
        template = templates.env.get_template("index.html")
        html_content = template.render(request=request, collections=collections)
        return HTMLResponse(content=html_content)
    except Exception as e:
        return HTMLResponse(content=f"Erreur lors du chargement de la page d'accueil : {str(e)}", status_code=500)

@app.get("/validate/{collection_name}", response_class=HTMLResponse)
async def validate_page(request: Request, collection_name: str):
    """L'interface de validation pour un jeu de données spécifique."""
    # Vérifier si la collection existe
    if collection_name not in await db.list_collection_names():
        raise HTTPException(status_code=404, detail="Collection non trouvée")

    return templates.TemplateResponse("validate.html", {"request": request, "collection_name": collection_name})

@app.get("/api/rows/{collection_name}")
async def get_rows(collection_name: str):
    """Récupérer toutes les lignes pour l'interface de validation."""
    collection = db[collection_name]
    cursor = collection.find({})
    rows = await cursor.to_list(length=10000) # Ajuster selon la taille attendue

    # Convertir l'ObjectId MongoDB en chaîne pour la compatibilité JSON
    for row in rows:
        row["_id"] = str(row["_id"])

    return JSONResponse(content=rows)

@app.post("/api/save")
async def save_row(update: RowUpdate):
    """Sauvegarder une ligne validée dans MongoDB."""
    collection = db[update.collection]

    # On utilise l' _id MongoDB pour identifier la ligne
    row_id = update.data.get("_id")
    if not row_id:
        return JSONResponse(content={"ok": False, "error": "ID manquant"}, status_code=400)

    # Convertir l'ID chaîne en ObjectId si nécessaire
    from bson import ObjectId

    try:
        await collection.update_one(
            {"_id": ObjectId(row_id)},
            {"$set": update.data}
        )
        return JSONResponse(content={"ok": True})
    except Exception as e:
        return JSONResponse(content={"ok": False, "error": f"Erreur serveur : {str(e)}"}, status_code=500)

@app.get("/export/{collection_name}")
async def export_collection(collection_name: str):
    """Export a collection to JSONL format."""
    collection = db[collection_name]
    cursor = collection.find({})

    async def generate_jsonl():
        async for row in cursor:
            # Remove MongoDB internal ID from the export if desired,
            # or keep it. Usually, users want the original format.
            # We convert ObjectId to string if it exists.
            if "_id" in row:
                row["_id"] = str(row["_id"])
            yield json.dumps(row, ensure_ascii=False) + "\n"

    return StreamingResponse(
        generate_jsonl(),
        media_type="application/x-jsonlines",
        headers={"Content-Disposition": f"attachment; filename={collection_name}.jsonl"}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
