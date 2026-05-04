# Huawei Virtual Meter Emulator für Home Assistant

Diese Custom Component emuliert ein Huawei Smart Meter (über Modbus TCP und UDP Discovery) direkt aus Home Assistant heraus. Sie ermöglicht es, eine Huawei Wallbox mit dynamischen Werten zu füttern, die über die Home Assistant UI konfiguriert werden.

## Funktionen
- **UDP Discovery:** Antwortet auf Port 6600, damit die Wallbox das "Meter" findet.
- **Modbus TCP:** Lauscht auf Port 502 für eingehende Register-Abfragen.
- **UI-Konfiguration:** Register können bequem über die Integrationsoberfläche an beliebige Home Assistant Entitäten (Sensoren, Input Numbers) gebunden werden.

## Installation über HACS
1. Öffne HACS in deinem Home Assistant.
2. Klicke oben rechts auf das Drei-Punkte-Menü und wähle **"Benutzerdefinierte Repositories"**.
3. Füge die URL deines GitHub-Repositories ein und wähle als Kategorie **"Integration"**.
4. Klicke auf Herunterladen und starte Home Assistant neu.
