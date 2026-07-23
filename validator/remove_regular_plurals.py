# -*- coding: utf-8 -*-
"""remove_regular_plurals.py — retire de la file de validation les PLURIELS RÉGULIERS en -m
quand la forme singulière est déjà présente dans la liste.

Justification (REGLES_ANUFO.md §4) : « Pluriel : suffixe -m » et « Agentif : -fɔ (pluriel -fɔm) ».
La formation du pluriel est RÉGULIÈRE et prévisible : faire valider au natif "kristofɔ" ET
"kristofɔm" est du travail en double. Le singulier validé suffit à couvrir le lexème.

Sécurités :
- Ne touche JAMAIS une ligne déjà validée (le travail du natif est intouchable), ni comme
  plurielle à retirer, ni comme singulier.
- Ne retire le pluriel QUE si la forme singulière existe réellement dans le fichier.
- La forme plurielle retirée n'est pas perdue : elle est enregistrée dans l'entrée du singulier
  (champ `pluriel` : forme + fréquence), pour que le natif la voie pendant la validation et
  puisse signaler si ce pluriel a un sens propre.
- Le circonfixe m-…-m des racines en b- (ba→mbam, REGLES §4) n'est PAS traité ici : c'est un
  autre procédé, non détectable par simple suffixe -m -> laissé intact.
- Rapport complet écrit dans reports/plurals_removed.txt pour relecture.
"""
import json
import os
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "data_norm/vocab_to_validate_validated.jsonl"
REPORT = os.path.join("reports", "plurals_removed.txt")


def effective(row):
    return (row.get("anufo_corrige") or "").strip() or row["anufo"]


def main():
    with open(PATH, "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]

    by_form = {}
    for r in rows:
        by_form.setdefault(effective(r), []).append(r)

    removed = []
    kept = []
    for r in rows:
        form = effective(r)
        if r.get("valide_humain"):
            kept.append(r)  # jamais toucher au travail validé
            continue
        if not form.endswith("m") or len(form) < 3:
            kept.append(r)
            continue
        singular = form[:-1]
        sing_rows = by_form.get(singular)
        if not sing_rows:
            kept.append(r)
            continue

        # rattache la forme plurielle à l'entrée du singulier (visible dans le validateur)
        target = sing_rows[0]
        target.setdefault("pluriel", {
            "forme": form,
            "frequence": r["frequence"],
            "note": "pluriel régulier -m, retiré de la file de validation",
        })
        removed.append((singular, form, target["frequence"], r["frequence"], bool(target.get("valide_humain"))))

    kept.sort(key=lambda r: -r["frequence"])
    for i, r in enumerate(kept, start=1):
        r["id"] = f"W{i:05d}"

    with open(PATH, "w", encoding="utf-8") as f:
        for r in kept:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    os.makedirs("reports", exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("Pluriels reguliers en -m retires de la file de validation\n")
        f.write("(le singulier reste a valider ; la forme plurielle est tracee dans son entree)\n\n")
        f.write(f"{'SINGULIER':<22}{'PLURIEL RETIRE':<24}{'freq sing':>10}{'freq plur':>10}   sing deja valide\n")
        for sing, plur, fs, fp, sv in sorted(removed, key=lambda t: -t[3]):
            f.write(f"{sing:<22}{plur:<24}{fs:>10}{fp:>10}   {'oui' if sv else 'non'}\n")
        f.write(f"\nTotal retire : {len(removed)}\n")

    n_val = sum(1 for r in kept if r.get("valide_humain"))
    print(f"Pluriels reguliers -m retires : {len(removed)}")
    print(f"Total : {len(rows)} -> {len(kept)}")
    print(f"Validees preservees : {n_val}")
    print(f"Rapport : {REPORT}")


if __name__ == "__main__":
    main()
