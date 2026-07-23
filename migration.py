import json
import os
from pymongo import MongoClient, UpdateOne
from tqdm import tqdm

# Configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "anufo_db")
DATA_DIR = "data_norm"

def migrate():
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    print(f"Connexion à MongoDB : {MONGO_URI}")
    print(f"Utilisation de la base de données : {DB_NAME}")

    # Lister tous les fichiers .jsonl dans data_norm/
    files = [f for f in os.listdir(DATA_DIR) if f.endswith(".jsonl")]

    if not files:
        print("Aucun fichier .jsonl trouvé dans data_norm/")
        return

    for filename in files:
        collection_name = filename.replace(".jsonl", "")
        print(f"\nTraitement de {filename} -> collection '{collection_name}'...")

        collection = db[collection_name]

        # 1. Créer un index unique sur 'anufo' pour accélérer les mises à jour et éviter les doublons
        collection.create_index("anufo", unique=True)

        rows_to_migrate = []
        file_path = os.path.join(DATA_DIR, filename)

        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    row = json.loads(line)
                    if "anufo" not in row:
                        continue

                    # Assurer que les champs de base existent
                    row.setdefault("valide_humain", False)
                    row.setdefault("qc_note", "")

                    # Utilisation de UpdateOne avec upsert=True.
                    # On utilise $setOnInsert pour que les données soient fixées UNIQUEMENT à la création.
                    # Si le document existe déjà (déjà validé par un humain), on NE L'ÉCRASE PAS.
                    rows_to_migrate.append(
                        UpdateOne(
                            {"anufo": row["anufo"]},
                            {"$setOnInsert": row},
                            upsert=True
                        )
                    )

        if rows_to_migrate:
            # Écriture groupée pour des performances maximales
            batch_size = 1000
            total_ops = len(rows_to_migrate)

            for i in tqdm(range(0, total_ops, batch_size)):
                batch = rows_to_migrate[i : i + batch_size]
                collection.bulk_write(batch)

            print(f"Traitement de {total_ops} entrées pour {collection_name}.")
        else:
            print("Le fichier était vide ou ne contenait aucune entrée valide.")

    print("\nMigration terminée avec succès ! 🚀")
    print("Toutes les données ont été synchronisées. Les validations humaines ont été préservées.")

if __name__ == "__main__":
    migrate()
