# -*- coding: utf-8 -*-
"""
validator_app.py — Application web LOCALE de validation du corpus anufo.
GÉNÉRIQUE : s'adapte automatiquement au format du fichier JSONL passé en argument.
Lancement :  python validator_app.py data_norm/vocab_to_validate.jsonl
Puis ouvrir : http://localhost:5000

Deux modes, détectés automatiquement à partir des champs de la 1re ligne :
- "vocab"   : fichier au format vocabulaire actuel (anufo, fr_propose, fr_candidats...)
              -> interface INCHANGÉE par rapport à la version précédente (aucune régression).
- "generic" : tout autre format JSONL -> interface construite dynamiquement à partir des
              champs détectés (texte simple, objet imbriqué type "concept", liste de paires
              type "gloss", liste de candidats type "fr_candidats", liste d'objets à
              compléter type "phrases_creees").

Commun aux deux modes : sauvegarde continue atomique (écriture .tmp puis os.replace), reprise
à la 1re ligne non validée, barre de progression, raccourcis clavier (Entrée/↑/↓), champ
valide_humain, et un champ libre qc_note (remarque par ligne, ex. "homonyme", "à revoir").
Sortie : <nom>_validated.jsonl à côté de l'entrée. Aucune dépendance externe (http.server).
"""
import json, os, sys
from http.server import HTTPServer, BaseHTTPRequestHandler

DATA = sys.argv[1] if len(sys.argv) > 1 else "data_norm/vocab_to_validate.jsonl"
OUT = DATA.replace(".jsonl", "_validated.jsonl")
if os.path.exists(OUT):
    DATA = OUT  # reprise : on repart du fichier validé


def load():
    rows = []
    with open(DATA, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def save(rows):
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, OUT)  # écriture atomique = jamais de corruption


# --- Détection de format + schéma (mode "generic" uniquement) --------------------------------
# Signature du format vocabulaire ACTUEL (validator/build_full_vocab.py) : présence de ces
# champs précis -> on sert l'interface historique à l'identique, sans y toucher.
VOCAB_SIGNATURE = {"anufo", "fr_propose", "en_propose", "fr_candidats", "statut"}


def detect_format(row0):
    if VOCAB_SIGNATURE.issubset(row0.keys()):
        return "vocab"
    return "generic"


SKIP_SCHEMA_KEYS = {"valide_humain", "qc_note", "id"}


def build_schema(row0):
    """Une passe sur la 1re ligne -> description des champs pour construire l'UI générique.
    Le fichier est supposé homogène (mêmes champs sur toutes les lignes), donc un seul passage
    suffit — cohérent avec le reste du pipeline (JSONL homogènes par fichier)."""
    schema = []
    for key, value in row0.items():
        if key in SKIP_SCHEMA_KEYS:
            continue
        if isinstance(value, dict):
            schema.append({"key": key, "type": "object", "subfields": list(value.keys())})
        elif isinstance(value, list):
            if key == "phrases_creees" or (value and isinstance(value[0], dict)):
                item_keys = list(value[0].keys()) if value and isinstance(value[0], dict) else ["concept", "anufo", "fr", "en"]
                schema.append({"key": key, "type": "list_of_objects", "item_keys": item_keys})
            elif value and isinstance(value[0], list):
                schema.append({"key": key, "type": "list_of_pairs"})
            else:
                # liste de candidats (chaînes) : si un champ homonyme sans suffixe existe
                # (ex. fr_candidats -> fr), les puces remplissent ce champ au clic.
                base = None
                for suffix in ("_candidats", "candidats"):
                    if key.endswith(suffix):
                        candidate_base = key[: -len(suffix)].rstrip("_")
                        if candidate_base in row0:
                            base = candidate_base
                schema.append({"key": key, "type": "list_of_chips", "target": base})
        else:
            schema.append({"key": key, "type": "text"})
    return schema


ROWS = load()
FORMAT = detect_format(ROWS[0]) if ROWS else "generic"
SCHEMA = [] if FORMAT == "vocab" else build_schema(ROWS[0]) if ROWS else []

for r in ROWS:
    r.setdefault("valide_humain", False)
    r.setdefault("qc_note", "")

# --- Page mode "vocab" : INCHANGÉE (même HTML/JS qu'avant cette évolution) -------------------
PAGE_VOCAB = """<!doctype html><html lang=fr><meta charset=utf-8>
<title>Validation Anufo</title><style>
body{font-family:system-ui;margin:0;background:#f4f4f5;color:#18181b}
header{position:sticky;top:0;background:#1e293b;color:#fff;padding:12px 20px;display:flex;gap:20px;align-items:center;z-index:10}
.bar{flex:1;height:10px;background:#334155;border-radius:5px;overflow:hidden}
.fill{height:100%;background:#22c55e;width:0%}
main{display:flex;height:calc(100vh - 54px)}
#list{width:38%;overflow:auto;border-right:1px solid #ddd;background:#fff}
#focus{flex:1;padding:24px;overflow:auto}
.row{padding:8px 14px;border-bottom:1px solid #eee;cursor:pointer;display:flex;gap:10px;align-items:center}
.row:hover{background:#f0f9ff}.row.sel{background:#dbeafe}
.badge{font-size:11px;padding:2px 7px;border-radius:10px}
.fiable{background:#dcfce7;color:#166534}.averif{background:#fef9c3;color:#854d0e}
.done{background:#e0e7ff;color:#3730a3}
.anufo{font-weight:600}.card{max-width:640px}
label{display:block;margin:14px 0 4px;font-size:13px;color:#475569;font-weight:600}
input,textarea{width:100%;padding:9px;border:1px solid #cbd5e1;border-radius:6px;font-size:15px;box-sizing:border-box}
.cands{margin:6px 0;display:flex;gap:6px;flex-wrap:wrap}
.chip{background:#f1f5f9;border:1px solid #cbd5e1;padding:4px 10px;border-radius:14px;cursor:pointer;font-size:13px}
.chip:hover{background:#e2e8f0}
.btns{margin-top:20px;display:flex;gap:10px}
button{padding:10px 18px;border:0;border-radius:8px;font-size:15px;cursor:pointer}
.ok{background:#22c55e;color:#fff}.skip{background:#e2e8f0}.corr{background:#3b82f6;color:#fff}
.ex{margin-top:18px;padding:12px;background:#f8fafc;border-left:3px solid #94a3b8;font-size:14px;border-radius:4px}
small{color:#64748b}
</style>
<header>
<b>Validation Anufo — vocabulaire</b>
<div class=bar><div class=fill id=fill></div></div>
<span id=stat></span>
</header>
<main>
<div id=list></div>
<div id=focus><div class=card id=card><p>Chargement…</p></div></div>
</main>
<script>
let rows=[], cur=0;
async function api(u,d){let r=await fetch(u,{method:d?'POST':'GET',headers:{'Content-Type':'application/json'},body:d?JSON.stringify(d):null});return r.json()}
async function boot(){rows=await api('/rows');
  // reprise : 1re non validée
  let i=rows.findIndex(r=>!r.valide_humain); cur=i<0?0:i;
  render()}
function render(){
  let done=rows.filter(r=>r.valide_humain).length;
  document.getElementById('fill').style.width=(100*done/rows.length)+'%';
  document.getElementById('stat').textContent=done+' / '+rows.length+' validés';
  let L=document.getElementById('list');L.innerHTML='';
  rows.forEach((r,i)=>{let d=document.createElement('div');
    d.className='row'+(i==cur?' sel':'');
    let b=r.valide_humain?'done':(r.statut=='fiable'?'fiable':'averif');
    let bt=r.valide_humain?'validé':r.statut;
    d.innerHTML=`<span class=anufo>${r.anufo_corrige||r.anufo}</span>
      <small>${r.fr_corrige||r.fr_propose||'—'}</small>
      <span class="badge ${b}" style=margin-left:auto>${bt}</span>`;
    d.onclick=()=>{cur=i;render()};L.appendChild(d)});
  let r=rows[cur];let c=document.getElementById('card');
  let fr=r.fr_corrige||r.fr_propose||'', en=r.en_corrige||r.en_propose||'', an=r.anufo_corrige||r.anufo;
  c.innerHTML=`
    <h2>${r.anufo} <small>(${r.frequence||'?'}×, source: ${r.source||'?'})</small></h2>
    <label>Mot anufo (corriger si besoin)</label><input id=an value="${an}">
    <label>Traduction française</label><input id=fr value="${fr}">
    <div class=cands>${(r.fr_candidats||[]).map(x=>`<span class=chip onclick="document.getElementById('fr').value='${x}'">${x}</span>`).join('')}</div>
    <label>Traduction anglaise</label><input id=en value="${en}">
    <div class=cands>${(r.en_candidats||[]).map(x=>`<span class=chip onclick="document.getElementById('en').value='${x}'">${x}</span>`).join('')}</div>
    ${r.exemple&&r.exemple.anufo?`<div class=ex><b>Exemple (${r.exemple.ref||''}) :</b><br>${r.exemple.anufo}<br><small>${r.exemple.fr||''}</small></div>`:''}
    ${r.formes_fusionnees&&r.formes_fusionnees.length>1?`<div class=ex><b>⚠ Formes fusionnées par ton (à vérifier — même mot ou vrais mots distincts ?) :</b><br>${r.formes_fusionnees.map(x=>`${x.anufo} (${x.frequence}×) → ${x.fr_propose||'?'} / ${x.en_propose||'?'}`).join('<br>')}</div>`:''}
    <label>Note (qc_note, libre — ex. "homonyme", "à revoir avec X")</label>
    <textarea id=qcnote rows=2>${r.qc_note||''}</textarea>
    <div class=btns>
      <button class=ok onclick=valide(true)>✓ Valider (correct)</button>
      <button class=corr onclick=valide(false)>✎ Enregistrer correction</button>
      <button class=skip onclick=next()>Passer →</button>
    </div>
    <p><small>Raccourcis : Entrée = valider · flèches ↑↓ = naviguer</small></p>`;
}
async function valide(asis){let r=rows[cur];
  r.anufo_corrige=document.getElementById('an').value;
  r.fr_corrige=document.getElementById('fr').value;
  r.en_corrige=document.getElementById('en').value;
  r.qc_note=document.getElementById('qcnote').value;
  r.valide_humain=true;
  await api('/save',{index:cur,row:r});    // SAUVEGARDE IMMÉDIATE
  next();}
function next(){if(cur<rows.length-1)cur++;render()}
function prev(){if(cur>0)cur--;render()}
document.addEventListener('keydown',e=>{
  if(document.activeElement&&document.activeElement.tagName=='TEXTAREA'&&e.key=='Enter')return;
  if(e.key=='Enter'){e.preventDefault();valide(true)}
  if(e.key=='ArrowDown'){e.preventDefault();next()}
  if(e.key=='ArrowUp'){e.preventDefault();prev()}});
boot();
</script></html>"""

# --- Page mode "generic" : UI construite dynamiquement à partir du schéma détecté ------------
PAGE_GENERIC = """<!doctype html><html lang=fr><meta charset=utf-8>
<title>Validation Anufo — générique</title><style>
body{font-family:system-ui;margin:0;background:#f4f4f5;color:#18181b}
header{position:sticky;top:0;background:#1e293b;color:#fff;padding:12px 20px;display:flex;gap:20px;align-items:center;z-index:10}
.bar{flex:1;height:10px;background:#334155;border-radius:5px;overflow:hidden}
.fill{height:100%;background:#22c55e;width:0%}
main{display:flex;height:calc(100vh - 54px)}
#list{width:38%;overflow:auto;border-right:1px solid #ddd;background:#fff}
#focus{flex:1;padding:24px;overflow:auto}
.row{padding:8px 14px;border-bottom:1px solid #eee;cursor:pointer;display:flex;gap:10px;align-items:center}
.row:hover{background:#f0f9ff}.row.sel{background:#dbeafe}
.badge{font-size:11px;padding:2px 7px;border-radius:10px}
.averif{background:#fef9c3;color:#854d0e}.done{background:#e0e7ff;color:#3730a3}
.card{max-width:720px}
label{display:block;margin:14px 0 4px;font-size:13px;color:#475569;font-weight:600}
input,textarea{width:100%;padding:9px;border:1px solid #cbd5e1;border-radius:6px;font-size:15px;box-sizing:border-box}
fieldset{border:1px solid #cbd5e1;border-radius:8px;margin:14px 0;padding:10px 14px}
legend{font-size:13px;color:#475569;font-weight:600;padding:0 6px}
.cands{margin:6px 0;display:flex;gap:6px;flex-wrap:wrap}
.chip{background:#f1f5f9;border:1px solid #cbd5e1;padding:4px 10px;border-radius:14px;cursor:pointer;font-size:13px}
.chip:hover{background:#e2e8f0}
.pair{display:flex;gap:8px;margin:6px 0}
.pair input{flex:1}
.pair button,.objcard button{background:#fee2e2;color:#991b1b;border:0;border-radius:6px;padding:6px 10px;cursor:pointer}
.objcard{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px;margin:8px 0}
.objcard div{font-size:14px;margin:2px 0}
.addbtn{background:#e0e7ff;color:#3730a3;border:0;border-radius:6px;padding:8px 12px;cursor:pointer;margin-top:6px}
.btns{margin-top:20px;display:flex;gap:10px}
button.main{padding:10px 18px;border:0;border-radius:8px;font-size:15px;cursor:pointer}
.ok{background:#22c55e;color:#fff}.skip{background:#e2e8f0}
small{color:#64748b}
</style>
<header>
<b>Validation Anufo — format générique</b>
<div class=bar><div class=fill id=fill></div></div>
<span id=stat></span>
</header>
<main>
<div id=list></div>
<div id=focus><div class=card id=card><p>Chargement…</p></div></div>
</main>
<script>
const SCHEMA = __SCHEMA__;
let rows=[], cur=0;
async function api(u,d){let r=await fetch(u,{method:d?'POST':'GET',headers:{'Content-Type':'application/json'},body:d?JSON.stringify(d):null});return r.json()}
async function boot(){rows=await api('/rows');
  let i=rows.findIndex(r=>!r.valide_humain); cur=i<0?0:i;
  render()}
function summarize(r){
  for(const f of SCHEMA){ if(f.type=='text' && r[f.key]) return String(r[f.key]); }
  return '(ligne '+(rows.indexOf(r)+1)+')';
}
function render(){
  let done=rows.filter(r=>r.valide_humain).length;
  document.getElementById('fill').style.width=(100*done/rows.length)+'%';
  document.getElementById('stat').textContent=done+' / '+rows.length+' validés';
  let L=document.getElementById('list');L.innerHTML='';
  rows.forEach((r,i)=>{let d=document.createElement('div');
    d.className='row'+(i==cur?' sel':'');
    d.innerHTML=`<span>${summarize(r)}</span>
      <span class="badge ${r.valide_humain?'done':'averif'}" style=margin-left:auto>${r.valide_humain?'validé':'à valider'}</span>`;
    d.onclick=()=>{cur=i;render()};L.appendChild(d)});
  renderCard();
}
function fieldHtml(f, r){
  const val = r[f.key];
  if(f.type=='text'){
    return `<label>${f.key}</label><input data-k="${f.key}" value="${(val==null?'':val).toString().replace(/"/g,'&quot;')}">`;
  }
  if(f.type=='object'){
    let sub = f.subfields.map(sk=>{
      let v=(val&&val[sk]!=null)?val[sk]:'';
      return `<label>${sk}</label><input data-k="${f.key}.${sk}" value="${String(v).replace(/"/g,'&quot;')}">`;
    }).join('');
    return `<fieldset><legend>${f.key}</legend>${sub}</fieldset>`;
  }
  if(f.type=='list_of_chips'){
    let chips=(val||[]).map(x=>`<span class=chip onclick="fillChip('${f.target||''}','${String(x).replace(/'/g,"\\\\'")}')">${x}</span>`).join('');
    return `<label>${f.key}</label><div class=cands>${chips||'<small>—</small>'}</div>`;
  }
  if(f.type=='list_of_pairs'){
    let pairs=(val||[]).map((p,pi)=>`<div class=pair>
        <input data-pair="${f.key}.${pi}.0" value="${String(p[0]||'').replace(/"/g,'&quot;')}">
        <input data-pair="${f.key}.${pi}.1" value="${String(p[1]||'').replace(/"/g,'&quot;')}">
        <button onclick="removePair('${f.key}',${pi})">✕</button></div>`).join('');
    return `<fieldset><legend>${f.key}</legend><div id="pairs_${f.key}">${pairs}</div>
      <button class=addbtn onclick="addPair('${f.key}')">+ ajouter une paire</button></fieldset>`;
  }
  if(f.type=='list_of_objects'){
    let items=(val||[]).map((o,oi)=>`<div class=objcard>${f.item_keys.map(k=>`<div><b>${k}:</b> ${typeof o[k]=='object'?JSON.stringify(o[k]):(o[k]||'')}</div>`).join('')}
      <button onclick="removeObj('${f.key}',${oi})">✕ retirer</button></div>`).join('');
    let form=f.item_keys.map(k=>`<input placeholder="${k}" data-newobj="${f.key}.${k}">`).join('');
    return `<fieldset><legend>${f.key}</legend>${items||'<small>Aucun élément</small>'}
      <div class=pair>${form}</div>
      <button class=addbtn onclick="addObj('${f.key}')">+ ajouter</button></fieldset>`;
  }
  return '';
}
function renderCard(){
  let r=rows[cur];let c=document.getElementById('card');
  let html = SCHEMA.map(f=>fieldHtml(f,r)).join('');
  html += `<label>Note (qc_note, libre — ex. "homonyme", "à revoir avec X")</label>
    <textarea id=qcnote rows=2>${r.qc_note||''}</textarea>
    <div class=btns>
      <button class="main ok" onclick=valide()>✓ Valider / enregistrer</button>
      <button class="main skip" onclick=next()>Passer →</button>
    </div>
    <p><small>Raccourcis : Entrée = valider · flèches ↑↓ = naviguer</small></p>`;
  c.innerHTML = html;
}
function fillChip(target, val){ if(!target)return; let el=document.querySelector(`[data-k="${target}"]`); if(el) el.value=val; }
function getPath(obj,path){let parts=path.split('.');let o=obj;for(let i=0;i<parts.length-1;i++){o=o[parts[i]]=o[parts[i]]||{};}return {o,k:parts[parts.length-1]};}
function addPair(key){ rows[cur][key]=rows[cur][key]||[]; rows[cur][key].push(["",""]); renderCard(); }
function removePair(key,idx){ rows[cur][key].splice(idx,1); renderCard(); }
function addObj(key){
  let obj={}; document.querySelectorAll(`[data-newobj^="${key}."]`).forEach(el=>{
    let k=el.getAttribute('data-newobj').split('.').slice(1).join('.'); obj[k]=el.value; });
  rows[cur][key]=rows[cur][key]||[]; rows[cur][key].push(obj); renderCard();
}
function removeObj(key,idx){ rows[cur][key].splice(idx,1); renderCard(); }
async function valide(){
  let r=rows[cur];
  document.querySelectorAll('[data-k]').forEach(el=>{
    let path=el.getAttribute('data-k');
    if(path.includes('.')){ let [k,sk]=path.split('.'); r[k]=r[k]||{}; r[k][sk]=el.value; }
    else { r[path]=el.value; }
  });
  document.querySelectorAll('[data-pair]').forEach(el=>{
    let [key,idx,pos]=el.getAttribute('data-pair').split('.');
    r[key][+idx][+pos]=el.value;
  });
  r.qc_note=document.getElementById('qcnote').value;
  r.valide_humain=true;
  await api('/save',{index:cur,row:r});
  next();
}
function next(){if(cur<rows.length-1)cur++;render()}
function prev(){if(cur>0)cur--;render()}
document.addEventListener('keydown',e=>{
  if(document.activeElement&&document.activeElement.tagName=='TEXTAREA'&&e.key=='Enter')return;
  if(e.key=='Enter'){e.preventDefault();valide()}
  if(e.key=='ArrowDown'){e.preventDefault();next()}
  if(e.key=='ArrowUp'){e.preventDefault();prev()}});
boot();
</script></html>"""


class H(BaseHTTPRequestHandler):
    def _send(self, body, ct="application/json"):
        self.send_response(200)
        self.send_header("Content-Type", ct)
        # Sans ça, Firefox (plus agressif que Chrome sur le cache HTTP par défaut) peut resservir
        # une VIEILLE version de la page/JS après un redémarrage du serveur -> boutons "morts"
        # car ils appellent des fonctions JS qui ont changé/disparu côté serveur redémarré.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_GET(self):
        if self.path == "/":
            if FORMAT == "vocab":
                self._send(PAGE_VOCAB, "text/html; charset=utf-8")
            else:
                page = PAGE_GENERIC.replace("__SCHEMA__", json.dumps(SCHEMA, ensure_ascii=False))
                self._send(page, "text/html; charset=utf-8")
        elif self.path == "/rows":
            self._send(json.dumps(ROWS, ensure_ascii=False))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        d = json.loads(self.rfile.read(n) or "{}")
        if self.path == "/save":
            row = d["row"]
            ROWS[d["index"]] = row

            # RELECTURE DU DISQUE AVANT ÉCRITURE : sans ça, l'app réécrit tout le fichier depuis
            # sa mémoire et ANNULE toute modification externe faite pendant qu'elle tourne
            # (constaté en vrai : un script de dédoublonnage a vu ses 241 suppressions écrasées
            # à la validation suivante). On repart donc du fichier sur disque, on n'y remplace
            # QUE la ligne éditée (identifiée par son mot anufo d'origine, stable même si les
            # id sont renumérotés par un script externe), et on réécrit.
            try:
                disk_rows = load()
            except Exception:
                disk_rows = None

            if disk_rows:
                key = row.get("anufo")
                replaced = False
                for i, dr in enumerate(disk_rows):
                    if dr.get("anufo") == key:
                        disk_rows[i] = row
                        replaced = True
                        break
                if replaced:
                    save(disk_rows)
                    ROWS[:] = disk_rows
                    self._send(json.dumps({"ok": True, "total": len(disk_rows)}))
                    return
                # la ligne n'existe plus sur disque (retirée par un script externe) : on ne la
                # réinjecte pas, on signale au client qu'il doit recharger.
                ROWS[:] = disk_rows
                self._send(json.dumps({"ok": False, "stale": True, "total": len(disk_rows)}))
                return

            save(ROWS)
            self._send('{"ok":true}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"Données : {DATA}")
    print(f"Sortie  : {OUT} (sauvegarde continue)")
    print(f"Format détecté : {FORMAT}" + (f" (champs : {[f['key'] for f in SCHEMA]})" if FORMAT == "generic" else ""))
    print("Ouvre ton navigateur sur : http://localhost:5000")
    HTTPServer(("127.0.0.1", 5000), H).serve_forever()
