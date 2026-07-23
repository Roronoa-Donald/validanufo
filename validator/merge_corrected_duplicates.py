# -*- coding: utf-8 -*-
"""merge_corrected_duplicates.py — fusionne les doublons APPARUS APRÈS CORRECTION du natif.

Cas non détecté par les passes précédentes (elles comparaient le mot d'origine `anufo`) :
pendant la validation, le natif corrige l'orthographe d'un mot (`anufo_corrige`) et la forme
corrigée se retrouve IDENTIQUE à celle d'une autre ligne. Exemples réels trouvés :
  - "sudi"     corrigé en "wahara"  -> doublon avec la ligne "wahara"  (souffrance / souffrir)
  - "kereewam" corrigé en "kereewa" -> doublon avec la ligne "kereewa" (enseignement / doctrine)
  - "adi"      corrigé en "dodo"    -> doublon avec la ligne "dodo"    (proche / près)

Règle appliquée : fusion sur la FORME EFFECTIVE (anufo_corrige sinon anufo).
- Fréquences additionnées (le mot est réellement plus fréquent que chaque ligne isolée).
- Les DEUX gloses sont conservées : la principale reste celle de la ligne la plus fréquente,
  l'autre est ajoutée dans `sens_alternatifs` (rien n'est perdu — ex. souffrir/souffrance sont
  deux nuances du même mot, au natif de trancher s'il veut affiner).
- `formes_fusionnees` garde la trace des mots d'origine (dont celui qui a été corrigé).
- Le statut `valide_humain` est conservé (le travail de validation reste acquis).

Fusionne aussi les paires ton-différent dont le natif a validé les DEUX avec le MÊME sens
(ex. nya/nyá tous deux "avoir") : même sens + même racine = même mot, le ton était noté de
façon incohérente dans la source. Les paires ton-différent à sens DIFFÉRENTS (má "ne pas" vs
ma "donner", ba "enfant" vs bá "futur"...) ne sont PAS touchées : ce sont de vraies paires
minimales tonales, les fusionner détruirait une distinction linguistique réelle.
"""
import json
import sys
import unicodedata

PATH = sys.argv[1] if len(sys.argv) > 1 else "data_norm/vocab_to_validate_validated.jsonl"


def bare(text):
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def effective(row):
    return (row.get("anufo_corrige") or "").strip() or row["anufo"]


def gloss_of(row):
    return ((row.get("fr_corrige") or "").strip() or (row.get("fr_propose") or "").strip()).lower()


def merge_group(group):
    group = sorted(group, key=lambda r: -r["frequence"])
    primary = dict(group[0])
    primary["frequence"] = sum(r["frequence"] for r in group)

    sens_alt = list(primary.get("sens_alternatifs", []))
    formes = list(primary.get("formes_fusionnees", []))
    for r in group:
        g_fr = (r.get("fr_corrige") or "").strip() or (r.get("fr_propose") or "").strip()
        g_en = (r.get("en_corrige") or "").strip() or (r.get("en_propose") or "").strip()
        if r is not group[0] and g_fr and g_fr.lower() != gloss_of(group[0]):
            entry = {"fr": g_fr, "en": g_en, "depuis_mot": r["anufo"], "frequence": r["frequence"]}
            if entry not in sens_alt:
                sens_alt.append(entry)
        formes.append({
            "anufo": r["anufo"],
            "anufo_corrige": r.get("anufo_corrige") or "",
            "frequence": r["frequence"],
            "fr": g_fr,
            "en": g_en,
            "etait_valide": bool(r.get("valide_humain")),
        })
    if sens_alt:
        primary["sens_alternatifs"] = sens_alt
    primary["formes_fusionnees"] = formes
    return primary


def main():
    with open(PATH, "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]

    # --- 1) doublons EXACTS sur la forme effective (créés par les corrections du natif) -------
    by_exact = {}
    for r in rows:
        by_exact.setdefault(effective(r), []).append(r)

    after_exact = []
    merged_exact = []
    for form, group in by_exact.items():
        if len(group) == 1:
            after_exact.append(group[0])
        else:
            merged_exact.append((form, [r["anufo"] for r in group]))
            after_exact.append(merge_group(group))

    # --- 2) paires ton-différent VALIDÉES avec le MÊME sens -----------------------------------
    by_bare = {}
    for r in after_exact:
        by_bare.setdefault(bare(effective(r)), []).append(r)

    final_rows = []
    merged_tonal = []
    kept_distinct = []
    for key, group in by_bare.items():
        if len(group) == 1:
            final_rows.append(group[0])
            continue
        glosses = {gloss_of(r) for r in group if gloss_of(r)}
        if len(glosses) <= 1:
            merged_tonal.append((key, [effective(r) for r in group]))
            final_rows.append(merge_group(group))
        else:
            kept_distinct.append((key, [(effective(r), gloss_of(r)) for r in group]))
            final_rows.extend(group)

    final_rows.sort(key=lambda r: -r["frequence"])
    for i, r in enumerate(final_rows, start=1):
        r["id"] = f"W{i:05d}"

    with open(PATH, "w", encoding="utf-8") as f:
        for r in final_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    lines = []
    lines.append(f"Fichier : {PATH}")
    lines.append(f"Doublons EXACTS fusionnes (apres correction du natif) : {len(merged_exact)}")
    for form, origins in merged_exact:
        lines.append(f"   {form}  <- {origins}")
    lines.append(f"Paires tonales fusionnees (meme sens valide) : {len(merged_tonal)}")
    for key, forms in merged_tonal:
        lines.append(f"   {key}  <- {forms}")
    lines.append(f"Paires tonales CONSERVEES separees (sens differents) : {len(kept_distinct)}")
    for key, pairs in kept_distinct:
        lines.append(f"   {key} : {pairs}")
    lines.append(f"Total : {len(rows)} -> {len(final_rows)}")
    lines.append(f"Validees preservees : {sum(1 for r in final_rows if r.get('valide_humain'))}")

    with open("reports/dedup_vocab_report.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines[:3]))
    print("... rapport complet -> reports/dedup_vocab_report.txt")


if __name__ == "__main__":
    main()
