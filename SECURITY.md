# Zabezpečení NeuroPilotu

Bezpečnostní opravy vznikají nad aktuální větví `main`. Starší snapshoty a ZIP
archivy v `research/` slouží jako historické důkazy, nejsou podporovaným vydáním.

## Soukromé hlášení problému

Použij [Report a vulnerability](https://github.com/HappyMistake64/NeuroPilot/security/advisories/new).
Soukromé hlášení je v repozitáři zapnuté (ověřeno 4. 10. 2026).
Do veřejného issue nevkládej tokeny, osobní data ani použitelný exploit.
Uveď verzi/commit, dopad a minimální reprodukci bez skutečných přihlašovacích údajů.

## Podporované použití

Aplikace běží na localhostu v jednom procesu. Kontrola Host/Origin, browserové
hlavičky a sandbox nejsou přihlašovací systém. Nezpřístupňuj Flask ani volitelné
Gradio přímo internetu; přístup z telefonu vyžaduje samostatně ověřené řízení
přístupu a TLS. Nepoužívej `debug=True`, Gradio `share=True` ani veřejný bind.
Webový výzkum načítá uživatelem zadané adresy; stávající kontrola veřejných IP
nenahrazuje síťový egress firewall proti změnám DNS. Nedůvěryhodné URL nepouštěj
v síti s dostupnými citlivými službami.

RSI kandidáti patří pouze do ověřeného sandboxu bez sítě a tajných údajů.
Neměň kvóty, hodnoticí brány nebo izolaci proto, aby prošel test. Tokenový limit
modelu je účetní kontrola, nikoli garantovaný strop účtování vzdáleného serveru.

## Závislosti a CI

Pro běžnou instalaci použij auditované verze v `requirements.lock.txt`; pro testy
`requirements-dev.lock.txt`. Instaluj pomocí `pip install --require-hashes -r ...`.
Oba lock soubory jsou vyřešené pro Python 3.11 s platformními markery; tato
verze Pythonu se také testuje v CI. Pro JavaScript použij
`npm ci --ignore-scripts`. Runtime modelu se běžnými testy nestahuje.

`requirements-ai.lock.txt` zachycuje volitelný modelový stack pro Linux/Python 3.11.
Audit kontroluje jeho závislosti bez instalace velkých modelových balíků; není
ověřením inference, kompatibility GPU ani jiných platforem.

CI na pull requestech a při týdenní kontrole obsahuje:

- testy aplikace, Python dependency audit, npm audit a redigovaný Gitleaks scan;
- CodeQL pro Python a JavaScript se sadou `security-extended`;
- minimální oprávnění workflow, vypnuté ukládání checkout credentials a žádné
  `pull_request_target` spouštění cizího kódu;
- akce připnuté na celé commit SHA, lockfiles s integritou balíků a Dependabot.

CodeQL hlásí nálezy do záložky Security. Dodatečná kontrola SARIF zastaví job při
každém nalezeném výsledku; samotný úspěšný upload nestačí. To neověřuje stav
starších alertů na jiných větvích. Bez aktivních ochranných pravidel větve lze CI obejít.
`.gitleaksignore` má pouze přesné výjimky pro ověřený hash ve starém reportu;
nikdy do něj nepřidávej skutečný token nebo plošnou výjimku pro zdrojový kód.

Při aktualizaci závislostí regeneruj příslušný lock příkazem v jeho záhlaví,
zkontroluj diff a spusť testy i audit. Připnutí verzí není náhradou aktualizací.

## Přihlašovací údaje a incidenty

Používej oficiální přihlášení; soubory `accounts.json`, `auth.json`, `.env`,
soukromé klíče, osobní paměť, stav agenta a generované projekty nepatří do Gitu.
`.gitignore` je prevence nechtěného přidání, nikoli ochrana již zveřejněných dat.

Pokud unikne token, nejprve jej odvolej u poskytovatele a obnov přihlášení.
Pouhé smazání souboru nebo přepsání historie token nezneplatní. Následně prověř
historii, logy, artefakty a přístupy; případné přepsání historie koordinuj s vlastníkem.
Nikomu neposílej heslo, obnovovací kód ani GitHub PAT v issue nebo chatu.

## Nastavení vlastníka na GitHubu

Aktuální stav, konkrétní nastavení a import ochrany `main` popisuje
[security/GITHUB_SETUP.md](security/GITHUB_SETUP.md).
