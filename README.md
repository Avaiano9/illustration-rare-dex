# Illustration Rare Dex

Rastreador pessoal de Pokémon com carta **Alt Art / Illustration Rare / Special
Illustration Rare**. Marca-se por **espécie** (basta ter uma carta de cada
Pokémon). O site se mantém atualizado sozinho conforme novos sets são lançados.

---

## O que é cada arquivo

```
index.html                      -> o site (abre no navegador)
data/tracker.json               -> a lista de Pokémon e cartas (atualizada pelo robô)
data/dexmap.json                -> nº da Pokédex -> nome e região
data/known_sets.json            -> sets já incorporados (controle interno)
scripts/build.py                -> incorpora sets novos (rodado pelo robô)
.github/workflows/update.yml    -> o robô semanal (GitHub Actions)
```

---

## Como publicar no GitHub Pages (gratuito, ~5 minutos)

1. Crie uma conta no GitHub (se ainda não tiver) e clique em **New repository**.
   - Dê um nome, ex.: `illustration-rare-dex`.
   - Deixe **Public** (Pages e Actions são gratuitos em repositórios públicos).
   - Crie o repositório.

2. Envie estes arquivos para o repositório, mantendo a mesma estrutura de pastas.
   - Pelo site: botão **Add file → Upload files**, arraste tudo e confirme.
   - (A pasta `.github` pode não aparecer ao arrastar; se faltar, crie o arquivo
     manualmente em **Add file → Create new file** com o caminho
     `.github/workflows/update.yml` e cole o conteúdo.)

3. Ative o Pages: **Settings → Pages**.
   - Em **Source**, escolha **Deploy from a branch**.
   - Branch: **main** e pasta **/ (root)**. Salve.
   - Em ~1 minuto o site fica no ar em:
     `https://SEU-USUARIO.github.io/illustration-rare-dex/`

4. Ative o robô: aba **Actions** → se pedir, clique em **I understand my
   workflows, enable them**. Pronto.
   - Ele roda sozinho toda segunda-feira.
   - Para rodar na hora: **Actions → Atualizar cartas → Run workflow**.

Feito. O site já funciona, e toda semana as cartas dos sets novos entram
automaticamente — inclusive aumentando o total de Pokémon colecionáveis.

---

## Como funciona a atualização

O `scripts/build.py` consulta o dataset comunitário
[`PokemonTCG/pokemon-tcg-data`](https://github.com/PokemonTCG/pokemon-tcg-data),
que recebe cada set novo pouco depois do lançamento. Ele pega as cartas
**Illustration Rare** e **Special Illustration Rare** dos sets ainda não
incorporados, agrupa por Pokémon (nº da Pokédex) e grava em `data/tracker.json`.
O robô semanal roda esse script e publica as mudanças. O site simplesmente
carrega o `tracker.json` — então, ao visitar, você sempre vê a versão mais nova.

O botão **Atualizar agora** no site faz a mesma busca na hora, caso não queira
esperar o robô semanal.

> Observação: as cartas **Illustration Rare / Special Illustration Rare** têm
> raridade própria e entram automaticamente. As "Alt Art" antigas (V/VMAX/VSTAR
> da era Sword & Shield) não têm marcação limpa de "arte alternativa" nos dados,
> então já vêm na base curada, mas não são detectadas automaticamente em sets
> futuros — o que não é problema, pois os sets novos usam IR/SIR.

---

## Seu progresso

Fica salvo **neste navegador/dispositivo** (armazenamento local — sem custo, sem
servidor). Para levar a outro aparelho, use **Exportar** e depois **Importar**.

Rodar localmente pelo disco (`file://`) pode não carregar os dados por segurança
do navegador; por isso a recomendação é publicar no Pages (ou usar um servidor
local, ex.: `python -m http.server` na pasta do projeto).
