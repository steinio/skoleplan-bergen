# Skoleplan Bergen

Ukeplaner (*arbeidsplaner*) for grunnskolene i Bergen, samlet på én side — med
kalenderabonnement for klassene der skolens plan er tydelig nok til å lage ett.

**👉 [Åpne siden](https://steinio.github.io/skoleplan-bergen/)**

Finn skolen, finn klassen, trykk *Legg til i kalender*. Ingen konto, ingen
innlogging, ingenting å installere. Lekser, prøver, turer og fridager dukker opp
i kalenderen din av seg selv.

Uoffisiell tjeneste laget av en forelder. Alt innholdet hentes fra skolenes egne,
åpent publiserte sider på bergen.kommune.no.

## Hvorfor bare noen klasser har kalender

Skolene publiserer planene sine svært ulikt. Alle 81 skolene bruker én av to
former, og det avgjør hva som er mulig:

| Form | Skoler | Hva vi får til |
| --- | ---: | --- |
| Publisert Google-dokument | 15 | Leser ukeplanen; lekser der oppsettet tillater det |
| PDF via kommunens filarkiv | 68 | Lenke til nyeste uke per trinn |

Radene er merket ærlig:

* **kalender** — datoene er til å stole på, så vi lager et `.ics`-abonnement
* **plan** — planen er lest, men dokumentet sier ikke hvilken uke den gjelder
* **pdf** — skolen publiserer PDF-er; vi lenker til nyeste

En kalenderoppføring på feil dag er verre enn ingen oppføring. Derfor lager vi
aldri et abonnement av en uke vi bare har gjettet.

## Periode

Velg **periode** øverst på siden før du abonnerer. Standard er en uke tilbake og
fire måneder frem, så kalenderen din slipper både gamle timer og neste sommer.
Du kan også velge én måned eller hele skoleåret.

Perioden er bakt inn i selve kalenderfilen — en `.ics` kan ikke lese
spørrestreng — så valget må tas før du abonnerer. Vil du bytte senere, fjern
abonnementet og legg det til på nytt med den andre perioden.

## Kjøre det selv

Ingen avhengigheter utover Python 3.10+.

```bash
python3 catalogue.py                  # kartlegg alle skolene -> data/catalogue.json
python3 build_site.py                 # bygg siden og kalenderne -> site/
python3 build_site.py --render-only   # bygg bare siden på nytt, uten nedlasting
python3 scrape.py --class 8E          # én klasse, til JSON/ICS/HTML/Markdown
python3 -m pytest tests -q
```

## Hvordan det virker

```
schoolplan/bergen.py      finn skoler og planer fra kommunens sitemap
schoolplan/tablegrid.py   HTML-tabeller -> rutenett (slår ut rowspan/colspan)
schoolplan/parse.py       rutenett -> uker, dager, timer, terminoversikt
schoolplan/aux.py         lekser fra hjelpetabellene skolene bruker
schoolplan/highlights.py  norsk tekst -> kategori (lekse, prøve, tur, fridag …)
schoolplan/render_ics.py  kalenderfil man kan abonnere på
build_site.py             hele nettsiden
```

Siden bygges og publiseres automatisk to ganger i døgnet av
`.github/workflows/site.yml`.

## Feil i planen din?

Innholdet kommer rått fra skolens eget dokument — vi retter ikke på det. Står
det feil der, står det feil her. Mangler klassen din, eller ser noe rart ut,
[opprett en sak](https://github.com/steinio/skoleplan-bergen/issues).

## Bruksstatistikk

Siden teller hvor mange som faktisk bruker den, i to deler, fordi de måler helt
ulike ting:

* **Sidevisninger** — et lite skript fra GoatCounter, uten informasjonskapsler.
* **Abonnementer** — en Cloudflare Worker foran kalenderfilene, i `worker/`.

Grunnen til at det trengs to: en kalenderapp kjører aldri JavaScript. Den henter
bare `.ics`-filen med noen timers mellomrom, i det uendelige. Sidestatistikk ser
derfor ingen abonnenter i det hele tatt, og GitHub Pages gir ingen tilgangslogg.

Begge er valgfrie. Uten oppsett kjører siden helt uten sporing.

### Sette opp telling av abonnenter

```bash
cd worker
npx wrangler kv namespace create COUNTS     # lim id-en inn i wrangler.toml
npx wrangler deploy
```

Sett så `ICS_HOST` som repository-variabel (*Settings → Secrets and variables →
Actions → Variables*) til adressen workeren fikk, for eksempel
`https://skoleplan.ditt-navn.workers.dev`. Neste bygg peker kalenderlenkene dit.

Tall hentes fra `/stats` på samme adresse:

```json
{ "subscribed_classes": 14, "classes": { "gimle-oppveksttun-skole-8e": 3 } }
```

Workeren teller **unike klienter per klasse per dag**, ikke forespørsler — én
telefon som spør åtte ganger om dagen skal telle som én abonnent.

### Sette opp sidevisninger

Opprett en konto på [goatcounter.com](https://www.goatcounter.com/) og sett
`GOATCOUNTER_CODE` som repository-variabel til kodenavnet ditt.

## Personvern

Tjenesten har ingen konto og ingen innlogging, og henter kun sider skolene
allerede har publisert åpent.

Med tellingen slått på:

* **Ingen IP-adresse lagres.** Workeren lager en SHA-256-sum av adressen,
  klassen og datoen, med et salt som byttes hver dag. Summen kan ikke regnes
  tilbake til en adresse, og kan ikke brukes til å følge noen fra én dag til den
  neste. Den slettes etter 48 timer.
* **Det lagres bare summer** — hvor mange som abonnerer på hver klasse, per dag.
* **Ingen informasjonskapsler**, verken fra siden eller fra GoatCounter, så det
  trengs ingen samtykkeboks.

Er tellingen ikke satt opp, skjer ingenting av dette.
