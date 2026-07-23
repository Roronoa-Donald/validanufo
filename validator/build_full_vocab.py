# -*- coding: utf-8 -*-
"""
build_full_vocab.py — prépare TOUT le vocabulaire biblique pour validation humaine.
AUCUN mot biblique laissé de côté. Pour chaque mot UNIQUE :
  - déjà glosé (lexique/interlinéaire) → proposé comme 'fiable' avec sa traduction
  - sinon → traduction fr/en la plus probable par RÉCURRENCE (co-occurrence Dice)
Sortie = fichier de travail pour l'app de validation.

Rappel d'échelle : le NT anufo = ~235 000 tokens mais seulement ~4500 mots UNIQUES.
On valide chaque mot UNE fois, pas à chaque occurrence.
"""
import json, csv, re, collections, unicodedata, glob, os

def norm(t):
    t=unicodedata.normalize("NFD",t).replace("\u0300","")
    t=unicodedata.normalize("NFC",t)
    t=re.sub(r"ñ(?=[aeiouɛɔ])","ny",t); t=re.sub(r"ñ(?=[a-zɛɔŋ])","n",t)
    for a,b in [("ĩ","in"),("ũ","un"),("ã","an"),("ɛ̃","ɛn"),("ɔ̃","ɔn"),("ʃ","s"),("ꭍ","s"),("ʒ","z"),("dʒ","j"),("tʃ","c"),("ɪ","i"),("ʊ","u")]:
        t=t.replace(a,b)
    return t

STOP_FR=set("de la le les un une des et à a au aux en du que qui ce se il elle ils elles on ne pas sa son ses leur d l n s est ont a".split())
STOP_EN=set("the a an of and to in he she it they them his her that who this is was for be as not so on with".split())
GRAM=set("na ne ka bo i n o a ni nu ma wo be dɛ tɔ ama nsɛ dama yiri bi ya am u m".split())

def load_existing():
    g=collections.defaultdict(list)
    for e in json.load(open("data/raw/chakosi_lexicon.json",encoding="utf-8")):
        g[norm(e["chakosi"])].append((e["english"],"lexique"))
    p="data/raw/chakosi_interlinear_corpus.csv"
    if os.path.exists(p):
        for row in csv.DictReader(open(p,encoding="utf-8")):
            aw=row["chakosi"].split(); gl=row["gloss_interlinear"].split()
            if len(aw)==len(gl):
                for a,gg in zip(aw,gl): g[norm(a.lower())].append((gg,"interlinéaire"))
    return g

def run():
    existing=load_existing()
    freq=collections.Counter()
    cooc_fr=collections.defaultdict(collections.Counter); cnt_fr=collections.Counter()
    cooc_en=collections.defaultdict(collections.Counter); cnt_en=collections.Counter()
    example_verse={}
    for path in sorted(glob.glob("data/raw/anufo_nt_partie_*.jsonl")):
        for line in open(path,encoding="utf-8"):
            d=json.loads(line)
            if not d.get("alignment_ok"): continue
            A=[norm(w) for w in re.findall(r"[a-zɛɔŋáéíóú]+",d["anufo"].lower())]
            FR=[w for w in re.findall(r"[a-zàâçéèêëîïôùûü]+",d["french"].lower()) if w not in STOP_FR]
            EN=[w for w in re.findall(r"[a-z]+",d["english"].lower()) if w not in STOP_EN]
            for w in set(A):
                freq[w]+=1
                if w not in example_verse:               # 1 phrase-exemple par mot
                    example_verse[w]={"anufo":d["anufo"],"fr":d["french"],"en":d["english"],
                                      "ref":f"{d['book_code']} {d['chapter']}:{d['verse']}"}
            for w in set(FR): cnt_fr[w]+=1
            for w in set(EN): cnt_en[w]+=1
            for a in set(A):
                for fr in set(FR): cooc_fr[a][fr]+=1
                for en in set(EN): cooc_en[a][en]+=1

    def best(cooc,cnt,w,f):
        out=[]
        for t,c in cooc[w].items():
            if c>=max(2,f*0.15):
                out.append((round(2*c/(f+cnt[t]),3),t))
        return [t for _,t in sorted(out,reverse=True)[:3]]

    rows=[]
    for w,f in freq.most_common():
        known=existing.get(w,[])
        is_gram = w in GRAM
        fr_cand=best(cooc_fr,cnt_fr,w,f)
        en_cand=best(cooc_en,cnt_en,w,f)
        # statut proposé
        if known:
            statut="fiable"; fr=known[0][0] if known else ""; src=known[0][1]
        elif is_gram:
            statut="a_verifier"; fr=(fr_cand[0] if fr_cand else ""); src="grammatical"
        elif fr_cand:
            statut="a_verifier"; fr=fr_cand[0]; src="recurrence"
        else:
            statut="a_verifier"; fr=""; src="hapax_sans_candidat"
        ev=example_verse.get(w,{})
        rows.append({
            "id": f"W{len(rows)+1:05d}",
            "anufo": w,
            "frequence": f,
            "fr_propose": fr,
            "en_propose": (known[0][0] if known and src=="interlinéaire" else (en_cand[0] if en_cand else "")),
            "fr_candidats": fr_cand,
            "en_candidats": en_cand,
            "glose_existante": [g for g,_ in known[:3]],
            "source": src,
            "statut": statut,           # fiable / a_verifier
            "valide_humain": False,     # passe à True dans l'app
            "anufo_corrige": "",        # rempli si l'humain corrige
            "fr_corrige": "", "en_corrige": "",
            "exemple": ev,              # phrase-exemple pour créer des phrases
            "phrases_creees": []        # l'humain y ajoute ses phrases {concept,anufo,fr,en}
        })
    os.makedirs("data_norm",exist_ok=True)
    with open("data_norm/vocab_to_validate.jsonl","w",encoding="utf-8") as f:
        for r in rows: f.write(json.dumps(r,ensure_ascii=False)+"\n")

    tot=len(rows); fiable=sum(1 for r in rows if r["statut"]=="fiable")
    rec=sum(1 for r in rows if r["source"]=="recurrence")
    hap=sum(1 for r in rows if r["source"]=="hapax_sans_candidat")
    print(f"Mots UNIQUES du corpus biblique (aucun laissé) : {tot}")
    print(f"  proposés fiables (déjà glosés)        : {fiable}")
    print(f"  traduction proposée par récurrence    : {rec}")
    print(f"  sans candidat (hapax difficile)       : {hap}")
    print(f"  → 100% des mots sont dans le fichier, chacun avec un statut.")
    print(f"Fichier : data_norm/vocab_to_validate.jsonl")

if __name__=="__main__": run()
