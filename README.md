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

## Personvern

Tjenesten lagrer ingenting om deg. Den har ingen konto, ingen informasjonskapsler
og ingen sporing, og henter kun sider skolene allerede har publisert åpent.
