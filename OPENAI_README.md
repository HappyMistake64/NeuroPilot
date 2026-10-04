# NeuroPilot 3.4.0 — OpenAI přes předplatné ChatGPT

RSI nyní podporuje přímé přihlášení **Continue with ChatGPT**. Nepotřebuje API klíč ani Codex CLI. Používá oficiální OAuth pro využití předplatného v lokální aplikaci a veřejné rozhraní Responses. Dostupnost modelů, oprávnění, předplatné a případné kredity spravuje OpenAI. Nejde o neomezený nebo zaručeně bezplatný přístup.

## Připojení na Fedoře / Ubuntu

Ve složce rozbaleného projektu:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m rsi init
python server.py
```

1. Otevři `http://127.0.0.1:5000/rsi`.
2. V části **OpenAI přes předplatné ChatGPT** zvol **Continue with ChatGPT**, potom odkaz **Dokončit přihlášení v ChatGPT**.
3. Přihlas se na stránce OpenAI a povol NeuroPilotu využití předplatného. Prohlížeč musí běžet na stejném počítači jako NeuroPilot: přihlášení se vrací na místní adresu `127.0.0.1`.
4. Po dokončení se vrať do NeuroPilotu. Klikni na **Načíst dostupné modely**, vyber model a **Použít pro RSI**.
5. **Otestovat spojení · 1 dotaz** provede skutečný dotaz a uloží jeho výsledek mezi běhy. Úspěch označuje pouze `model_inference_verified: true` v dokončeném testu.
6. **Ověřit prostředí** zkontroluje také izolaci. Pro experimenty připrav Podman, Docker nebo Bubblewrap podle `RSI_README.md`.

Samotné přihlášení nebo načtení katalogu ještě nepotvrzuje, že účet může provést dotaz. Pokud oprávnění nebo limit účtu nestačí, zobrazí se chyba; program se nepřepne na placené API ani na jiný model.

Přihlašovací pokus platí deset minut. Zrušíš ho tlačítkem **Zrušit čekající přihlášení**. Uložený účet vybereš v seznamu; opětovné přihlášení používá jeho existující registraci. **Nový účet / workspace** slouží pro další registraci. **Odhlásit aktivní účet** odstraní místní tokeny a pokusí se odvolat vzdálenou relaci. Pokud se odvolání nepodaří potvrdit, UI to oznámí; přístup lze zrušit v nastavení ChatGPT.

## Terminál

```bash
python -m rsi openai-login
python -m rsi openai-status
python -m rsi openai-models
```

Z výpisu modelů vyber skutečné `id`, například jej vlož místo zástupného textu níže:

```bash
python -m rsi config --set provider=chatgpt --set openai_model=ID_Z_VYPISU
python -m rsi provider-check
python -m rsi doctor
python -m rsi baseline --limit 10
```

`openai-login --account oaiapp_…` obnoví přihlášení existující registrace z `openai-status`. Volba `--no-browser` pouze vypíše přihlašovací adresu. Není to vzdálený device-code režim: zpětná adresa stále vede na počítač s NeuroPilotem.

Odhlášení: `python -m rsi openai-logout`. Návrat k Ollamě: `python -m rsi config --set provider=ollama`. Předchozí nastavení lokálního modelu se zachovává.

## Co je propojené

- RSI baseline, návrhy změn, kampaně a obě větve A/B experimentu používají zvolený provider.
- Model vrací JSON. Soubory upravuje a testy spouští stávající broker NeuroPilotu. OpenAI nedostává shell, přístup k disku, cookies prohlížeče ani očekávané odpovědi skrytých testů.
- Výstupy modelu jsou data; žádný vzdálený požadavek na nástroj se zde automaticky nevykonává.
- Plánovač na `/` a samostatná Gradio aplikace mají původní rozhraní. Toto připojení ovládá laboratoř `/rsi`.

## Limity a reprodukovatelnost

Tento oficiální režim je preview. Vyžaduje streamování a `store: false`. Nepodporuje `max_output_tokens`, teplotu ani deterministický seed. NeuroPilot tyto parametry neposílá; semena experimentů jsou evidována jako neaplikovaná.

`context_tokens + output_tokens` u ChatGPT určuje pouze rezervaci před dotazem. Po dokončení se započítají skutečné vstupní a výstupní tokeny. Jeden dotaz může rezervaci i celkový limit překročit; po zjištění přečerpání se běh zastaví. Při výpadku bez údajů o spotřebě zůstává účtovaná rezervace a spotřeba je označena jako neznámá. Nemusí odpovídat skutečné vzdálené spotřebě. Vlastní finanční limity nastav v **ChatGPT Settings → Usage**.

Limity počtu dotazů a čekání dál platí. Zastavení ukončí místní transport, ale nezaručuje okamžité ukončení výpočtu ani účtování na serveru OpenAI. Název cloudového modelu není hash vah; report proto uvádí `weights_pinned: false`. Změnu účtu/modelu během jednoho experimentu odmítáme, změnu vah za stejným názvem nelze spolehlivě odhalit. Zohledni to při interpretaci RSI a A/B výsledků.

## Přihlašovací údaje a data

Tokeny ukládá pouze serverová část mimo projekt do `~/.config/neuropilot/openai/accounts.json`; složka má oprávnění `0700`, soubor `0600`. Proměnná `NEUROPILOT_OPENAI_AUTH_DIR` dovoluje zvolit jinou chráněnou cestu. Nedávej ji do adresáře projektu, experimentů, sdílených složek ani záloh pro podporu. Tento backend používá unixové zamykání; dodávka RSI je pro Linux.

Tokeny se neposílají do JavaScriptu, SQLite auditu nebo exportů. Obnova rotujících tokenů je zamčená mezi procesy. Přihlášení kontroluje podpis ID tokenu, issuer, audience, expiraci, nonce, jednorázový state a PKCE. Host ID a registrace se zachovávají po odhlášení. Heslo zadáváš pouze na stránce OpenAI.

Zadání a kód v kontextu se posílají OpenAI. Lokální audit stále obsahuje zadání a odpovědi, jak uvádí `RSI_README.md`.

## Ověření dodávky

Automatické testy používají podepsané testovací ID tokeny, místní callback a simulované odpovědi transportu. Ověřují protokol a chování aplikace, **ne přístup tvého účtu ani kvalitu modelu**. Zkušební běh bez přihlášení skončil `blocked` s nulou modelových volání. Skutečné OAuth přihlášení a inference čekají na dokončení na cílovém počítači. Žádný skutečný přínos RSI se tímto vydáním netvrdí.

## Oficiální dokumentace použitá při implementaci

- Registrace a přihlášení: https://developers.openai.com/siwc/token-sharing-open-source/sign-in
- Účty a relace: https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions
- Modely a inference: https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference
- Omezení preview: https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations
- Ověřování ID tokenu: https://developers.openai.com/siwc/website

Dokumentace ověřena během této implementace. Při budoucích změnách protokolu integraci znovu ověř; nepoužívej náhradní neoficiální endpointy.

## Cloudový Codex a vzdálená VM

Ověřeno proti oficiální dokumentaci 4. 10. 2026:
[Self-hosted VMs](https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms).
Pro tuto přímou OSS integraci je dokumentovaný postup **lokální OAuth ve stejném
NeuroPilotu → bezpečný přenos registrace → import na VM**. `--no-browser` nemění
loopback callback na vzdálené přihlášení. Přihlášení Codex CLI, jeho device-code
režim ani jeho soubor `auth.json` nejsou registrací NeuroPilotu a neimportují se.

1. Na VM spusť `python -m rsi openai-status`. Tím vznikne a uloží se vlastní host ID
   VM, zatím bez přihlášení. Úspěch tohoto příkazu není důkaz inference.
2. Na svém počítači dokonči `python -m rsi openai-login` a zjisti ID registrace
   pomocí `python -m rsi openai-status`. Použij stejný účet a workspace, který má
   používat VM. Import vyžaduje dosud platný podepsaný ID token; pokud vypršel,
   nejdřív lokální přihlášení obnov.
3. Přenes chráněný `~/.config/neuropilot/openai/accounts.json` přes dostupný
   zabezpečený kanál (například SSH/SCP) mimo repozitář, RSI state, sdílené složky
   a zálohy. Soubor na VM musí vlastnit aktuální uživatel a mít práva `0600`.
   Neposílej jeho obsah do chatu, GitHubu ani argumentů příkazové řádky.
4. Na VM importuj **jednu explicitně vybranou registraci**. Nahraď cestu a ID:

   ```bash
   python -m rsi openai-import --file /chranena/cesta/accounts.json --account oaiapp_ID
   python -m rsi openai-models
   python -m rsi config --set provider=chatgpt --set openai_model=ID_Z_VYPISU
   python -m rsi provider-check
   ```

Import zachová vlastní host ID VM a ostatní účty. Ověří podpis ID tokenu,
issuer, audience, expiraci, shodu subjectu a scope pro předplatné; neznámé položky
nekopíruje. Odmítne symlink, nechráněný soubor a zdroj nebo cíl uvnitř repozitáře
či zvoleného RSI state. Výstup neobsahuje tokeny a má `inference_verified: false`.
Teprve dokončený `provider-check` s `model_inference_verified: true` potvrzuje
skutečnou modelovou odpověď aplikace. Po importu odstraň přenosovou kopii bezpečným
postupem svého prostředí; další obnovování rotujících tokenů nech na VM a stejnou
relaci současně neobnovuj na notebooku. Import relaci nekopíruje do nového
nezávislého přihlášení; host-specific attribution a revocation přenesených relací
zatím podle dokumentace nejsou dostupné.

HTTP transport respektuje zděděné `HTTP_PROXY`/`HTTPS_PROXY`, `NO_PROXY` a CA trust
prostředí, včetně procesu inference. TLS ověřování zůstává zapnuté, přesměrování
se odmítají. Proxy musí být důvěryhodná a nastavená správcem prostředí.

Pro samostatný test s nejvýše jedním dotazem lze použít oddělený state:

```bash
python -m rsi --state /chranena/cesta/connection-check config \
  --set provider=chatgpt --set openai_model=ID_Z_VYPISU \
  --set max_calls=1 --set max_tokens=10240 --set max_seconds=120
python -m rsi --state /chranena/cesta/connection-check provider-check
```

Tokenový limit zůstává účetní, nikoli tvrdý limit serveru. Tento test nespouští
kandidátní kód. Baseline a kampaně nadále vyžadují úspěšné ověření sandboxu;
chybějící izolace se neobchází.

## Alternativa pro telefon: připojení přes Codex app-server

NeuroPilot má samostatné příkazy pro oficiální
[Codex app-server](https://developers.openai.com/codex/app-server). Tato cesta
používá přihlášení spravované Codexem a jeho podporovaný device-code flow.
Není to import Codex tokenů do přímého OpenAI provideru. Tokeny čte, ukládá a
obnovuje pouze Codex; NeuroPilot komunikuje přes lokální stdio JSON-RPC.

```bash
python -m rsi codex-status
python -m rsi codex-login
```

`codex-login` spustí oficiální `codex login --device-auth`, který vypíše odkaz na `https://auth.openai.com/codex/device` a krátký
jednorázový kód. Otevři odkaz na telefonu, zadej kód a dokonči přihlášení na
stránce OpenAI. Terminál musí zůstat otevřený do potvrzení serverem, nejvýše
10 minut. Device-code přihlášení může vyžadovat povolení v bezpečnostním nastavení
účtu nebo workspace. Heslo ani přístupové tokeny se nezadávají do NeuroPilotu.
Tento postup může obnovit přihlášení sdílené s místním Codex CLI.

Samotný `codex-status` neověřuje model. Účet může být uveden jako přihlášený,
i když je jeho token již odvolaný. K ověření použij:

```bash
python -m rsi --state /chranena/cesta/codex-check codex-check
# Nebo explicitně model z codex-status:
python -m rsi --state /chranena/cesta/codex-check codex-check --model ID_Z_VYPISU
```

NeuroPilot zadá jeden pevný dotaz s novou náhodnou hodnotou a požaduje její přesné
vrácení v JSON. Teprve dokončený tah se správnou odpovědí a bez porušení rozpočtu
má `model_inference_verified: true`. Výsledek a dostupné skutečné tokeny se uloží
do RSI registru jako `codex_connection_check`. Chybějící spotřeba zůstává neznámá,
ponechá se rezervace. Při chybě přihlášení spusť znovu `codex-login`.

Proces běží v prázdném dočasném adresáři, s vypnutými nástroji, pluginy, MCP
servery, hooks a přístupem k execution environments; sandbox je pouze pro čtení.
NeuroPilot nepředává projektu ani skryté testy a nepovoluje požadavky na nástroje.
Kontrola dodržuje lokální timeout a tokenový účetní rozpočet, nepoužívá fallback
na API klíč nebo jiného providera. Neukládej výpis jednorázového kódu do GitHubu.

**Samostatný `codex-check` není providerem pro RSI kampaně.** Jeden tah Codexu může
zahrnovat více interních modelových požadavků a opakování. Report proto uvádí
`budget_unit: codex_turn`, `underlying_model_calls: null` a
`rsi_experiments_supported: false`. Pro RSI použij níže popsaný provider s vlastní rozpočtovou bránou.

## Codex pro baseline a RSI kampaně

Po `codex-login` vyber model na `/rsi`: **Načíst modely Codexu → Použít Codex
pro RSI → Otestovat spojení**. Nebo v terminálu:

```bash
python -m rsi codex-status
python -m rsi config --set provider=codex --set codex_model=ID_Z_VYPISU
python -m rsi provider-check
python -m rsi init
python -m rsi doctor
python -m rsi baseline --limit 10
python -m rsi campaign --generations 1
```

Tento provider používá oficiální rozhraní Codex app-server a jeho konfigurovatelného
Responses providera (`requires_openai_auth=true`). Lokální brána s náhodnou cestou
na loopbacku rezervuje **každý skutečně předaný HTTP požadavek před odesláním**,
včetně případných opakování klienta. Přihlašovací hlavičky předá pouze v paměti
na výchozí backend oficiálního Codexu; nečte `auth.json`, nekopíruje tokeny do
registru a nepoužívá přímý SIWC OAuth token. Brána není obecná HTTP proxy.

Při vyčerpání počtu volání nebo rezervací tokenů další požadavek neodešle.
Chybějící spotřeba ponechá rezervaci; známé skutečné tokeny ji nahradí.
Server nevynucuje náš tokenový strop, takže jeden požadavek může účetní rozpočet
překročit. Potom se běh zastaví. Timeout a stop ukončí upstream proces.

Nativní nástroje Codexu jsou vypnuté a z požadavků odstraněné. Model vrací JSON
pro existující broker NeuroPilotu. Kandidátní Python a řešení úloh běží nadále
v ověřeném Docker/Podman/Bubblewrap sandboxu bez sítě, tokenů a skrytých testů.
Brány přijetí ani `auto_promote=false` se nemění. Přihlášený účet je během
experimentu kontrolován pomocí otisku identity; model nemá fallback.

Ověřená verze klienta: `codex 0.159.0-alpha.3`. Rozhraní app-server využívá
experimentální pole; po aktualizaci CLI znovu spusť test spojení. Tato verze
podporuje pouze výchozí backend `https://chatgpt.com` bez omezení směrování
workspace. Jinou regionální/residenční politiku odmítne. Modely bez této
kompatibility jsou překážkou, kterou aplikace neobchází. Seed ani konkrétní váhy
hostovaného modelu nelze připnout; report to výslovně uvádí.

Aktuální živé výsledky a reprodukci obsahuje `RSI_CODEX_REPORT.md`.
