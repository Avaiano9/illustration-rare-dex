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

MAX_REQUESTS = int(os.environ.get("PRICES_MAX_REQUESTS", "520"))
SLEEP = 0.15
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
    """(código, nº frouxo) -> {(nosso set, nosso nº)} — base + extras + biblioteca."""
    tracker = load("tracker.json", []); extras = load("extras.json", [])
    library = load("library.json", {})
    limmap = load("limmap.json", {})
    w = {}
    def note(sn, num):
        code = limmap.get(sn)
        if code: w.setdefault((code, loosenum(num)), set()).add((sn, str(num)))
    for s in tracker:
        for c in s["cards"]: note(c.get("set"), c.get("num"))
    for e in extras: note(e.get("set"), e.get("num"))
    for v in library.values():
        for c in v: note(c.get("set"), c.get("num"))
    return w, limmap

# =====================================================================
# PARTE 1 — preços do TCGcsv
# =====================================================================
def precos_tcgcsv(wanted, limmap, cards_out):
    codes = {c for c, _ in wanted}
    nomes = {setkey(n): limmap[n] for n in limmap}
    # apelidos: código nosso -> trecho que aparece no nome do grupo do TCGplayer
    ALIAS_TOKENS = {
        "SVP": "svblackstarpromo", "SP": "swshblackstarpromo",
        "SMP": "smblackstarpromo", "XYP": "xyblackstarpromo",
        "BWP": "bwblackstarpromo", "HSP": "hgssblackstarpromo",
        "DPP": "dpblackstarpromo", "NP": "nintendoblackstarpromo",
        "WP": "wizardsblackstarpromo", "MEP": "meblackstarpromo",
        "CEL": "celebrations",
    }
    ALT_TOKENS = {  # variações comuns dos nomes de grupos de promo
        "SVP": ["scarletvioletpromo"], "SP": ["swordshieldpromo"],
        "SMP": ["sunmoonpromo"], "XYP": ["xypromo"], "BWP": ["blackwhitepromo"],
        "HSP": ["heartgoldsoulsilverpromo"], "DPP": ["diamondpearlpromo"],
        "MEP": ["megaevolutionpromo", "megapromo"],
    }
    print("PREÇOS (TCGcsv/TCGplayer)…")
    grupos = (http_json(f"{TCGCSV}/groups") or {}).get("results") or []
    print(f"  grupos de Pokémon no TCGplayer: {len(grupos)}")
    casados = []; usados = set()
    for g in grupos:
        ab = str(g.get("abbreviation") or "").upper()
        nk = setkey(g.get("name") or "")
        code = ab if ab in codes else nomes.get(nk)
        if not code:
            for cd, tok in ALIAS_TOKENS.items():
                if cd in codes and tok in nk: code = cd; break
        if not code:
            for cd, toks in ALT_TOKENS.items():
                if cd in codes and any(x in nk for x in toks): code = cd; break
        if not code:
            # último recurso: nome do nosso set contido no nome do grupo
            for onk, cd in nomes.items():
                if cd in codes and len(onk) > 8 and onk in nk: code = cd; break
        if code and code in codes:
            casados.append((g.get("groupId"), code, g.get("name")))
            usados.add(code)
    print(f"  sets casados: {len(casados)}")
    faltando = sorted(codes - usados)
    if faltando: print(f"  códigos SEM grupo no TCGplayer: {faltando}")
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
# PARTE 1b — preços japoneses (TCGplayer categoria Japão, via TCGcsv)
# =====================================================================
# Linhagem: qual(is) set(s) japonês(es) deram origem a cada set inglês da era
# IR/SIR. Tokens normalizados procurados no NOME do grupo japonês do TCGplayer.
# O nome do próprio set inglês também é sempre tentado (cobre nomes idênticos,
# como Black Bolt / White Flare e a era Mega Evolution).
LINEAGE = {
 "Scarlet & Violet": ["scarletex", "violetex"],
 "Paldea Evolved": ["tripletbeat", "snowhazard", "clayburst"],
 "Obsidian Flames": ["ruleroftheblackflame"],
 "151": ["pokemoncard151", "151"],
 "Paradox Rift": ["ancientroar", "futureflash"],
 "Paldean Fates": ["shinytreasure"],
 "Temporal Forces": ["wildforce", "cyberjudge"],
 "Twilight Masquerade": ["crimsonhaze", "maskofchange"],
 "Shrouded Fable": ["nightwanderer"],
 "Stellar Crown": ["stellarmiracle"],
 "Surging Sparks": ["superelectricbreaker"],
 "Prismatic Evolutions": ["terastalfest"],
 "Journey Together": ["battlepartners"],
 "Destined Rivals": ["gloryofteamrocket", "heatwavearena"],
}
def precos_japones(jp_out, jpx_out, tracker):
    """Menor preço japonês por Pokémon (jp_out) e, quando a linhagem do set é
    conhecida, o preço da MESMA ARTE por carta inglesa (jpx_out)."""
    dexmap = load("dexmap.json", {})
    name2dex = {v[0].lower(): int(k) for k, v in dexmap.items()}
    def guess(nm):
        n = str(nm or "").split(" - ")[0].strip().lower()
        n = re.sub(r"\(.*?\)", "", n).strip()
        n = re.sub(r"^(mega|team rocket's|ethan's|misty's|steven's|marnie's|cynthia's|"
                   r"arven's|iono's|lillie's|hop's|n's)\s+", "", n)
        n = re.sub(r"\s+(ex|gx|v|vmax|vstar)$", "", n)
        return name2dex.get(n.strip())
    print("PREÇOS JAPONESES (TCGcsv)…")
    cats = (http_json("https://tcgcsv.com/tcgplayer/categories") or {}).get("results") or []
    cat = None
    for c in cats:
        nm = str(c.get("name") or "").lower()
        if "japan" in nm and "pokemon" in nm.replace("é", "e"): cat = c; break
    if not cat:
        print("  categoria japonesa não encontrada — etapa pulada."); return
    cid = cat.get("categoryId")
    grupos = (http_json(f"https://tcgcsv.com/tcgplayer/{cid}/groups") or {}).get("results") or []
    grupos = [g for g in grupos if str(g.get("publishedOn") or "") >= "2022-10"]
    print(f"  sets japoneses desde a era AR/SAR: {len(grupos)}")
    RAR_OK = {"artrare": "ar", "specialartrare": "sar", "ar": "ar", "sar": "sar"}
    achados = 0
    gdata = {}   # nome normalizado do grupo -> {(dexn, camada): menor preço}
    for g in grupos:
        gid = g.get("groupId"); gnk = setkey(g.get("name") or "")
        prods = (http_json(f"https://tcgcsv.com/tcgplayer/{cid}/{gid}/products") or {}).get("results") or []
        precos = (http_json(f"https://tcgcsv.com/tcgplayer/{cid}/{gid}/prices") or {}).get("results") or []
        por = {}
        for p in precos:
            v = p.get("marketPrice") or p.get("midPrice") or p.get("lowPrice")
            try: v = float(v)
            except (TypeError, ValueError): continue
            if v > 0: por[p.get("productId")] = min(v, por.get(p.get("productId"), v))
        tabela = gdata.setdefault(gnk, {})
        for pr in prods:
            rar = ""
            for ed in (pr.get("extendedData") or []):
                if str(ed.get("name", "")).lower() == "rarity":
                    rar = re.sub(r"[^a-z]", "", str(ed.get("value", "")).lower())
            camada = RAR_OK.get(rar)
            if not camada: continue
            v = por.get(pr.get("productId"))
            if v is None: continue
            base = str(pr.get("name") or "")
            for parte in base.split("&"):
                d = guess(parte)
                if d is None: continue
                jp_out[str(d)] = min(round(v, 2), jp_out.get(str(d), 10**9))
                ch = (d, camada)
                tabela[ch] = min(round(v, 2), tabela.get(ch, 10**9))
                achados += 1
    print(f"  espécies com preço japonês: {len(jp_out)} ({achados} cartas AR/SAR casadas)")

    # ----- casamento arte-a-arte pela linhagem -----
    TIER = {"Illustration Rare": "ar", "Special Illustration Rare": "sar"}
    sem_fonte = set(); casadas = 0
    for sp in tracker:
        for c in sp["cards"]:
            camada = TIER.get(c.get("rarity"))
            if not camada: continue
            en = c.get("set") or ""
            tokens = list(LINEAGE.get(en, [])) + [setkey(en)]
            fontes = [tab for gnk, tab in gdata.items()
                      if any(tok and tok in gnk for tok in tokens)]
            if not fontes:
                sem_fonte.add(en); continue
            vals = [tab[(sp["dexn"], camada)] for tab in fontes if (sp["dexn"], camada) in tab]
            if not vals: continue
            jpx_out[f"{setkey(en)}|{numkey(c.get('num'))}"] = min(vals)
            casadas += 1
    print(f"  mesma arte (linhagem): {casadas} cartas casadas")
    if sem_fonte:
        print(f"  sets EN sem fonte japonesa casada: {sorted(sem_fonte)}")
        print(f"  (nomes dos grupos JP para calibrar: {sorted(gdata.keys())[:40]}…)")

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

    jp_out = prices.get("jp", {}); jpx_out = prices.get("jpx", {})
    tracker = load("tracker.json", [])
    try:
        precos_tcgcsv(wanted, limmap, cards_out)
        precos_japones(jp_out, jpx_out, tracker)
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
                         "cards": cards_out, "imgs": imgs_out, "jp": jp_out, "jpx": jpx_out})
    print(f"prices.json: {len(cards_out)} preços | {len(jp_out)} espécies JP | {len(jpx_out)} mesma-arte | {len(imgs_out)} imagens | req: {req_count} | US$ 1 = R$ {rate}")

if __name__ == "__main__":
    main()
