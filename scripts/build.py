#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Robô semanal do Illustration Rare Dex. Faz quatro coisas, nesta ordem:

 1. BASE (data/tracker.json): adiciona as Illustration Rare / Special
    Illustration Rare dos sets recém-lançados (dataset PokemonTCG/pokemon-tcg-data).
 2. BIBLIOTECA (data/library.json): adiciona as demais cartas "quebra-moldura"
    dos sets novos (Full Art ex, douradas, raridades especiais) para escolha manual.
 3. PROMOS (data/library.json): adiciona Pokémon das linhas "Black Star Promos"
    de todas as eras a partir do TCGdex (que cobre MEP/SVP), com imagens do TCGdex.
 4. IMAGENS/TOTAIS (data/imgmap.json, data/set_totals.json): atualiza o mapa de
    imagens reserva e os totais impressos dos sets.

Roda no GitHub Actions, mas também localmente: python scripts/build.py
Só usa a biblioteca padrão do Python 3.
"""

import json, os, re, io, tarfile, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
RAW  = "https://raw.githubusercontent.com/PokemonTCG/pokemon-tcg-data/master/"
TCGDEX_TAR = "https://codeload.github.com/tcgdex/cards-database/tar.gz/refs/heads/master"

CUTOFF = "2023/01/01"
KEEP_TRACKER = {"Illustration Rare", "Special Illustration Rare"}
# quebra-moldura para a biblioteca (sets novos são todos de era moderna)
KEEP_LIBRARY = {"Ultra Rare", "Hyper Rare", "Shiny Ultra Rare", "Black White Rare",
                "Mega Hyper Rare", "MEGA_ATTACK_RARE", "Rare Ultra", "Rare Rainbow",
                "Rare Secret", "Rare Shiny GX", "Trainer Gallery Rare Holo",
                "Amazing Rare", "LEGEND", "Rare Holo Star", "Classic Collection"}
def keep_library_extra(c):
    nm = c.get("name",""); r = c.get("rarity")
    if r == "Rare Holo VMAX": return True                 # VMAX básicas (arte sem moldura)
    if r == "Rare Holo GX" and " & " in nm: return True   # TAG TEAM básicas
    if r == "Rare Holo V" and str(c.get("number","")).upper().startswith("SV"): return True
    return False

IMG_ALIAS = {  # nosso nome de set -> nome no TCGdex (quando difere)
 "Scarlet & Violet Black Star Promos": "SVP Black Star Promos",
 "Astral Radiance Trainer Gallery": "Astral Radiance",
 "Brilliant Stars Trainer Gallery": "Brilliant Stars",
 "Lost Origin Trainer Gallery": "Lost Origin",
 "Silver Tempest Trainer Gallery": "Silver Tempest",
 "Crown Zenith Galarian Gallery": "Crown Zenith",
 "Shining Fates Shiny Vault": "Shining Fates",
 "Hidden Fates Shiny Vault": "Hidden Fates",
 "HS—Triumphant": "Triumphant", "HS—Undaunted": "Undaunted", "HS—Unleashed": "Unleashed",
 "HeartGold & SoulSilver": "HeartGold SoulSilver",
}

def load(name, default):
    try: return json.load(open(os.path.join(DATA, name), encoding="utf-8"))
    except Exception: return default

def save(name, obj, **kw):
    json.dump(obj, open(os.path.join(DATA, name), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"), **kw)

def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "irdex-bot"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode("utf-8"))

def dedup(c):
    return (str(c.get("set","")).lower().replace(" ","") + "|" +
            re.sub(r"[^A-Z0-9]", "", str(c.get("num","")).upper()))

# Lista oficial embutida do MEP Black Star Promos (numero, nome da carta).
# Rede de seguranca: se o Bulbapedia estiver fora do ar, o robo usa esta lista.
# Nao-Pokemon (Estadios) sao ignorados automaticamente (nao resolvem Pokedex).
MEP_FALLBACK = [
 (1,"Meganium"),(2,"Inteleon"),(3,"Alakazam"),(4,"Lunatone"),(5,"Drifloon"),(6,"Drifblim"),
 (7,"Psyduck"),(8,"Golduck"),(9,"Alakazam"),(10,"Riolu"),(11,"Mega Latias ex"),(12,"Mega Lucario ex"),
 (13,"Mega Venusaur ex"),(14,"Ceruledge"),(15,"Zacian"),(16,"Flygon"),(17,"Toxtricity"),(18,"Cottonee"),
 (19,"Whimsicott"),(20,"Sneasel"),(21,"Weavile"),(22,"Charcadet"),(23,"Mega Charizard X ex"),
 (24,"Oricorio ex"),(25,"Mega Kangaskhan ex"),(26,"Meloetta"),(27,"Haunter"),(28,"Celebratory Fanfare"),
 (29,"Mega Charizard X ex"),(30,"Mega Charizard Y ex"),(31,"N's Zekrom"),(32,"Mega Gardevoir ex"),
 (33,"Mega Lucario ex"),(34,"Mega Meganium ex"),(35,"Mega Emboar ex"),(36,"Mega Feraligatr ex"),
 (37,"Bulbasaur"),(38,"Charmander"),(39,"Squirtle"),(40,"Turtwig"),(41,"Chimchar"),(42,"Piplup"),
 (43,"Rowlet"),(44,"Litten"),(45,"Popplio"),(46,"Chikorita"),(47,"Cyndaquil"),(48,"Totodile"),
 (49,"Snivy"),(50,"Tepig"),(51,"Oshawott"),(52,"Grookey"),(53,"Scorbunny"),(54,"Sobble"),
 (55,"Treecko"),(56,"Torchic"),(57,"Mudkip"),(58,"Chespin"),(59,"Fennekin"),(60,"Froakie"),
 (61,"Sprigatito"),(62,"Fuecoco"),(63,"Quaxly"),(64,"Serperior"),(65,"Barbaracle"),(66,"Tyrantrum"),
 (67,"Doublade"),(68,"Makuhita"),(69,"Chikorita"),(70,"Tyrunt"),(71,"Mega Zygarde ex"),
 (72,"Mega Clefable ex"),(73,"Mega Gengar ex"),(74,"Delphox"),(75,"Ampharos"),(76,"Crobat"),
 (77,"Goodra"),(78,"Toxel"),(79,"Charmeleon"),(80,"Fennekin"),(81,"Mega Greninja ex"),(82,"Miraidon"),
 (83,"Slowbro"),(84,"Dhelmise"),(85,"Bastiodon"),(86,"Slowpoke"),(87,"Binacle"),(88,"Zarude"),
 (89,"Mega Zeraora ex"),(90,"Mega Darkrai ex"),(91,"Mega Dragonite ex"),(92,"Paradise Resort"),
 (93,"Pikachu"),(94,"Alolan Exeggutor"),(95,"Lucario"),(96,"Moltres"),(97,"Articuno"),(98,"Zapdos"),
 (99,"Greninja ex"),(100,"Sylveon ex"),(101,"Nidorina"),(102,"Victini"),(103,"Zeraora"),(104,"Mewtwo"),
 (105,"Mew"),(106,"Ditto"),(107,"Pikachu ex"),(108,"Espeon ex"),(109,"Pikachu ex"),(110,"Umbreon ex"),
]
MEP_WIKI = ("https://bulbapedia.bulbagarden.net/w/index.php"
            "?title=MEP_Black_Star_Promos_(TCG)&action=raw")

def fetch_mep_list():
    """Tenta ler a lista do Bulbapedia (auto-atualizavel). Se falhar ou vier
    pequena demais, usa a lista embutida. Sempre retorna [(num, nome), ...]."""
    try:
        req = urllib.request.Request(MEP_WIKI, headers={"User-Agent": "irdex-bot"})
        txt = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
        out = []
        for m in re.finditer(r"\{\{Setlist/entry\|(\d+)\|[^|]*\|\{\{TCG ID\|MEP Promo\|([^|}]+)", txt):
            out.append((int(m.group(1)), m.group(2).strip()))
        # so confia se cobrir pelo menos o que ja conhecemos
        if len(out) >= len(MEP_FALLBACK):
            print(f"  MEP: lista obtida do Bulbapedia ({len(out)} cartas)")
            return out
        print(f"  MEP: Bulbapedia veio curto ({len(out)}); usando lista embutida")
    except Exception as e:
        print(f"  MEP: Bulbapedia indisponivel ({e}); usando lista embutida")
    return list(MEP_FALLBACK)

def build_mep_promos(library, dexmap, have):
    name2dex = {v[0].lower(): int(k) for k, v in dexmap.items()}
    def mep_dex(nm):
        n = nm.lower()
        n = re.sub(r"^mega\s+", "", n)
        n = re.sub(r"^(alolan|galarian|hisuian|paldean)\s+", "", n)
        n = re.sub(r"^[a-z]+'s\s+", "", n)                # N's Zekrom -> zekrom
        n = re.sub(r"\s+(ex|gx|v|vmax|vstar)$", "", n)
        n = re.sub(r"\s+[xy]$", "", n)                    # Charizard X/Y
        return name2dex.get(n.strip())
    added = 0
    for num, nm in fetch_mep_list():
        dex = mep_dex(nm)
        if dex is None:  # nao-Pokemon (Estadios) ou nome desconhecido: pula
            continue
        n3 = str(num).zfill(3)
        card = {"name": nm, "set": "MEP Black Star Promos", "num": n3,
                "img": ("https://limitlesstcg.nyc3.cdn.digitaloceanspaces.com/"
                        f"tpci/MEP/MEP_{n3}_R_EN_SM.png"), "rarity": "Promo"}
        if dedup(card) in have:
            continue
        have.add(dedup(card)); added += 1
        library.setdefault(str(dex), []).append(dict(card))
    return added

def main():
    tracker  = load("tracker.json", [])
    library  = load("library.json", {})
    dexmap   = load("dexmap.json", {})
    known    = set(load("known_sets.json", []))       # sets já processados p/ BASE
    libknown = set(load("lib_known_sets.json", []))   # sets já processados p/ BIBLIOTECA
    totals   = load("set_totals.json", {})

    by_dex = {s["dexn"]: s for s in tracker}
    have = {dedup(c) for s in tracker for c in s["cards"]}
    have |= {dedup(c) for v in library.values() for c in v}

    name2dex = {v[0].lower(): int(k) for k, v in dexmap.items()}
    def guess_dex(nm):
        n = nm.lower()
        n = re.sub(r"^(mega|team rocket's|ethan's|misty's|steven's|marnie's|cynthia's|"
                   r"arven's|iono's|lillie's|hop's|n's)\s+", "", n)
        n = re.sub(r"\s+(ex|gx|v|vmax|vstar)$", "", n)
        return name2dex.get(n.strip())

    # ---------- 1 e 2) sets novos do dataset principal ----------
    sets = get_json(RAW + "sets/en.json")
    sinfo = {s["name"]: s for s in sets}
    new_tracker = [s for s in sets if s["id"] not in known and s.get("releaseDate","") >= CUTOFF]
    new_library = [s for s in sets if s["id"] not in libknown and s.get("releaseDate","") >= CUTOFF]
    todo = {s["id"]: s for s in new_tracker + new_library}
    add_ir = add_lib = new_sp = 0
    done_names = []

    for sid, st in sorted(todo.items(), key=lambda kv: kv[1].get("releaseDate","")):
        try:
            cards = get_json(RAW + f"cards/en/{sid}.json")
        except Exception as e:
            print(f"  aviso: falha ao ler {sid} ({e}); tentará na próxima vez")
            continue
        code = st.get("ptcgoCode") or ""
        def cardimg(c, num):
            # 1) imagem oficial do proprio dataset (scrydex) - cobre sets novos
            #    desde o lancamento. 2) Limitless por ptcgoCode. O site ainda tem
            #    a corrente de reserva (Limitless/TCGdex/scrydex) se a principal falhar.
            imgs = c.get("images") or {}
            u = imgs.get("large") or imgs.get("small")
            if u: return u
            if code and "-" not in code:
                n = num.zfill(3) if num.isdigit() else num
                return (f"https://limitlesstcg.nyc3.cdn.digitaloceanspaces.com/"
                        f"tpci/{code}/{code}_{n}_R_EN_SM.png")
            return f"https://images.scrydex.com/pokemon/{sid}-{num}/large"
        for c in cards:
            if c.get("supertype") != "Pokémon": continue
            dexs = c.get("nationalPokedexNumbers") or []
            if not dexs: continue
            card = {"name": c["name"], "set": st["name"], "num": str(c.get("number","")),
                    "img": cardimg(c, str(c.get("number",""))),
                    "rarity": c.get("rarity")}
            if dedup(card) in have: continue
            r = c.get("rarity")
            if r in KEEP_TRACKER and sid in {s["id"] for s in new_tracker}:
                have.add(dedup(card)); add_ir += 1
                for dexn in dexs:
                    info = dexmap.get(str(dexn), [c["name"], "—"])
                    sp = by_dex.get(dexn)
                    if sp is None:
                        sp = {"species": info[0], "dex": f"#{int(dexn):04d}",
                              "region": info[1], "dexn": int(dexn), "cards": []}
                        by_dex[dexn] = sp; new_sp += 1
                    sp["cards"].append(dict(card))
            elif (r in KEEP_LIBRARY or keep_library_extra(c)) and sid in {s["id"] for s in new_library}:
                have.add(dedup(card)); add_lib += 1
                for dexn in dexs:
                    library.setdefault(str(dexn), []).append(dict(card))
        if sid in {s["id"] for s in new_tracker}: known.add(sid)
        if sid in {s["id"] for s in new_library}: libknown.add(sid)
        if st.get("printedTotal"): totals.setdefault(st["name"], st["printedTotal"])
        done_names.append(st["name"])

    # ---------- 2.5) MEP Black Star Promos: lista curada (auto-suficiente) ----------
    # O TCGdex vinha incompleto para o MEP (faltavam varias cartas do meio e as
    # mais novas). Aqui o robo monta a colecao MEP a partir de uma lista oficial
    # embutida (fonte da verdade), e ainda tenta atualizar sozinho pelo Bulbapedia.
    add_mep = build_mep_promos(library, dexmap, have)

    # ---------- 3 e 4) TCGdex: promos + mapa de imagens ----------
    LIM_PROMO_CODES = {
        "MEP Black Star Promos": "MEP", "Scarlet & Violet Black Star Promos": "SVP",
        "SWSH Black Star Promos": "SP", "SM Black Star Promos": "SMP",
        "XY Black Star Promos": "XYP",
    }
    add_promo = 0
    tmap = {}
    try:
        req = urllib.request.Request(TCGDEX_TAR, headers={"User-Agent": "irdex-bot"})
        blob = urllib.request.urlopen(req, timeout=300).read()
        tf = tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz")
        members = {m.name: m for m in tf.getmembers() if m.name.endswith(".ts") and "/data/" in m.name}
        def read(m): return tf.extractfile(m).read().decode("utf-8", "replace")

        # ids de série e de set; detecta zero-padding pelos nomes de arquivo
        serie_ids = {}
        for name, m in members.items():
            parts = name.split("/data/")[1].split("/")
            if len(parts) == 1:  # arquivo de série
                mm = re.search(r'id:\s*"([^"]+)"', read(m))
                if mm: serie_ids[parts[0][:-3]] = mm.group(1)
        set_info = {}   # en name -> {"t": "serie/set", "p": pad, "dir": caminho}
        pads = {}
        for name in members:
            parts = name.split("/data/")[1].split("/")
            if len(parts) == 3 and re.fullmatch(r"0\d\d", parts[2][:-3] or ""):
                pads[parts[0] + "/" + parts[1]] = 1
        for name, m in members.items():
            parts = name.split("/data/")[1].split("/")
            if len(parts) == 2:  # arquivo de set
                serie = parts[0]
                if serie == "Pokémon TCG Pocket" or serie not in serie_ids: continue
                txt = read(m)
                mid = re.search(r'id:\s*"([^"]+)"', txt)
                men = re.search(r'en:\s*"([^"]+)"', txt)
                if mid and men:
                    key = serie + "/" + parts[1][:-3]
                    set_info[men.group(1)] = {"t": f"{serie_ids[serie]}/{mid.group(1)}",
                                              "p": pads.get(key, 0), "dir": key}

        # promos: qualquer set "Black Star Promos" com cartas Pokémon
        for en_name, info in set_info.items():
            if "Black Star Promos" not in en_name: continue
            our_name = {v: k for k, v in IMG_ALIAS.items()}.get(en_name, en_name)
            prefix = "cards-database-master/data/" + info["dir"] + "/"
            for name, m in members.items():
                if not name.startswith(prefix): continue
                txt = read(m)
                if 'category: "Pokemon"' not in txt: continue
                mn = re.search(r'name:\s*\{\s*[^}]*?en:\s*"([^"]+)"', txt, re.S)
                md = re.search(r'dexId:\s*\[([^\]]*)\]', txt)
                if not mn: continue
                dexs = [int(x) for x in re.findall(r"\d+", md.group(1))] if md else []
                if not dexs:
                    g = guess_dex(mn.group(1))
                    if g: dexs = [g]
                if not dexs: continue
                local = name.split("/")[-1][:-3]
                limcode = LIM_PROMO_CODES.get(our_name)
                if limcode:
                    ln = local.zfill(3) if local.isdigit() else local
                    img = (f"https://limitlesstcg.nyc3.cdn.digitaloceanspaces.com/"
                           f"tpci/{limcode}/{limcode}_{ln}_R_EN_SM.png")
                else:
                    img = f"https://assets.tcgdex.net/en/{info['t']}/{local}/high.webp"
                card = {"name": mn.group(1), "set": our_name, "num": local,
                        "img": img, "rarity": "Promo"}
                if dedup(card) in have: continue
                nm = re.sub(r"\D", "", local)
                if nm and any(re.sub(r"\D","",c["num"]).lstrip("0") == nm.lstrip("0")
                              for d in dexs for c in library.get(str(d), []) if c["set"] == our_name):
                    continue
                have.add(dedup(card)); add_promo += 1
                for d in dexs: library.setdefault(str(d), []).append(dict(card))

        # mapa de imagens reserva para todos os sets usados
        used = {c["set"] for s in by_dex.values() for c in s["cards"]}
        used |= {c["set"] for v in library.values() for c in v}
        imgmap = {}
        for n in sorted(x for x in used if x):
            k = IMG_ALIAS.get(n, n)
            if k in set_info:
                imgmap[n] = {"t": set_info[k]["t"], "p": set_info[k]["p"]}
        save("imgmap.json", imgmap, sort_keys=True)
        tmap = set_info
    except Exception as e:
        print(f"  aviso: TCGdex indisponível nesta rodada ({e}); promos/imagens ficam para a próxima")

    # ---------- 5) mapa Limitless (3ª fonte de imagens), via ptcgoCode ----------
    LIM_OVERRIDES = {
        "XY Black Star Promos": "XYP", "SM Black Star Promos": "SMP",
        "SWSH Black Star Promos": "SP", "Scarlet & Violet Black Star Promos": "SVP",
        "BW Black Star Promos": "BWP", "HGSS Black Star Promos": "HSP",
        "DP Black Star Promos": "DPP", "Nintendo Black Star Promos": "NP",
        "Wizards Black Star Promos": "WP", "MEP Black Star Promos": "MEP",
        "Brilliant Stars Trainer Gallery": "BRS", "Astral Radiance Trainer Gallery": "ASR",
        "Lost Origin Trainer Gallery": "LOR", "Silver Tempest Trainer Gallery": "SIT",
        "Crown Zenith Galarian Gallery": "CRZ", "Shining Fates Shiny Vault": "SHF",
        "Hidden Fates Shiny Vault": "HIF", "Celebrations: Classic Collection": "CEL",
    }
    codes = {s["name"]: s.get("ptcgoCode") for s in sets}
    used = {c["set"] for s in by_dex.values() for c in s["cards"]}
    used |= {c["set"] for v in library.values() for c in v}
    limmap = {}
    for n in sorted(x for x in used if x):
        cc = LIM_OVERRIDES.get(n) or codes.get(n)
        if cc and "-" not in cc:
            limmap[n] = cc
    save("limmap.json", limmap, sort_keys=True)

    # ---------- 6) mapa scrydex (fonte oficial de imagens), nome do set -> id ----------
    SCRY_OVERRIDES = {"MEP Black Star Promos": "mep"}
    sid_by_name = {s["name"]: s["id"] for s in sets}
    scrymap = {}
    for n in sorted(x for x in used if x):
        sc = SCRY_OVERRIDES.get(n) or sid_by_name.get(n)
        if sc:
            scrymap[n] = sc
    save("scrymap.json", scrymap, sort_keys=True)

    # ---------- salvar ----------
    tracker = [by_dex[k] for k in sorted(by_dex)]
    rel = lambda c: (sinfo.get(c["set"], {}).get("releaseDate", "9999/99/99"), c["set"], c["num"])
    for k in library: library[k].sort(key=rel)
    save("tracker.json", tracker)
    save("library.json", library)
    save("known_sets.json", sorted(known))
    save("lib_known_sets.json", sorted(libknown))
    save("set_totals.json", totals, sort_keys=True)

    if done_names: print("Sets novos processados:", ", ".join(done_names))
    print(f"BASE: +{add_ir} IR/SIR (+{new_sp} Pokémon) -> {len(tracker)} espécies")
    print(f"MEP (lista curada): +{add_mep} cartas")
    print(f"BIBLIOTECA: +{add_lib} quebra-moldura, +{add_promo} promos -> "
          f"{sum(len(v) for v in library.values())} entradas")

if __name__ == "__main__":
    main()
