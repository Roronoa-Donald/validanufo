# -*- coding: utf-8 -*-
"""propose_derivations.py — propose une glose FR **et EN** aux mots non validés qui sont des
formes DÉRIVÉES d'un radical déjà validé par le natif (affixes réguliers REGLES_ANUFO.md §4).

Deux sources croisées, par ordre de priorité :

1. CANDIDAT ATTESTÉ (le meilleur) : si l'alignement statistique Dice a proposé pour ce mot un
   candidat qui « ressemble » à la glose validée du radical (même début de mot), c'est presque
   sûrement la forme dérivée réelle, attestée dans la Bible.
   Ex. radical « galili » glosé *galilée* + candidat Dice « galiléen » -> on propose galiléen,
   pas un gabarit générique. C'est la vraie traduction, pas une paraphrase.

2. GABARIT MORPHOLOGIQUE (repli) : quand aucun candidat attesté ne correspond, on applique un
   gabarit par règle, adapté au type de la glose du radical (verbe / lieu-nom propre / autre)
   pour éviter les formulations absurdes.

⚠️ Toujours des PROPOSITIONS, jamais appliquées au lexique final : la découpe morphologique peut
être fortuite (« sumiɛ » n'est pas su-+miɛ « en train de ville »). Score de confiance fourni,
validation native obligatoire.
"""
import csv
import json
import os
import re
import sys
import unicodedata

PATH = "data_norm/vocab_to_validate_validated.jsonl"
REPORT = os.path.join("reports", "derivations_proposees.tsv")

# (label, extraction du radical, gabarit FR, gabarit EN, type attendu du radical)
AFFIXES = [
    ("agentif pluriel -fɔm", lambda w: w[:-3] if w.endswith("fɔm") and len(w) > 5 else None, "agentif_pl"),
    ("agentif -fɔ", lambda w: w[:-2] if w.endswith("fɔ") and len(w) > 4 else None, "agentif"),
    ("singulatif -niɛ", lambda w: w[:-3] if w.endswith("niɛ") and len(w) > 5 else None, "singulatif"),
    ("pluriel -m", lambda w: w[:-1] if w.endswith("m") and len(w) > 3 else None, "pluriel"),
    ("passé -li", lambda w: w[:-2] if w.endswith("li") and len(w) > 4 else None, "passe"),
    ("progressif su-", lambda w: w[2:] if w.startswith("su") and len(w) > 4 else None, "progressif"),
    ("progressif si-", lambda w: w[2:] if w.startswith("si") and len(w) > 4 else None, "progressif"),
    ("futur bɛ-", lambda w: w[2:] if w.startswith("bɛ") and len(w) > 4 else None, "futur"),
    ("passé a-", lambda w: w[1:] if w.startswith("a") and len(w) > 3 else None, "passe"),
]

FR_VERB_RE = re.compile(r"\w+(er|ir|re|oir)$")

# Dérivations agentives rédigées À LA MAIN (rôle prévu par CLAUDE.md : « rédiger les exemples
# gold »). Nécessaire car le français ne dérive pas mécaniquement : christ -> chrétien,
# égypte -> égyptien, médicament -> guérisseur. Le modèle est celui de
# chakosi_morphology_compounding.json (ayiri-fɔ = guérisseur/médecin, nwa-fɔ = homme riche).
# Clé = radical anufo validé. Valeur = (fr singulier, en singulier).
# Restent des PROPOSITIONS soumises à validation native, comme tout le reste de ce script.
CURATED_AGENTIVE = {
    # ethnonymes (lieu/nom propre -> habitant)
    "kristo": ("chrétien", "Christian"),
    "ijipiti": ("Égyptien", "Egyptian"),
    "makɛdoniya": ("Macédonien", "Macedonian"),
    "yudiya": ("Judéen", "Judean"),
    "akaya": ("Achaïen", "Achaian"),
    "roma": ("Romain", "Roman"),
    "levi": ("Lévite", "Levite"),
    # agentifs déverbaux / dénominaux
    "ayiri": ("guérisseur, médecin", "healer, doctor"),
    "ŋwaa": ("homme riche", "rich man"),
    "dadaka": ("trompeur", "deceiver"),
    "daani": ("témoin", "witness"),
    "jaraki": ("juge", "judge"),
    "fie": ("cultivateur, fermier", "farmer"),
    "lee": ("marin, batelier", "sailor, boatman"),
    "tukpaki": ("malade", "sick person"),
    "ahɔɛ": ("affamé", "hungry person"),
    "sɛrɛ": ("craintif, peureux", "fearful person"),
    "dawa": ("ancien, aîné", "elder"),
    "ŋgɔnlɛ": ("sage, personne intelligente", "wise person"),
    "kara": ("scribe, écrivain", "scribe, writer"),
    "sakpayo": ("bienfaiteur", "benefactor"),
    "nvanvani": ("parfumeur", "perfumer"),
    "ajɛkɛ": ("riche, trésorier", "wealthy person, treasurer"),
    "koro": ("celui qui aime", "one who loves"),
    "ŋminda": ("celui qui attend", "one who waits"),
    "konyaya": ("invité de noces", "wedding guest"),
}


def pluralize_list(text):
    """Met au pluriel chaque variante d'une glose « a, b » -> « as, bs ». Les irrégularités
    (boatman -> boatmen) ne sont pas gérées : ce sont des propositions, le natif corrige."""
    parts = [p.strip() for p in text.split(",")]
    return ", ".join(p if p.endswith("s") else p + "s" for p in parts)


def strip_accents(t):
    d = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in d if not unicodedata.combining(c))


def looks_derived_from(candidate, gloss):
    """Le candidat attesté est-il une forme dérivée de la glose du radical ?
    Heuristique : même racine sur les 4+ premières lettres, et candidat au moins aussi long
    (galilée -> galiléen, christ -> chrétien NON détecté, mais aucun faux positif grossier)."""
    c, g = strip_accents(candidate), strip_accents(gloss.split("/")[0].split("(")[0].strip())
    if len(c) < 4 or len(g) < 4:
        return False
    prefix = min(len(c), len(g), 5)
    return c[:prefix] == g[:prefix] and len(c) >= len(g) - 1


def pick_attested(candidates, stem_gloss):
    for cand in candidates or []:
        if looks_derived_from(cand, stem_gloss):
            return cand
    return None


def build_templates(kind, fr_g, en_g, stem=None):
    """Gabarits adaptés au type de la glose du radical, pour éviter l'absurde
    (« en train de ville »). Retourne (proposition_fr, proposition_en)."""
    fr_is_verb = bool(FR_VERB_RE.match(fr_g.strip().split()[0])) if fr_g.strip() else False
    if kind in ("agentif", "agentif_pl", "singulatif"):
        plural = kind == "agentif_pl"
        # 1) dérivation rédigée à la main : la vraie forme française/anglaise
        if stem in CURATED_AGENTIVE:
            fr_c, en_c = CURATED_AGENTIVE[stem]
            if plural:
                # accorder CHAQUE variante séparée par une virgule, sinon on obtient
                # « marin, bateliers » au lieu de « marins, bateliers »
                return (pluralize_list(fr_c) + " (pluriel)",
                        pluralize_list(en_c) + " (plural)")
            return fr_c, en_c
        if fr_is_verb:
            fr = f"celui qui {fr_g}" + (" (pluriel)" if plural else "")
            en = f"one who {en_g}" + ("s (plural)" if plural else "s")
        else:
            fr = f"habitant/personne de {fr_g}" + (" (pluriel)" if plural else "")
            en = f"person of {en_g}" + ("s (plural)" if plural else "")
        return fr, en
    if kind == "pluriel":
        return f"{fr_g} (pluriel)", f"{en_g} (plural)"
    if kind == "passe":
        return (f"{fr_g} (passé)" if fr_is_verb else f"{fr_g} (forme passée ?)"), f"{en_g} (past)"
    if kind == "progressif":
        return (f"en train de {fr_g}" if fr_is_verb else f"{fr_g} (progressif ?)"), f"{en_g} (progressive)"
    if kind == "futur":
        return (f"va {fr_g} (futur)" if fr_is_verb else f"{fr_g} (futur ?)"), f"will {en_g} (future)"
    return fr_g, en_g


def effective(row):
    return ((row.get("anufo_corrige") or "").strip() or row["anufo"]).lower()


def main():
    inject = "--inject" in sys.argv

    with open(PATH, "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]

    validated = {}
    for r in rows:
        if r.get("valide_humain"):
            fr = (r.get("fr_corrige") or "").strip()
            en = (r.get("en_corrige") or "").strip()
            if fr or en:
                validated[effective(r)] = (fr, en, r["frequence"])

    proposals = []
    for r in rows:
        if r.get("valide_humain"):
            continue
        w = effective(r)
        for rule, extract, kind in AFFIXES:
            stem = extract(w)
            if not stem or stem not in validated:
                continue
            fr_g, en_g, stem_freq = validated[stem]

            # 1) candidat attesté dans la Bible cohérent avec la glose du radical
            fr_att = pick_attested(r.get("fr_candidats"), fr_g) if fr_g else None
            en_att = pick_attested(r.get("en_candidats"), en_g) if en_g else None

            # 2) repli sur gabarit morphologique
            fr_tpl, en_tpl = build_templates(kind, fr_g or en_g, en_g or fr_g, stem)

            fr_prop = fr_att or fr_tpl
            en_prop = en_att or en_tpl

            conf = 0.2
            conf += min(len(stem) / 8.0, 1.0) * 0.4
            conf += min(stem_freq / 50.0, 1.0) * 0.2
            if kind in ("agentif", "agentif_pl", "singulatif"):
                conf += 0.15
            if rule.startswith("passé a-"):
                conf -= 0.2
            if fr_att or en_att:
                conf = max(conf, 0.9)  # forme réellement attestée dans le corpus

            proposals.append({
                "mot": w, "frequence": r["frequence"], "radical": stem,
                "glose_fr_radical": fr_g, "glose_en_radical": en_g, "regle": rule,
                "fr_propose": fr_prop, "en_propose": en_prop,
                "attestee": bool(fr_att or en_att),
                "confiance": round(max(0.0, min(1.0, conf)), 2),
                "_row": r,
            })
            break

    proposals.sort(key=lambda p: (-p["confiance"], -p["frequence"]))

    os.makedirs("reports", exist_ok=True)
    with open(REPORT, "w", encoding="utf-8", newline="") as f:
        wr = csv.writer(f, delimiter="\t")
        wr.writerow(["mot_anufo", "freq", "confiance", "attestee_bible", "regle", "radical",
                     "radical_fr_valide", "radical_en_valide", "fr_propose", "en_propose",
                     "votre_correction_fr", "votre_correction_en"])
        for p in proposals:
            wr.writerow([p["mot"], p["frequence"], p["confiance"], "OUI" if p["attestee"] else "",
                         p["regle"], p["radical"], p["glose_fr_radical"], p["glose_en_radical"],
                         p["fr_propose"], p["en_propose"], "", ""])

    if inject:
        for p in proposals:
            r = p["_row"]
            r["fr_propose"] = p["fr_propose"]
            r["en_propose"] = p["en_propose"]          # <- corrige l'incohérence FR/EN
            r["source"] = "derivation_auto"
            r["derivation"] = {
                "radical": p["radical"], "glose_fr_radical": p["glose_fr_radical"],
                "glose_en_radical": p["glose_en_radical"], "regle": p["regle"],
                "confiance": p["confiance"], "forme_attestee_bible": p["attestee"],
            }
        with open(PATH, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    att = sum(1 for p in proposals if p["attestee"])
    print(f"Propositions (FR + EN) : {len(proposals)}")
    print(f"   dont forme ATTESTEE dans la Bible (fiable) : {att}")
    print(f"   dont confiance >= 0.60                     : {sum(1 for p in proposals if p['confiance'] >= 0.6)}")
    print(f"Rapport : {REPORT}")
    print("INJECTE (fr_propose ET en_propose)." if inject else "(lecture seule)")


if __name__ == "__main__":
    main()
