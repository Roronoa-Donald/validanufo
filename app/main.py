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
import logging

# Configuration des logs pour faciliter le debug sur Render
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("anufo_app")

app = FastAPI()

# Configuration via variables d'environnement
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "anufo_db")

# Templates et fichiers statiques
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# MongoDB Client
try:
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
except Exception as e:
    logger.error(f"Erreur lors de la connexion à MongoDB : {e}")

class RowUpdate(BaseModel):
    collection: str
    index: int
    data: dict

async def validate_collection_exists(collection_name: str):
    """Vérifie si la collection existe et est valide."""
    if not collection_name or not isinstance(collection_name, str):
        return False
    try:
        existing_cols = await db.list_collection_names()
        return collection_name in existing_cols
    except Exception as e:
        logger.error(f"Erreur lors de la vérification de la collection {collection_name} : {e}")
        return False

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Lister toutes les collections (jeux de données) à valider."""
    try:
        col_names = await db.list_collection_names()
        collections = [str(name) for name in col_names]

        # Rendu manuel pour contourner le bug de cache de Jinja2/Python 3.14
        template = templates.env.get_template("index.html")
        html_content = template.render(request=request, collections=collections)
        return HTMLResponse(content=html_content)
    except Exception as e:
        logger.error(f"Erreur page index : {e}")
        return HTMLResponse(content=f"Erreur lors du chargում de la page d'accueil : {str(e)}", status_code=500)

@app.get("/validate/{collection_name}", response_class=HTMLResponse)
async def validate_page(request: Request, collection_name: str):
    """L'interface de validation pour un jeu de données spécifique."""
    if not await validate_collection_exists(collection_name):
        raise HTTPException(status_code=404, detail="Collection non trouvée ou invalide")

    try:
        template = templates.env.get_template("validate.html")
        html_content = template.render(request=request, collection_name=collection_name)
        return HTMLResponse(content=html_content)
    except Exception as e:
        logger.error(f"Erreur page validation ({collection_name}) : {e}")
        return HTMLResponse(content=f"Erreur lors du rendu de la page de validation : {str(e)}", status_code=500)

@app.get("/api/rows/{collection_name}")
async def get_rows(collection_name: str):
    """Récupérer toutes les lignes pour l'interface de validation."""
    try:
        if not await validate_collection_exists(collection_name):
            return JSONResponse(content={"error": "Collection non trouvée"}, status_code=404)

        collection = db[collection_name]
        # Tri par ID pour garantir la stabilité de l'ordre
        cursor = collection.find({}).sort("_id", 1)
        rows = await cursor.to_list(length=10000)

        for row in rows:
            row["_id"] = str(row["_id"])

        return JSONResponse(content=rows)
    except Exception as e:
        logger.error(f"Erreur API rows ({collection_name}) : {e}")
        return JSONResponse(content={"error": f"Erreur lors de la récupération des données : {str(e)}"}, status_code=500)

@app.post("/api/save")
async def save_row(update: RowUpdate):
    """Sauvegarder une ligne validée dans MongoDB."""
    try:
        if not await validate_collection_exists(update.collection):
            return JSONResponse(content={"ok": False, "error": "Collection non trouvée"}, status_code=404)

        collection = db[update.collection]
        row_id = update.data.get("_id")

        if not row_id:
            return JSONResponse(content={"ok": False, "error": "ID manquant"}, status_code=400)

        from bson import ObjectId
        await collection.update_one(
            {"_id": ObjectId(row_id)},
            {"$set": update.data}
        )
        return JSONResponse(content={"ok": True})
    except Exception as e:
        logger.error(f"Erreur API save : {e}")
        return JSONResponse(content={"ok": False, "error": f"Erreur serveur lors de la sauvegarde : {str(e)}"}, status_code=500)

@app.get("/export/{collection_name}")
async def export_collection(collection_name: str):
    """Exporter une collection au format JSONL."""
    try:
        if not await validate_collection_exists(collection_name):
            raise HTTPException(status_code=404, detail="Collection non trouvée")

        collection = db[collection_name]
        cursor = collection.find({})

        async def generate_jsonl():
            async for row in cursor:
                if "_id" in row:
                    row["_id"] = str(row["_id"])
                yield json.dumps(row, ensure_ascii=False) + "\n"

        return StreamingResponse(
            generate_jsonl(),
            media_type="application/x-jsonlines",
            headers={"Content-Disposition": f"attachment; filename={collection_name}.jsonl"}
        )
    except Exception as e:
        logger.error(f"Erreur export ({collection_name}) : {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'exportation : {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
