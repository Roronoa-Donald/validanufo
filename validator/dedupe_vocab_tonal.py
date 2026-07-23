# -*- coding: utf-8 -*-
"""dedupe_vocab_tonal.py — fusionne les entrées qui ne diffèrent que par le TON (accent aigu),
ex. "ka"/"ká", "bo"/"bó" (121 paires trouvées sur 2822 mots). Demande explicite de l'utilisateur
après vérification : ces paires ne sont PAS forcément de vrais doublons (l'anufo est une langue
à tons, REGLES_ANUFO.md §1 dit de conserver le ton), mais l'utilisateur a tranché : fusionner en
une seule entrée par racine sans ton. RIEN n'est perdu (les formes d'origine restent visibles
dans "formes_fusionnees" pour arbitrage humain dans le validateur).

IMPORTANT (travail déjà en cours de l'utilisateur, 250 mots validés au moment d'écrire ceci) :
la fusion est CONSCIENTE de valide_humain. Si une des entrées d'un groupe a déjà été validée
par le natif, sa correction (anufo_corrige/fr_corrige/en_corrige/valide_humain/qc_note) est
TOUJOURS conservée comme prioritaire dans l'entrée fusionnée — jamais écrasée par une entrée
non validée, même plus fréquente. Si les DEUX entrées d'un groupe sont validées avec des
corrections DIFFÉRENTES, la fusion est refusée pour ce groupe (conflit signalé, pas tranché
automatiquement) : les deux entrées restent séparées.

Opère sur le fichier passé en argument (typiquement data_norm/vocab_to_validate_validated.jsonl
si l'utilisateur a déjà commencé à valider — c'est celui que validator_app.py charge en
priorité — sinon data_norm/vocab_to_validate.jsonl).
"""
import json
import sys
import unicodedata


def bare(text):
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "data_norm/vocab_to_validate.jsonl"

    with open(path, "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]

    groups = {}
    for r in rows:
        groups.setdefault(bare(r["anufo"]), []).append(r)

    merged_rows = []
    n_merged_groups = 0
    n_rows_removed = 0
    n_conflicts = 0

    for key, group in groups.items():
        if len(group) == 1:
            merged_rows.append(group[0])
            continue

        validated = [r for r in group if r.get("valide_humain")]
        if len(validated) > 1:
            # plusieurs entrées du groupe déjà validées séparément par le natif : si leurs
            # corrections diffèrent, on ne tranche PAS automatiquement -> groupe non fusionné.
            corrections = {(r.get("anufo_corrige") or r["anufo"], r.get("fr_corrige") or "") for r in validated}
            if len(corrections) > 1:
                n_conflicts += 1
                merged_rows.extend(group)
                continue

        group_sorted = sorted(group, key=lambda r: -r["frequence"])
        # priorité : une entrée déjà validée par le natif prime toujours sur la fréquence brute.
        primary = validated[0] if validated else group_sorted[0]

        n_merged_groups += 1
        n_rows_removed += len(group) - 1

        fr_candidats, en_candidats, glose_existante, formes_fusionnees = [], [], [], []
        for r in group_sorted:
            for x in r.get("fr_candidats", []):
                if x not in fr_candidats:
                    fr_candidats.append(x)
            for x in r.get("en_candidats", []):
                if x not in en_candidats:
                    en_candidats.append(x)
            for x in r.get("glose_existante", []):
                if x not in glose_existante:
                    glose_existante.append(x)
            formes_fusionnees.append({
                "anufo": r["anufo"],
                "frequence": r["frequence"],
                "fr_propose": r.get("fr_propose"),
                "en_propose": r.get("en_propose"),
                "source": r.get("source"),
                "etait_valide": bool(r.get("valide_humain")),
            })

        merged = dict(primary)
        merged["frequence"] = sum(r["frequence"] for r in group)
        merged["fr_candidats"] = fr_candidats
        merged["en_candidats"] = en_candidats
        merged["glose_existante"] = glose_existante
        if not validated:
            merged["statut"] = "a_verifier"
        merged["formes_fusionnees"] = formes_fusionnees
        merged_rows.append(merged)

    merged_rows.sort(key=lambda r: -r["frequence"])
    for i, r in enumerate(merged_rows, start=1):
        r["id"] = f"W{i:05d}"

    with open(path, "w", encoding="utf-8") as f:
        for r in merged_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    n_validated_after = sum(1 for r in merged_rows if r.get("valide_humain"))
    print(f"Fichier : {path}")
    print(f"Groupes fusionnés : {n_merged_groups}  |  Conflits (2 validations différentes, non fusionnés) : {n_conflicts}")
    print(f"Lignes retirées : {n_rows_removed}")
    print(f"Total avant : {len(rows)} -> après : {len(merged_rows)}")
    print(f"Mots déjà validés préservés : {n_validated_after}")


if __name__ == "__main__":
    main()
