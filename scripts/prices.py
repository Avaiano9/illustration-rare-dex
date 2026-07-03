#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coletor de preços e imagens — versão 3.

PARTE 1 — PREÇOS (TCGcsv, gratuito, sem token):
  O tcgcsv.com redistribui diariamente os preços oficiais do TCGplayer.
  - /tcgplayer/3/groups              -> sets de Pokémon (groupId, name, abbreviation)
  - /tcgplayer/3/{gid}/products      -> cartas do set (productId, número)
  - /tcgplayer/3/{gid}/prices        -> preços por variante (marketPrice etc., USD)
  Casamos os sets pela ABREVIAÇÃO (mesmos códigos do limmap: CRI, PAF, MEW...)
  e, em segunda tentativa, pelo nome. Guardamos o MENOR preço de mercado entre
  as variantes de cada carta. Conversão USD->BRL pelo BCE (frankfurter.app).

PARTE 2 — IMAGENS (TCG Codex, token gratuito, só catálogo):
  O plano gratuito dá acesso a /sets e /cards (não a /prices). Aproveitamos o
  campo `image` da listagem para alimentar a 4ª fonte de imagens do site.
  Roda apenas se TCGCODEX_TOKEN existir; é retomável via cursor.

Saída: data/prices.json
  {"source","updated","currency":"USD","brl_rate",{...},"cards":{chave: usd},
   "imgs":{chave: url}}  — chave = nome do nosso set normalizado + "|" + número.
Só biblioteca padrão.
"""

import json, os, re, time, urllib.request, urllib.parse, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
TCGCSV = "https://tcgcsv.com/tcgplayer/3"     # 3 = Pokémon
CODEX  = "https://tcgcodex.com/api/v1"
TOKEN  = (os.environ.get("TCGCODEX_TOKEN") or "").strip()

MAX_REQUESTS = int(os.environ.get("PRICES_MAX_REQUESTS", "260"))
SLEEP = 0.3
req_count = 0

def load(name, default):
    try: return json.load(open(os.path.join(DATA, name), encoding="utf-8"))
    except Exception: return default

def save(name, obj):
    json.dump(obj, open(os.path.join(DATA, name), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"), sort_keys=True)

class Budget(RuntimeError): pass

def http_json(url, bearer=None):
    global req_count
    if req_count >= MAX_REQUESTS: raise Budget("teto de requisições da execução")
    h = {"Accept": "application/json", "User-Agent": "irdex/3.0 (pessoal)"}
    if bearer: h["Authorization"] = "Bearer " + bearer
    req = urllib.request.Request(url, headers=h)
    for tent in (1, 2, 3):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                req_count += 1; time.sleep(SLEEP)
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 403) and tent < 3:
                print(f"  HTTP {e.code}; aguardando {15*tent}s…"); time.sleep(15*tent); continue
            if e.code == 404: return None
            raise
    return None

# ---------- normalizações (idênticas às do site) ----------
def setkey(name): return re.sub(r"[^a-z0-9]", "", (name or "").lower())
def numkey(num):  return re.sub(r"[^A-Z0-9]", "", str(num or "").upper())
def loosenum(num):
    n = numkey(num); m = re.fullmatch(r"0*(\d+)", n)
    return m.group(1) if m else n

def wanted_map():
    """(código, nº frouxo) -> {(nosso set, nosso nº)} — base IR/SIR + extras."""
    tracker = load("tracker.json", []); extras = load("extras.json", [])
    limmap = load("limmap.json", {})
    w = {}
    def note(sn, num):
        code = limmap.get(sn)
        if code: w.setdefault((code, loosenum(num)), set()).add((sn, str(num)))
    for s in tracker:
        for c in s["cards"]: note(c.get("set"), c.get("num"))
    for e in extras: note(e.get("set"), e.get("num"))
    return w, limmap

# =====================================================================
# PARTE 1 — preços do TCGcsv
# =====================================================================
def precos_tcgcsv(wanted, limmap, cards_out):
    codes = {c for c, _ in wanted}
    nomes = {setkey(n): limmap[n] for n in limmap}
    print("PREÇOS (TCGcsv/TCGplayer)…")
    grupos = (http_json(f"{TCGCSV}/groups") or {}).get("results") or []
    print(f"  grupos de Pokémon no TCGplayer: {len(grupos)}")
    casados = []
    for g in grupos:
        ab = str(g.get("abbreviation") or "").upper()
        nk = setkey(g.get("name") or "")
        code = ab if ab in codes else nomes.get(nk)
        if code and code in codes:
            casados.append((g.get("groupId"), code, g.get("name")))
    print(f"  sets casados: {len(casados)}")
    novos = 0
    for gid, code, gname in casados:
        prods = (http_json(f"{TCGCSV}/{gid}/products") or {}).get("results") or []
        precos = (http_json(f"{TCGCSV}/{gid}/prices") or {}).get("results") or []
        por_prod = {}
        for p in precos:
            v = p.get("marketPrice") or p.get("midPrice") or p.get("lowPrice")
            try: v = float(v)
            except (TypeError, ValueError): continue
            if v <= 0: continue
            pid = p.get("productId")
            por_prod[pid] = min(v, por_prod.get(pid, v))
        n_set = 0
        for pr in prods:
            num = None
            for ed in (pr.get("extendedData") or []):
                if str(ed.get("name", "")).lower() in ("number", "card number"):
                    num = str(ed.get("value", "")).split("/")[0].strip(); break
            if not num: continue
            key = (code, loosenum(num))
            if key not in wanted: continue
            v = por_prod.get(pr.get("productId"))
            if v is None: continue
            for sn, on in wanted[key]:
                k = f"{setkey(sn)}|{numkey(on)}"
                cards_out[k] = min(round(v, 2), cards_out.get(k, 10**9))
                n_set += 1; novos += 1
        if n_set: print(f"  {code} ({gname}): {n_set} preços")
    print(f"  preços gravados/atualizados: {novos}")

# =====================================================================
# PARTE 2 — imagens do TCG Codex (catálogo; retomável)
# =====================================================================
def imagens_codex(wanted, limmap, imgs_out):
    if not TOKEN:
        print("IMAGENS (Codex): sem token — etapa pulada."); return
    print("IMAGENS (TCG Codex)…")
    cur = load("codex_cursor.json", {"sets": None, "done": []})
    codes = {c for c, _ in wanted}
    byname = {setkey(n): limmap[n] for n in limmap}
    def pag(path, **params):
        page = 1
        while True:
            qs = [("page", page), ("per_page", 100)]
            for k, v in params.items():
                if isinstance(v, list):
                    for x in v: qs.append((k + "[]", x))
                else: qs.append((k, v))
            j = http_json(CODEX + path + "?" + urllib.parse.urlencode(qs), bearer=TOKEN)
            if not j: return
            for it in (j.get("data") or []): yield it
            meta = j.get("meta") or {}
            if page >= int(meta.get("last_page") or 1): break
            page += 1
    A = lambda o: o.get("attributes") if isinstance(o.get("attributes"), dict) else o
    try:
        if cur["sets"] is None:
            idx, vistos = [], set()
            for s in pag("/sets"):
                c = A(s); sid = s.get("id") or c.get("id")
                if not sid or sid in vistos: continue
                game = str(((c.get("game") or {}).get("name")) or "").lower()
                if game and "pokemon" not in game: continue
                ident = str(c.get("identifier") or "").upper()
                code = ident if ident in codes else byname.get(setkey(c.get("name") or ""))
                if code and code in codes:
                    idx.append({"id": sid, "code": code}); vistos.add(sid)
            cur["sets"] = idx; save("codex_cursor.json", cur)
            print(f"  sets casados no Codex: {len(idx)}")
        for cs in cur["sets"]:
            if cs["id"] in cur["done"]: continue
            n = 0
            for card in pag("/cards", set_id=[cs["id"]]):
                c = A(card)
                num = c.get("number") or c.get("collector_number")
                img = c.get("image")
                if not num or not img: continue
                key = (cs["code"], loosenum(str(num).split("/")[0]))
                for sn, on in (wanted.get(key) or []):
                    imgs_out[f"{setkey(sn)}|{numkey(on)}"] = "https://tcgcodex.com/" + str(img).lstrip("/")
                    n += 1
            cur["done"].append(cs["id"]); save("codex_cursor.json", cur)
            if n: print(f"  {cs['code']}: {n} imagens")
        if all(cs["id"] in cur["done"] for cs in cur["sets"]):
            save("codex_cursor.json", {"sets": None, "done": []})
            print("  ciclo de imagens completo.")
    except Budget as e:
        print(f"  pausa nas imagens: {e} (cursor salvo; continua na próxima).")
    except urllib.error.HTTPError as e:
        print(f"  aviso Codex: HTTP {e.code} — etapa de imagens adiada para a próxima rodada.")

# =====================================================================
def main():
    wanted, limmap = wanted_map()
    print(f"cartas de interesse (base+extras): {len(wanted)}")
    prices = load("prices.json", {}) or {}
    cards_out = prices.get("cards", {})
    imgs_out  = prices.get("imgs", {})

    try:
        precos_tcgcsv(wanted, limmap, cards_out)
    except Budget as e:
        print(f"pausa nos preços: {e}")
    except Exception as e:
        print(f"aviso: TCGcsv indisponível nesta rodada ({e}); mantendo preços anteriores.")

    imagens_codex(wanted, limmap, imgs_out)

    rate = prices.get("brl_rate"); rate_date = prices.get("rate_date")
    try:
        j = http_json("https://api.frankfurter.app/latest?from=USD&to=BRL")
        v = ((j or {}).get("rates") or {}).get("BRL")
        if v: rate, rate_date = round(float(v), 4), j.get("date")
    except Exception as e:
        print(f"aviso: cotação indisponível ({e}); mantendo a anterior.")

    save("prices.json", {"source": "TCGplayer via TCGcsv",
                         "updated": datetime.date.today().isoformat(),
                         "currency": "USD", "brl_rate": rate, "rate_date": rate_date,
                         "cards": cards_out, "imgs": imgs_out})
    print(f"prices.json: {len(cards_out)} preços | {len(imgs_out)} imagens | req: {req_count} | US$ 1 = R$ {rate}")

if __name__ == "__main__":
    main()
