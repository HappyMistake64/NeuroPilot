# Bezpečnostní kontrola — 4. 10. 2026

Základ: `main` po PR #3, commit `70dd4578cebfad3f70847351d2f4c325b7eed295`.
Výsledky nástrojů shrnuje [verification/security_audit.json](../verification/security_audit.json).
Nejde o penetrační test ani záruku neexistence dalších zranitelností.

## Opraveno v bezpečnostním PR

- Chybělo pravidelné skenování závislostí a tajných údajů: přidán audit core,
  testovacích, volitelných AI a auditních Python závislostí, npm audit,
  Gitleaks historie i souborů včetně dekódování a archivů do hloubky 2.
- Akce byly navázané pouze na pohyblivé major tagy; nyní mají celé commit SHA.
  Python lockfiles obsahují verze a SHA256 hash balíků, npm lockfile integritu.
  CI používá `--require-hashes` a `npm ci --ignore-scripts`.
- Nově CodeQL pro Python/JavaScript, týdenní kontrola, Dependabot a CODEOWNERS.
  Joby mají omezená oprávnění; žádný nedůvěryhodný PR neběží přes
  `pull_request_target`. Změny dependencí se neslučují automaticky.
- Kontrola Origin dříve porovnávala jen síťovou autoritu bez schématu.
  Nyní ověřuje schéma/host/port, odmítá neplatné URL a browserové požadavky
  z jiného původu i při chybějící Origin hlavičce, pokud je dostupná Fetch Metadata.
- Doplněna ochrana proti vložení UI do rámce, omezení skriptů přes CSP, zákaz
  MIME sniffingu, referrerů a ukládání JSON odpovědí do cache.
- Doplněno ignorování osobní paměti, stavu agenta a generovaných projektů.

## Ověření

**284 Python testů prošlo**, včetně 20 nových bezpečnostních regresí a skutečných
zkoušek Bubblewrap/Docker. Prošel test agenta i oba DOM testy po instalaci ze
zamčených závislostí. DOM testy neověřují vynucení CSP skutečným prohlížečem;
regrese kontrolují odesílané hlavičky a chování serveru.

Python dependency audity i npm audit nenašly známou zranitelnost. Volitelný AI
stack byl vyřešen a auditován bez instalace velkých balíků či stahování modelu.
Gitleaks kontrola všech místních Git refs a sledovaných souborů po přesném
vyloučení jediného falešného nálezu nenašla tajné údaje. Nález byl uložený
SHA256 souboru `rsi/openai_auth.py` ve starém měřicím reportu, nikoli token.
Výjimky se vztahují jen na konkrétní fingerprint historie a souboru; žádný
adresář ani obecný vzor klíčů není vynechán.

Pomocná analýza Bandit byla ručně posouzena: jediný nález úrovně medium označil
`/tmp` v argumentech Bubblewrapu. Jde o privátní tmpfs uvnitř izolace, nikoli
předvídatelný dočasný hostitelský soubor. Upozornění na subprocess používají
seznamy argumentů bez shellu; náhodný výběr odpovědí/pořadí úloh není
kryptografické použití. Řetězce názvů tokenových limitů nejsou hesla.

## Zbývá u vlastníka GitHubu

`main` nebyla chráněná a rulesety nebyly nastavené. Soukromé hlášení zranitelností
je již zapnuté. Správa ochrany větve, nastavení Actions a čtení CodeQL konfigurace
nejsou připojenému GitHub App dostupné (HTTP 403). Proto nebyly změněny ani nebylo
potvrzeno zapnutí push protection / secret scanning / Dependabot alerts.
Připravený import a postup: [GITHUB_SETUP.md](GITHUB_SETUP.md).

CI se musí úspěšně provést a jeho konfigurace se musí sloučit na `main`.
Pravidelné běhy a Dependabot se aktivují z výchozí větve. Zelený CodeQL upload
není potvrzení nulových nálezů; sleduj také záložku Security.

## Hranice kontroly

Aplikace stále nemá uživatelské přihlášení pro veřejný provoz. Neměnila se
viditelnost repozitáře, přístupy spolupracovníků ani přihlášení ChatGPT. Zastavení
úlohy není garance zastavení vzdáleného účtování. Volitelné načítání webu kontroluje
IP a redirecty, ale bez síťové kontroly cílových spojení není ochrana proti DNS
rebindingu úplná. Pro veřejné nasazení je nutná samostatná bezpečnostní práce.
