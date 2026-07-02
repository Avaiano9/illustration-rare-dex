#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Atualiza data/tracker.json com as cartas Illustration Rare / Special Illustration
Rare dos sets recém-lancados, a partir do dataset comunitario do Pokemon TCG.

Roda automaticamente pelo GitHub Action (semanalmente), mas tambem pode ser
executado localmente:  python scripts/build.py

Nao depende de bibliotecas externas (apenas Python 3 padrao).
"""

import json, os, re, urllib.request

ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA   = os.path.join(ROOT, "data")
RAW    = "https://raw.githubusercontent.com/PokemonTCG/pokemon-tcg-data/master/"
KEEP   = {"Illustration Rare", "Special Illustration Rare"}
CUTOFF = "2023/01/01"   # IR/SIR so existem a partir da era Scarlet & Violet

def load(name, default):
    p = os.path.join(DATA, name)
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default

def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "irdex-bot"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))

def dedup(c):
    return (str(c.get("set","")).lower().replace(" ","") + "|" +
            re.sub(r"[^A-Z0-9]", "", str(c.get("num","")).upper()))

def main():
    tracker = load("tracker.json", [])
    dexmap  = load("dexmap.json", {})
    known   = set(load("known_sets.json", []))

    by_dex = {s["dexn"]: s for s in tracker}

    sets = get_json(RAW + "sets/en.json")
    new_sets = [s for s in sets
                if s["id"] not in known and (s.get("releaseDate","") >= CUTOFF)]
    new_sets.sort(key=lambda s: s.get("releaseDate",""))

    if not new_sets:
        print("Nada novo. tracker.json ja esta em dia.")
        return

    added_cards = 0
    added_species = 0
    processed = []

    for st in new_sets:
        sid, sname = st["id"], st["name"]
        try:
            cards = get_json(RAW + f"cards/en/{sid}.json")
        except Exception as e:
            print(f"  aviso: falha ao ler {sid} ({e}); tentara na proxima vez")
            continue  # nao marca como conhecido -> retenta semana que vem

        for c in cards:
            if c.get("supertype") != "Pokémon":
                continue
            if c.get("rarity") not in KEEP:
                continue
            dexs = c.get("nationalPokedexNumbers") or []
            if not dexs:
                continue
            card = {
                "name": c["name"],
                "set": sname,
                "num": str(c.get("number","")),
                "img": f"https://images.pokemontcg.io/{sid}/{c.get('number','')}.png",
                "rarity": c["rarity"],
            }
            counted = False
            for dexn in dexs:
                name, region = dexmap.get(str(dexn), [c["name"], "—"])
                sp = by_dex.get(dexn)
                if sp is None:
                    sp = {"species": name, "dex": f"#{int(dexn):04d}",
                          "region": region, "dexn": int(dexn), "cards": []}
                    by_dex[dexn] = sp
                    added_species += 1
                if not any(dedup(x) == dedup(card) for x in sp["cards"]):
                    sp["cards"].append(dict(card))
                    counted = True
            if counted:
                added_cards += 1

        known.add(sid)
        processed.append(sname)

    tracker = [by_dex[k] for k in sorted(by_dex)]

    json.dump(tracker, open(os.path.join(DATA, "tracker.json"), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    json.dump(sorted(known), open(os.path.join(DATA, "known_sets.json"), "w"),
              separators=(",", ":"))

    print(f"Sets incorporados: {len(processed)} -> {', '.join(processed)}")
    print(f"Cartas novas: {added_cards} | Pokemon novos: {added_species}")
    print(f"Total de Pokemon agora: {len(tracker)}")

if __name__ == "__main__":
    main()
