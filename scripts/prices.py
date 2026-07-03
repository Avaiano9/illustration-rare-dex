#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coletor de preços — TCG Codex API (/api/v1), com conversão automática EUR->BRL.

Fluxo (retomável entre execuções via data/price_cursor.json):
  A) /api/v1/sets (paginado): casa os sets do Codex com os nossos pelo
     `set_identifier` (mesmos códigos do data/limmap.json: CRI, MEP, XYP...).
  B) /api/v1/cards?set_id[]=N (paginado): coleta id + número das cartas que
     nos interessam (as da BASE IR/SIR + extras — são elas que alimentam as
     estimativas do painel).
  C) /api/v1/cards/{id}/prices: uma chamada por carta; usa o MENOR preço
     positivo entre as variantes (Normal, Reverse Holo...). Moeda: EUR.
  D) Cotação EUR->BRL do Banco Central Europeu (frankfurter.app, sem chave).

Saída: data/prices.json
  {"source","updated","currency":"EUR","eur_brl":taxa,"rate_date",
   "cards":{"<setkey>|<NUM>": preco_em_euros}}
A chave replica a normalização do site: nome do nosso set minúsculo sem
pontuação + "|" + número em maiúsculas só alfanumérico (zeros preservados).

Se TCGCODEX_TOKEN não existir, sai sem erro. Só biblioteca padrão.
"""

import json, os, re, time, urllib.request, urllib.parse, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
API  = "https://tcgcodex.com/api/v1"
TOKEN = (os.environ.get("TCGCODEX_TOKEN") or "").strip()

MAX_REQUESTS = int(os.environ.get("PRICES_MAX_REQUESTS", "220"))
SLEEP = float(os.environ.get("PRICES_SLEEP", "0.7"))
PER_PAGE = 100

req_count = 0

def load(name, default):
    try: return json.load(open(os.path.join(DATA, name), encoding="utf-8"))
    except Exception: return default

def save(name, obj):
    json.dump(obj, open(os.path.join(DATA, name), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"), sort_keys=True)

class Budget(RuntimeError): pass

def get(path, **params):
    global req_count
    if req_count >= MAX_REQUESTS: raise Budget("teto de requisições da execução")
    qs = []
    for k, v in params.items():
        if isinstance(v, (list, tuple)):
            for x in v: qs.append((k + "[]", x))
        elif v is not None:
            qs.append((k, v))
    url = API + path + ("?" + urllib.parse.urlencode(qs) if qs else "")
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "Authorization": "Bearer " + TOKEN,
        "User-Agent": "irdex-precos/2.0 (pessoal; %.1fs entre chamadas)" % SLEEP})
    for tent in (1, 2, 3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                req_count += 1; time.sleep(SLEEP)
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print(f"  429; aguardando {20*tent}s…"); time.sleep(20*tent); continue
            if e.code in (401, 403):
                raise RuntimeError(f"HTTP {e.code}: token recusado — confira o segredo TCGCODEX_TOKEN")
            if e.code == 404: return None
            raise
    raise Budget("limite de taxa persistente (429)")

def paginate(path, **params):
    page = 1
    while True:
        j = get(path, page=page, per_page=PER_PAGE, **params)
        if not j: return
        for item in (j.get("data") or []): yield item
        meta = j.get("meta") or {}
        if page >= int(meta.get("last_page") or 1): break
        page += 1

# ---------- normalizações (idênticas às do site) ----------
def setkey(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())

def numkey(num):   # como o site: maiúsculo, só alfanumérico, zeros preservados
    return re.sub(r"[^A-Z0-9]", "", str(num or "").upper())

def loosenum(num): # para casar 080 <-> 80 entre bases diferentes
    n = numkey(num); m = re.fullmatch(r"0*(\d+)", n)
    return m.group(1) if m else n

def attr(obj):     # objetos vêm como {type,id,attributes:{...}}
    return obj.get("attributes") if isinstance(obj.get("attributes"), dict) else obj

def find_number(card):
    c = attr(card)
    for k in ("collector_number", "number", "card_number", "num", "local_id", "localId"):
        v = c.get(k)
        if v is not None and str(v).strip():
            return str(v).split("/")[0].strip()
    for k in ("number_display", "identifier", "code", "name_number"):
        v = c.get(k)
        if isinstance(v, str) and v.strip():
            m = re.search(r"([A-Za-z]{0,4}\d+[a-z]?)\s*/", v)
            if m: return m.group(1)
    return None

def main():
    if not TOKEN:
        print("TCGCODEX_TOKEN ausente — etapa de preços pulada."); return

    tracker = load("tracker.json", [])
    extras  = load("extras.json", [])
    limmap  = load("limmap.json", {})
    cursor  = load("price_cursor.json", {"stage": "A", "codex_sets": [], "pend": [], "done_sets": []})
    prices  = load("prices.json", {}) or {}
    cards_out = prices.get("cards", {})
    imgs_out  = prices.get("imgs", {})

    # cartas de interesse: BASE + extras -> (código, nº frouxo) -> [(nosso set, nosso nº)]
    wanted = {}
    def note(setname, num):
        code = limmap.get(setname)
        if code: wanted.setdefault((code, loosenum(num)), set()).add((setname, str(num)))
    for s in tracker:
        for c in s["cards"]: note(c.get("set"), c.get("num"))
    for e in extras: note(e.get("set"), e.get("num"))
    codes = {c for c, _ in wanted}
    print(f"cartas de interesse (base+extras): {len(wanted)} em {len(codes)} códigos de set")

    try:
        # ---------- A) índice de sets ----------
        if cursor["stage"] == "A":
            idx = []
            totals = load("set_totals.json", {})
            tot_add = 0
            print("A) baixando índice de sets…")
            for s in paginate("/sets"):
                c = attr(s)
                ident = str(c.get("identifier") or c.get("set_identifier") or "").upper()
                sid = s.get("id") or c.get("id")
                game = str(((c.get("game") or {}).get("name")) or "").lower()
                if not (ident in codes and sid): continue
                if game and "pokemon" not in game:      # evita colisão com Lorcana/Magic etc.
                    print(f"   ignorando {ident} do jogo {game!r}"); continue
                idx.append({"id": sid, "ident": ident, "nome": c.get("name") or ""})
                ptotal = c.get("card_printed_total")
                if ptotal:
                    for (cd, _), pares in wanted.items():
                        if cd != ident: continue
                        for sn, _n in pares:
                            if sn not in totals and "Promo" not in sn:
                                totals[sn] = int(ptotal); tot_add += 1
            if tot_add:
                save("set_totals.json", totals)
                print(f"   totais impressos completados: {tot_add}")
            cursor["codex_sets"] = idx; cursor["stage"] = "B"
            save("price_cursor.json", cursor)
            print(f"   sets casados: {len(idx)}")

        # ---------- B) ids das cartas ----------
        if cursor["stage"] == "B":
            print("B) coletando ids das cartas…")
            for cs in cursor["codex_sets"]:
                if cs["id"] in cursor["done_sets"]: continue
                hits = 0
                for card in paginate("/cards", **{"set_id": [cs["id"]]}):
                    c = attr(card); cid = card.get("id") or c.get("id")
                    num = find_number(card)
                    if not cid or num is None: continue
                    key = (cs["ident"], loosenum(num))
                    if key in wanted:
                        alvo = [f"{setkey(sn)}|{numkey(on)}" for sn, on in wanted[key]]
                        img = c.get("image")
                        if img:
                            for k in alvo:
                                imgs_out[k] = "https://tcgcodex.com/" + str(img).lstrip("/")
                        cursor["pend"].append({"cid": cid, "keys": alvo}); hits += 1
                cursor["done_sets"].append(cs["id"])
                save("price_cursor.json", cursor)
                print(f"   {cs['ident']}: {hits} cartas de interesse")
            cursor["stage"] = "C"; save("price_cursor.json", cursor)
            print(f"   fila de preços: {len(cursor['pend'])} cartas")

        # ---------- C) preços, carta a carta ----------
        if cursor["stage"] == "C":
            print(f"C) preços ({len(cursor['pend'])} na fila)…")
            exemplo = False
            while cursor["pend"]:
                item = cursor["pend"][0]
                j = get(f"/cards/{item['cid']}/prices")
                vals = []
                for row in ((j or {}).get("data") or []):
                    a = attr(row)
                    p = a.get("price")
                    if isinstance(p, str): p = p.replace(",", ".")
                    try: p = float(p)
                    except (TypeError, ValueError): continue
                    if p > 0: vals.append(p)
                    if not exemplo:
                        print(f"   exemplo de variante: {a.get('variant')} price={a.get('price')} {a.get('currency')} ({a.get('priced_at')})")
                        exemplo = True
                if vals:
                    menor = round(min(vals), 2)
                    for k in item["keys"]: cards_out[k] = menor
                cursor["pend"].pop(0)
                if req_count % 20 == 0:
                    prices_tmp = dict(prices); prices_tmp["cards"] = cards_out; prices_tmp["imgs"] = imgs_out
                    save("prices.json", prices_tmp); save("price_cursor.json", cursor)
    except Budget as e:
        print(f"Pausa: {e}. Progresso salvo; a próxima execução continua de onde parou.")

    # ---------- D) cotação EUR->BRL ----------
    rate = prices.get("eur_brl"); rate_date = prices.get("rate_date")
    try:
        fx = get_fx()
        if fx: rate, rate_date = fx
    except Exception as e:
        print(f"aviso: cotação indisponível ({e}); mantendo a anterior.")

    prices = {"source": "TCG Codex (Cardmarket)",
              "updated": datetime.date.today().isoformat(),
              "currency": "EUR", "eur_brl": rate, "rate_date": rate_date,
              "cards": cards_out, "imgs": imgs_out}
    save("prices.json", prices)
    save("price_cursor.json", cursor)
    fila = len(cursor.get("pend", []))
    print(f"prices.json: {len(cards_out)} preços | fila restante: {fila} | req: {req_count} | €1 = R$ {rate}")
    if cursor["stage"] == "C" and not fila:
        save("price_cursor.json", {"stage": "A", "codex_sets": [], "pend": [], "done_sets": []})
        print("Ciclo completo — a próxima rodada renova tudo (sets novos incluídos).")

def get_fx():
    url = "https://api.frankfurter.app/latest?from=EUR&to=BRL"
    req = urllib.request.Request(url, headers={"User-Agent": "irdex/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        j = json.loads(r.read().decode("utf-8"))
    v = (j.get("rates") or {}).get("BRL")
    return (round(float(v), 4), j.get("date")) if v else None

if __name__ == "__main__":
    main()
