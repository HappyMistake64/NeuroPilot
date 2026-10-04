# Skutečné připojení NeuroPilotu přes Codex app-server

Datum: 4. 10. 2026. Výchozí `main`: `52b5ced7aa701d06b1b3e60bc3843ddb43ba4a19`.
Větev: `feat/codex-model-connection`. Codex CLI: `0.159.0-alpha.3`.

**NeuroPilot provedl skutečný modelový dotaz přes přihlášení ChatGPT spravované
Codexem. Výsledek je ověřený; automatické RSI kampaně tuto cestu zatím nepoužívají.**

## Podporovaná cesta a přihlášení z telefonu

Oficiální rozhraní [Codex app-server](https://developers.openai.com/codex/app-server)
je určené pro integrace aplikací a podporuje `account/read`, `model/list`,
`thread/start`, `turn/start` a `account/login/start` s typem `chatgptDeviceCode`.
[Dokumentace přihlášení](https://developers.openai.com/codex/auth) podporuje také
`codex login --device-auth`. Obě dokumentace byly přečteny při implementaci.

Původní účet vypadal přihlášený, ale první skutečný tah skončil `unauthorized`:
server odmítl obnovení staré relace. Samotné přihlášení ani katalog se tedy
nepovažovaly za důkaz inference. Pokus přes app-server nedostal potvrzení a byl
ukončen. Následující pokus přímo oficiálním CLI po potvrzení uživatelem na telefonu
skončil `Successfully logged in`. Teprve potom byl zopakován dotaz NeuroPilotu.

NeuroPilot nečetl ani nekopíroval tokeny Codexu. Jejich uložení a obnovu spravuje
oficiální klient mimo repozitář. Jednorázové přihlašovací kódy nejsou v této
zprávě ani v commitu. Nejde o přenos přihlášení do dosavadního přímého OAuth
provideru: ten má nadále vlastní oddělenou registraci.

## Skutečný výsledek

Příkaz provedený z kořene NeuroPilotu:

```bash
.venv/bin/python -m rsi --state /workspace/scratch/neuropilot-codex-check codex-check
```

Vybraný model byl výchozí model z katalogu po novém přihlášení. Žádný fallback
na API klíč, jiného providera nebo jiný model nebyl použit.

| Položka | Pozorovaný výsledek |
|---|---|
| Run ID | `run-8a56b31edf8c` |
| Transport | `codex_app_server` |
| Přihlášení | `chatgpt` |
| Model | `gpt-6.1-sol` |
| Status | `complete` |
| Ověřená inference | `true` |
| Počet odeslaných tahů | 1 |
| Vstupní tokeny | 5 040 |
| Výstupní tokeny | 38 |
| Skutečné tokeny celkem | 5 078 |
| Počet interních modelových HTTP požadavků | nezjištěn |

Model vrátil přesně požadovaný JSON s novou náhodnou výzvou:

```json
{"connection":"ok","nonce":"0d3d73d6268da03a27b1915ad4f03865"}
```

Důkaz: `verification/codex_model_connection.json`, včetně dostupné tokenové
telemetrie. Výsledek vznikl přijetím `turn/completed` se stavem `completed`
a kontrolou celé odpovědi proti výzvě. Test se nespokojí s přihlášením,
katalogem, částečným textem, chybnou výzvou nebo nedokončeným tahem.

## Implementace a hranice

Nové příkazy: `codex-status`, `codex-login`, `codex-check [--model ID]`.
`codex-login` používá přímo úspěšně ověřený oficiální CLI device-code flow;
nezávisí na prvním nedokončeném pokusu přes app-server.
`rsi/codex_connection.py` obsahuje omezený stdio JSON-RPC transport, deadline,
limit velikosti odpovědí a ukončení procesové skupiny při chybě nebo zastavení.
Surové chyby provideru, konfigurace a přihlašovací údaje se nezapisují do auditu.

Kontrola používá pouze pevný krátký prompt, nový dočasný pracovní adresář,
ephemeral thread, read-only sandbox, prázdné execution environments a vypnuté
nástroje, pluginy, hooks a nakonfigurované MCP servery. Nepředává projekt ani
skryté testy. Nepodporované serverové požadavky a výstupy nástrojů odmítá.

**RSI kampaně tuto integraci zatím nepoužívají.** Jeden tah app-serveru může
zahrnovat více interních volání nebo retry. Počet interních požadavků se nevydává
za jeden. Audit explicitně uvádí `budget_unit: codex_turn`,
`underlying_model_calls: null`, `rsi_experiments_supported: false`.
Konfigurace `provider=codex` není povolená. Dosavadní limity experimentů,
sandboxy, hodnoticí brány a přímý OAuth provider zůstávají zachované.

Pro kontrolu se rezervuje nejvýše jeden tah, platí existující timeout a tokenový
účetní rozpočet. Chybějící telemetrie není nula a ponechává rezervaci. Jeden tah
může překročit rezervaci; serverový tvrdý tokenový strop není podporován.
Zastavení místního procesu nezaručuje zastavení vzdáleného účtování. Účetní
omezení předplatného se nadále řídí účtem ChatGPT.

## Testy

- `NEUROPILOT_TEST_SANDBOXES=bwrap,docker python -m pytest tests -q`:
  **239 passed**, včetně 17 nových protokolových a procesových testů.
- `python agent_test.py`: prošel.
- `npm run test:ui`: prošel.
- `npm run test:rsi-ui`: prošel.
- `git diff --check`: prošel.

Protokolové testy používají fixtures; skutečný modelový důkaz je oddělený výše.
Další krok pro automatické kampaně je spolehlivé účtování interních modelových
volání. Doložený přínos RSI ani sebezdokonalení se tímto výsledkem netvrdí.
