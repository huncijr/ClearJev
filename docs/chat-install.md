# ClearJev telepítése chaten keresztül (Codex CLI chatbot)

> Nem kell terminálos `curl`. Nyisd meg a Codex CLI-t (`codex` parancs a
> terminálban), és illeszd be az alábbi promptot egyben. Az AI végigviszi a
> telepítést — neked csak jóváhagyásokat kell adnod, a végén pedig trustolnod
> a hookot és új sessiont nyitnod (ezt csak te tudod megcsinálni).
>
> Előfeltétel: Codex CLI + `python3` a gépen. Jev API key jó ha van
> (https://console.typesafe.ai/keys), de anélkül is felmegy (heurisztikus
> fallback módban).

## Másolható prompt

```text
Telepítsd a ClearJev skillt és hookot a gépemre:

1. Klónozd a https://github.com/huncijr/ClearJev repót egy temp mappába
   (elég shallow clone: git clone --depth 1).
2. Futtasd a plugins/clearjev-router/scripts/install.sh -t a klónból.
   Ez bemásolja a skillt a ~/.codex/skills + ~/.agents/skills mappákba,
   bejegyzi a UserPromptSubmit hookot a ~/.codex/hooks.json-be (merge, a
   meglévő hookjaim megtartásával), engedélyezi a skills+hooks feature-öket
   a ~/.codex/config.toml-ban, és felteszi a `clearjev` parancsot a
   ~/.local/bin-be. A ~/.local/bin-en kívül máshova rendszer-szinten ne írj.
3. Ha a script TYPESAFE_API_KEY-t kér, hagyd üresen (Enter) — a keyt én adom
   meg később kézzel.
4. A végén futtasd le:
   python3 ~/.codex/skills/clearjev-router/scripts/jev_route.py --check
   és mutasd meg a teljes kimenetet.
5. Mondd el, mi a következő két kézi lépésem (Codex újraindítás + hook
   trust /hooks-ban + új session), de azokat ne próbáld megcsinálni helyettem.

Ha valamelyik lépéshez engedély kell (shell, hálózat), kérj jóváhagyást,
ne kerüld meg. Ha az install.sh nem futtatható ezen a rendszeren, szólj, és
a lépéseit kézzel, egyenként hajtsd végre ugyanazzal a hatással.
```

## Kézi lépések a prompt után (neked)

1. **API key** (ha kihagytad):
   ```bash
   export TYPESAFE_API_KEY="a_te_keyed"
   ```
2. **Ellenőrzés**: `clearjev status` (ha `command not found`:
   `export PATH="$HOME/.local/bin:$PATH"`), majd `clearjev check`.
3. **Codex újraindítás** (CLI: kilépés + `codex` újra; App: új chat nem elég,
   az Appot is érdemes újraindítani az első telepítéskor).
4. **Hook trust**: CLI-ben `/hooks` → `ClearJev routing` / `jev_route.py`
   (`UserPromptSubmit`) → jóváhagyás. Trust nélkül a Codex csendben kihagyja
   a hookot.
5. **Új session** nyitása, majd próbaprompt:
   `Implement Stripe subscriptions with monthly/yearly plans, webhooks and access control.`
   Elvárt: `ClearJev routing` státusz + routing blokk (`Model: gpt-6-sol · ...`).

## Vezérlés chaten belül (telepítés után)

- Automatikus: semmit nem kell írni, minden prompt előtt routol.
- `$clearjev-router` — a skill explicit meghívása.
- `noroute: ...` — egy prompt routing nélkül.
- `reroute: ...` — rossz döntés korrekciója.
- Mondatban is kérheted az ügynököt: „Kapcsold ki a ClearJev routingot"
  (ilyenkor az ügynök a `clearjev off` parancsot futtatja shellben —
  shell-jog kell hozzá; ha megtagadja, terminálban: `clearjev off` / `on`).

## Ha nem működik (sorrendben ellenőrizd)

1. Megvan? `ls ~/.codex/skills/clearjev-router/SKILL.md`
2. `clearjev status` mit ír?
3. `/hooks`-ban trustolva van a hook? (Leggyakoribb ok.)
4. A próba új sessionben történt?
5. Nincs másik `clearjev-router` nevű skill?

## Eltávolítás (maradéktalanul visszafordítható)

```bash
clearjev off
rm -rf ~/.codex/skills/clearjev-router ~/.agents/skills/clearjev-router
rm -f ~/.local/bin/clearjev
```

majd vedd ki a `jev_route.py` bejegyzést a `~/.codex/hooks.json`
`UserPromptSubmit` listájából (vagy tiltsd le `/hooks`-ban).
