# Infrastructure Context – Homelab (Alex)

> **Zweck dieses Dokuments:** Onboarding für einen KI-Agenten (z.B. Claude Code, Cursor),
> der in diesem Homelab Repos in Gitea anlegen und Code in Docker-Containern auf der
> `dockervm` ausführen soll. Deployment erfolgt über das bestehende Webhook-Pattern
> (siehe Abschnitt "Deployment-Pipeline").

---

## 1. Netzwerk-Topologie

| Komponente              | IP                  | Rolle                                       |
|-------------------------|---------------------|---------------------------------------------|
| UDM Pro (Gateway)       | `192.168.116.1`     | Router, Firewall                            |
| PiHole                  | `192.168.116.240`   | DNS für `.lan` Domains                      |
| Nginx Proxy Manager     | `192.168.116.205`   | Reverse Proxy für interne Dienste           |
| Proxmox Host            | `192.168.116.200`   | Virtualisierung                             |
| **Gitea** (auf dockervm)| `192.168.116.230:3010` | Git-Server + Webhooks                     |
| **Docker Host (dockervm)** | `192.168.116.230` | Debian 12, User `alex`, alle App-Container |
| Webhook-Receiver        | `192.168.116.230:9001` | Empfängt Gitea Push-Events               |
| Synology NAS            | `192.168.116.101`   | NFS-Server, Massendaten                     |
| Portainer (auf dockervm)| `portainer.lan:9000`| Container-Verwaltung                        |

**Subnetz:** `192.168.116.0/24` (Standard-LAN). Es gibt zusätzlich ein isoliertes VLAN
`192.168.2.0/24` – aktuell für den Agenten **nicht relevant**.

---

## 2. Storage-Regeln (HARTE REGELN – nicht verhandelbar)

| Datentyp                       | Speicherort                  | Begründung                          |
|--------------------------------|------------------------------|-------------------------------------|
| **Datenbanken (SQLite, PG, etc.)** | Lokale NVMe (Docker Named Volume) | NFS → SQLite-Korruption          |
| App-Code / Repos               | `/opt/<projekt>/` auf dockervm | Lokale NVMe, schneller Build       |
| Massendaten, Configs, Media    | `/mnt/nas/docker/<projekt>/` | NFS-Mount vom NAS                   |
| Backups                        | NAS, separater Pfad          | Off-Host                            |

> ⚠️ **Agent darf niemals Datenbank-Volumes nach `/mnt/nas/...` mounten.** Bei Zweifel:
> Named Volume verwenden, nie Bind-Mount auf NFS für Schreib-intensive DB-Files.

**Standard-NFS-Mount in der dockervm:** `/mnt/nas/docker`

---

## 3. Deployment-Pipeline (Push-to-Deploy via Webhook)

Der Agent folgt dem etablierten Muster aus `road-to-2010`. Schema:

```
git push origin <branch>
        │
        ▼
   Gitea (192.168.116.230:3010)
        │  Webhook (branch-filter, mit Secret)
        ▼
   webhook-binary (dockervm:9001)
        │  führt deploy-Script aus
        ▼
   docker compose up --build -d
```

### Branch-Konvention

| Branch    | Environment | Trigger                          |
|-----------|-------------|----------------------------------|
| `main`    | PROD        | Auto-Deploy via Webhook          |
| `develop` | TEST        | Auto-Deploy via Webhook          |
| Feature-Branches | -    | Kein Auto-Deploy                 |

### Was der Agent pro neuem Projekt einrichten muss

1. **Gitea-Repo anlegen** via API (siehe Abschnitt 5)
2. **Verzeichnisse** auf dockervm: `/opt/<projekt>/prod` und `/opt/<projekt>/test`
3. **Webhook-Hooks** in `/opt/webhook/hooks.json` ergänzen (neue `id`)
4. **Deploy-Scripts** in `/opt/webhook/deploy-<projekt>-prod.sh` + `-test.sh`
5. **Gitea Webhook** im Repo registrieren (Push-Event, Branch-Filter, **Secret setzen**)
6. **Ports** im `docker-compose.yml` eindeutig wählen (siehe Port-Tabelle Abschnitt 7)
7. **webhook.service neustarten:** `sudo systemctl restart webhook`

### Bestehende Webhook-Struktur (Referenz)

```
/opt/webhook/
├── hooks.json          # Alle Hook-Definitionen (JSON-Array)
├── deploy-prod.sh
├── deploy-test.sh
└── deploy-<neues-projekt>-{prod,test}.sh   ← neue Scripts hier
```

`webhook.service` läuft als User `alex` (nicht root) und horcht auf Port `9001`.

---

## 4. Sicherheits-Pflichten für den Agenten

> Diese Punkte sind **bewusst strenger als die bestehende `road-to-2010`-Pipeline**,
> die historisch ohne Secrets gestartet ist. Für neue Projekte gilt:

- **Webhook-Secret pflicht.** Jeder neue Hook in `hooks.json` muss `trigger-rule` mit
  HMAC-SHA256-Signaturprüfung (`x-gitea-signature`) haben. Secret wird in Gitea und
  in `hooks.json` hinterlegt, nicht im Repo.
- **Gitea Access Token mit minimalem Scope.** Wenn der Agent Repos anlegt: Token mit
  Scope `write:repository` (nicht Admin). Token niemals in Repos committen, nur über
  ENV-Variable / Secrets-File auf der dockervm.
- **Kein Docker-Socket-Mount** in Agent-Containern ohne expliziten Grund. Falls nötig:
  `tecnativa/docker-socket-proxy` als Vermittler, nie `/var/run/docker.sock` direkt.
- **Keine Root-Logins via SSH.** Alle Aktionen auf dockervm laufen als User `alex` mit
  `sudo` bei Bedarf. `webhook.service` läuft auch als `alex`.
- **PUID/PGID prüfen** bei Bind-Mounts auf NFS – `alex` auf dockervm hat UID `1000`,
  muss zur NAS-Berechtigung passen.
- **Rollback-Strategie überlegen** für jeden neuen Service. Aktuelles
  `docker compose up --build` lässt den Container im undefinierten Zustand wenn der
  Build crasht – für kritische Dienste Tagged Images statt `:latest` verwenden.

---

## 5. Gitea API – Cheatsheet für den Agenten

**Base-URL:** `http://192.168.116.230:3010/api/v1`
**Auth:** `Authorization: token <ACCESS_TOKEN>` (Token aus Gitea → User Settings → Applications)

### Repo anlegen

```bash
curl -X POST "http://192.168.116.230:3010/api/v1/user/repos" \
  -H "Authorization: token $GITEA_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "mein-projekt",
    "description": "...",
    "private": true,
    "auto_init": true,
    "default_branch": "main"
  }'
```

### Webhook am Repo registrieren

```bash
curl -X POST "http://192.168.116.230:3010/api/v1/repos/<owner>/<repo>/hooks" \
  -H "Authorization: token $GITEA_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "gitea",
    "active": true,
    "events": ["push"],
    "branch_filter": "main",
    "config": {
      "url": "http://192.168.116.230:9001/hooks/deploy-<projekt>-prod",
      "content_type": "json",
      "secret": "<webhook-secret>"
    }
  }'
```

### Code pushen (Standard-Git, keine API)

```bash
git remote add origin http://<user>:$GITEA_TOKEN@192.168.116.230:3010/<owner>/<repo>.git
git push origin main
```

> 💡 Token in URL nur in CI/Agent-Kontext – auf Dev-Maschinen lieber Credential-Helper
> oder SSH-Key.

---

## 6. Verhaltensregeln für den Agenten

- **`docker compose` statt einzelner `docker run`.** Jeder Service als Stack.
- **Named Volumes für DBs**, Bind-Mounts (`/mnt/nas/docker/...`) für Massendaten.
- **Bei NFS-Bind-Mounts**: PUID/PGID prüfen (User `alex` = UID 1000 auf dockervm).
- **Keine Default-Ports**, die kollidieren – Port-Tabelle (Abschnitt 7) konsultieren
  und neuen Eintrag ergänzen.
- **Bei Unsicherheit Pushback statt blindem Ausführen.** Lieber kurz nachfragen als
  Prod kaputt machen.
- **Erklären, *warum*** ein nicht-trivialer Befehl gemacht wird (gilt auch für den Agenten,
  wenn er einen Plan vorschlägt).
- **Erinnern an `sudo` statt Root-Login** falls SSH-Themen auftauchen.

---

## 7. Port-Belegung dockervm (Stand: bei Änderungen pflegen)

| Port  | Service                | Container/Stack         |
|-------|------------------------|-------------------------|
| 3002  | road-to-2010 PROD      | `fifa-tracker`          |
| 3003  | road-to-2010 TEST      | `fifa-tracker-test`     |
| 3010  | Gitea                  | `gitea`                 |
| 9000  | Portainer              | `portainer`             |
| 9001  | Webhook-Receiver       | systemd `webhook.service`|
| ????  | *(neue Services hier eintragen)* |               |

> Agent: **vor neuer Port-Wahl diese Tabelle checken und ergänzen.**

---

## 8. Nützliche Befehle (für den Agenten als Referenz)

```bash
# Webhook-Service
sudo systemctl status webhook
sudo systemctl restart webhook
journalctl -u webhook -f

# Manuell Deploy triggern (Bypass Gitea)
curl -X POST http://192.168.116.230:9001/hooks/deploy-<projekt>-prod

# Container-Status
docker ps
docker compose -f /opt/<projekt>/prod/docker-compose.yml logs -f

# DB-Backup aus Named Volume
docker cp <container>:/app/data/dev.db ~/backup-$(date +%Y%m%d).db
```

---

## 9. Was der Agent NICHT tun darf

- ❌ Datenbank-Files auf NFS schreiben
- ❌ Container als `root` ohne Notwendigkeit laufen lassen
- ❌ `/var/run/docker.sock` ohne Proxy in Container mounten
- ❌ Secrets/Tokens ins Repo committen
- ❌ Bestehende `road-to-2010`-Hooks ändern (eigene anlegen)
- ❌ Auf dem Proxmox-Host direkt arbeiten – Workloads gehören in LXC/VM
- ❌ Webhooks ohne Secret anlegen (bestehende Legacy-Hooks ausgenommen)

---

## 10. Offene Punkte / TODOs (für Alex, nicht den Agenten)

- [ ] Bestehende `road-to-2010` Webhooks nachträglich mit Secret absichern
- [ ] Rollback-Strategie für `compose up --build` Fehlerfälle definieren
- [ ] Tagged Images (`:v1.2.3`) statt `:latest` für PROD evaluieren
- [ ] Gitea-Backup-Strategie dokumentieren (DB liegt wo genau?)
