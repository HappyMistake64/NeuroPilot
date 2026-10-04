# Připojení NeuroPilotu v cloudovém Codexu — 4. 10. 2026

Výchozí commit `main`: `676ee04`. Větev: `feat/chatgpt-cloud-connection`.

**Výsledek: skutečná inference je blokovaná chybějící vlastní registrací
NeuroPilotu. Modelová odpověď ani využití předplatného aplikací nebyly ověřeny.**

## Podporované přihlášení

Oficiální dokumentace ověřena přes HTTPS během práce:

- [Registration and sign-in](https://developers.openai.com/siwc/token-sharing-open-source/sign-in)
- [Self-hosted VMs](https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms)
- [Models and inference](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference)
- [Preview limitations](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations)

Přímá OSS integrace používá vlastní dynamickou registraci NeuroPilotu, scope
`chatgpt.tokens.use.direct` a veřejný Responses endpoint. Na vzdálené VM je
podporovaný přenos registrace vytvořené stejnou aplikací při lokálním OAuth,
s ponecháním vlastního host ID VM. Není potřeba API klíč.

`codex login status` oznámil přihlášení přes ChatGPT. To dokládá pouze přihlášení
Codexu. Jeho credential store nebyl čten ani kopírován. `openai-status` aplikace
vrátil `active: null`, `accounts: []`, `inference_verified: false`. Na žádost
uživatele byly prohledány názvy souborů repozitáře; žádný soubor registrace nebyl
nalezen. Záznamy ve `verification/` jsou výsledky kontrol, nikoliv přihlášení.

## Dodané změny

- HTTP klient už nevypíná zděděnou proxy. Stejný klient používají discovery,
  přihlášení, refresh, katalog modelů a inference. TLS a zákaz redirectů zůstávají.
- `openai-import --file … --account …` importuje jednu chráněnou nativní
  registraci. Ověřuje identitu a oprávnění, zachovává host ID VM, neukládá
  neznámá metadata a odmítá uložení do projektu nebo RSI state.
- Dokumentace a UI vysvětlují cloudový postup a odlišují přihlášení od inference.
- 18 nových testů importu a proxy; všechny používají testovací tokeny.

## Skutečné ověření prostředí

Síťová politika prostředí byla aktuální a vynucená; nebyly nakonfigurovány žádné
secret bindings ani outbound identities. Po opravě klient NeuroPilotu skutečně
načetl `https://auth.openai.com/.well-known/openid-configuration`:
`oidc_discovery_reachable: true`, `issuer_matches: true`, JWKS na oficiálním
hostu. Jde o síťové ověření bez tokenu, ne o modelový dotaz.

Příkaz aplikace:

```bash
python -m rsi --state /workspace/scratch/neuropilot-cloud-check provider-check
```

State měl provider `chatgpt`, `max_calls=1`, `max_tokens=10240`,
`max_seconds=120`, beze zvoleného modelu (žádný katalog účtu nebyl dostupný).
Výsledek uložený registrem a zkopírovaný bez credential dat do
`verification/cloud_provider_check.json`:

- Run ID: `run-6f77a28dba70`
- `status: blocked`
- `model_inference_verified: false`
- Chyba: „Nejdřív se přihlas přes Continue with ChatGPT.“
- Počet modelových volání: **0**, účtovaná rezervace: **0**, skutečné tokeny: **null**

Nebyl proveden autentizovaný HTTP inference request. Neúspěšný preflight se
nevydává za skutečný modelový dotaz. K dokončení chybí chráněná registrace,
načtení modelového katalogu a jeden úspěšný `provider-check`.

Při prvním ověření `doctor` odmítl experimenty: Podman není nainstalován, Docker nemá lokální
obraz a Bubblewrap neprošel probe. Nebyla spuštěna baseline ani kampaň,
nebyla oslabena izolace, rozpočty, přijímací brány ani ochrana skrytých testů.

## Testy

Python 3.12, závislosti z `requirements-dev.txt`, jsdom z `package.json`.
Repozitář neměl npm lockfile, proto bylo použito `npm install`.

| Kontrola | Výsledek |
|---|---|
| Výchozí `python -m pytest tests -q` | 202 passed |
| Po změnách `python -m pytest tests -q` | 220 passed |
| `python agent_test.py` | prošel |
| `npm run test:ui` | prošel |
| `npm run test:rsi-ui` | prošel |

Testy rozhraní běžely s `PYTHON=/workspace/NeuroPilot/.venv/bin/python`.
DOM testy ani podepsané testovací JWT nedokládají živou inferenci.


## Následná oprava sandboxu

Docker daemon je funkční; byl stažen požadovaný obraz `python:3.12-slim`.
Docker nyní úspěšně ověřuje izolaci. Digest a výsledky kontrol jsou v
`verification/cloud_sandbox_check.json`.

Bubblewrap měl zapisovatelný vlastní kořenový tmpfs. Probe tak dokázal vytvořit
soubory `/root` a `/workspace` uvnitř sandboxu a správně běh odmítl; nešlo o zápis
do hostitelského `/root` nebo `/workspace`. Přidáno `--remount-ro /` po sestavení
mountů. Kořen je nyní pouze pro čtení, oddělený `/tmp` zůstává zapisovatelný.
Stávající kontroly nebyly zmírněny. Bubblewrap nyní prochází všemi kontrolami.

Ověření po opravě:

- `NEUROPILOT_TEST_SANDBOXES=bwrap,docker python -m pytest tests -q`:
  **222 passed**, včetně dvou skutečných testů sandboxu. Bez této proměnné se
  explicitní integrační testy přeskočí, aby unit suite nevyžadovala Docker.
- Oba DOM testy opět prošly.
- Skutečný `reference-check` přes Bubblewrap: **60/60 referencí prošlo a 60/60
  vadných řešení bylo odhaleno**, bez modelu. Výsledek je v
  `verification/cloud_reference_check.json`.
- Aktuální `doctor`: **sandbox.ok=true**, model stále bez přihlášení;
  `ready=false`. Viz `verification/cloud_doctor.json`.
- Opakovaný `provider-check`: `blocked`, 0 modelových volání, inference neověřena.
  Viz `verification/cloud_provider_check_latest.json`.

Uživatel má k dispozici pouze telefon. Současné přímé OAuth s loopback callbackem
nelze dokončit na telefonu pro aplikaci běžící na cloudové VM. Oficiální postup
pro tuto integraci vyžaduje lokální přihlášení stejné aplikace a přenos registrace.
Codex CLI má vlastní podporovaný device-code login, ale jeho registrace není
registrací přímého provideru NeuroPilotu. Nebyl zaveden neoficiální endpoint,
kopírovány tokeny Codexu ani deklarována neprovedená inference. Zbývá získat vlastní
registraci NeuroPilotu; izolace už není překážkou.
