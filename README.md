# Asset Tracker (lokal, macvlan, mit Basic-Auth)

## Aufbau
- Flask-Webinterface zur Verwaltung von "Assets" (z.B. Konten, Depots, Immobilien).
- Pro Asset wird eine eigene CSV-Datei mit den Spalten `date,value` im Docker-Volume `asset_data` (Pfad im Container: `/data/assets/<name>.csv`) gepflegt.
- Assets koennen ueber das Webinterface angelegt, umbenannt und geloescht werden (Umbenennen benennt die CSV-Datei um und passt betroffene Portfolios automatisch an).
- Werte (Datum + Wert) koennen angelegt und bearbeitet werden, solange der Eintrag nicht aelter als 7 Tage ist.
- Sperrfrist: Jeder Eintrag, dessen Datum mehr als 7 Tage in der Vergangenheit liegt, gilt als gesperrt. Gesperrte Eintraege koennen ueber das Webinterface weder bearbeitet noch geloescht werden. Neue, rueckwirkende Eintraege fuer ein noch nicht vorhandenes Datum lassen sich weiterhin anlegen; erst ein bereits bestehender, mehr als 7 Tage alter Eintrag ist unveraenderbar.
- Portfolios (Subsets von Assets) koennen angelegt werden; die Summenzeitreihe wird per Forward-Fill je Asset gebildet und dann aufsummiert.
- API-Endpoint fuer Automatisierung: GET /api/portfolio/<name> liefert JSON [[datum, summe], ...] (per Basic-Auth geschuetzt).
- Das gesamte Webinterface ist per HTTP Basic Auth geschuetzt.

## Vor dem Start unbedingt anpassen (docker-compose.yml)
1. APP_PASSWORD auf ein eigenes, sicheres Passwort setzen (aktuell Platzhalter BITTE_AENDERN).
2. SECRET_KEY auf einen zufaelligen, langen String setzen, z.B. erzeugen mit:
   python3 -c "import secrets; print(secrets.token_hex(32))"
3. APP_USERNAME bei Bedarf anpassen (Default: admin).

Netzwerk-Parameter sind bereits eingetragen:
- Parent-Interface: eth0
- Subnetz: 192.168.0.0/24, Gateway: 192.168.0.1
- Container-IP: 192.168.0.37 (fest reserviert)

## Starten
```
docker compose up -d --build
```

Danach ist das Interface unter http://192.168.0.37:5000 erreichbar (Login mit Username/Passwort aus der compose-Datei), aber nur aus deinem LAN.

## Wichtiger Hinweis zu macvlan
Der Docker-Host selbst kann standardmaessig NICHT per 192.168.0.37 auf den Container zugreifen (macvlan isoliert den Host vom Container-Traffic). Von allen anderen Geraeten im 192.168.0.0/24-Netz ist der Container aber normal erreichbar.

## Backup
Die CSV-Dateien liegen im Volume asset_data. Sicherung z.B. mit:
```
docker run --rm -v asset_data:/data -v $(pwd):/backup alpine tar czf /backup/asset_data_backup.tar.gz -C /data .
```
