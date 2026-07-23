# -*- coding: utf-8 -*-
"""remove_covered_duplicates.py — pour chaque mot déjà VALIDÉ par le natif (en tenant compte de
sa correction anufo_corrige, pas seulement du champ anufo d'origine), retire du fichier les
lignes NON validées qui représentent le même mot (racine sans ton, casse ignorée). Ne touche
JAMAIS aux lignes déjà validées (demande explicite de l'utilisateur : "laisse ceux déjà validé,
concentre-toi sur ceux non validé").

Cas concret trouvé : une entrée source mal océrisée "je" a été corrigée par le natif en "kpaja"
pendant la validation — la vraie forme "kpaja" existait déjà comme ligne SÉPARÉE non validée
plus bas dans la liste (freq=3, jamais glosée) ; désormais redondante, donc retirée.
"""
import json
import unicodedata

PATH = "data_norm/vocab_to_validate_validated.jsonl"


def bare(text):
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def effective_form(row):
    return (row.get("anufo_corrige") or "").strip() or row["anufo"]


def main():
    with open(PATH, "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]

    validated = [r for r in rows if r.get("valide_humain")]
    not_validated = [r for r in rows if not r.get("valide_humain")]

    validated_bare_forms = {bare(effective_form(r)) for r in validated}

    kept_not_validated = []
    removed = []
    for r in not_validated:
        if bare(r["anufo"]) in validated_bare_forms:
            removed.append(r)
        else:
            kept_not_validated.append(r)

    final_rows = validated + kept_not_validated
    final_rows.sort(key=lambda r: -r["frequence"])
    for i, r in enumerate(final_rows, start=1):
        r["id"] = f"W{i:05d}"

    with open(PATH, "w", encoding="utf-8") as f:
        for r in final_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"Lignes non validées retirées (déjà couvertes par une validation) : {len(removed)}")
    for r in removed:
        print(f"  - {r['anufo']!r} (freq={r['frequence']}, fr_propose={r.get('fr_propose')!r})")
    print(f"Total avant : {len(rows)} -> après : {len(final_rows)}")
    print(f"Validées (inchangées) : {len(validated)} | Non validées restantes : {len(kept_not_validated)}")


if __name__ == "__main__":
    main()
