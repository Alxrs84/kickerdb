import pandas as pd

# CSV-Dateien laden mit korrektem Separator
original_file = "autodownload/data_2024-12-23_10-17-03.csv"  # Ursprungsdatenstand
updated_file = "autodownload/data_2025-01-05_10-17-03.csv"   # Veränderte Daten

# CSV-Dateien einlesen und sicherstellen, dass sie semicolon-getrennt sind
df_original = pd.read_csv(original_file, sep=';')
df_updated = pd.read_csv(updated_file, sep=';')

# Spaltennamen bereinigen (z. B. Leerzeichen entfernen)
df_original.columns = df_original.columns.str.strip()
df_updated.columns = df_updated.columns.str.strip()

# Spaltennamen prüfen
if "ID" not in df_original.columns or "ID" not in df_updated.columns:
    raise KeyError("Die Spalte 'ID' wurde in den Dateien nicht gefunden. Verfügbare Spalten sind:"
                   f"\nOriginal: {df_original.columns}\nUpdate: {df_updated.columns}")

# Vergleichskategorien definieren
key_field = "ID"  # Primärschlüssel (z. B. Spieler-ID)
compare_fields = ["Marktwert", "Punkte"]

# Hinzugefügte Zeilen
added_rows = df_updated[~df_updated[key_field].isin(df_original[key_field])]
added_rows["Änderungstyp"] = "Hinzugefügt"

# Entfernte Zeilen
removed_rows = df_original[~df_original[key_field].isin(df_updated[key_field])]
removed_rows["Änderungstyp"] = "Entfernt"

# Geänderte Zeilen: Schnittmenge nach ID, Unterschiede in Vergleichsfeldern
common_rows = df_original.merge(df_updated, on=key_field, suffixes=('_old', '_new'))
changed_rows = common_rows[
    (common_rows[[f"{field}_old" for field in compare_fields]] !=
     common_rows[[f"{field}_new" for field in compare_fields]].values).any(axis=1)
]

# Wenn geänderte Zeilen gefunden, Differenzen berechnen
if not changed_rows.empty:
    for field in compare_fields:
        changed_rows[f"{field}_Differenz"] = changed_rows[f"{field}_new"] - changed_rows[f"{field}_old"]
    changed_rows["Änderungstyp"] = "Geändert"

# Alle Unterschiede in einer Datei zusammenführen
differences = pd.concat([added_rows, removed_rows, changed_rows], ignore_index=True)

# Ergebnisse anzeigen
print("Zusammenfassung der Unterschiede:")
print(differences)

# Exportiere alle Unterschiede in eine CSV-Datei
differences.to_csv("alle_unterschiede.csv", index=False)

# Optional: Separate Dateien für jeden Unterschiedstyp exportieren
#added_rows.to_csv("added_rows.csv", index=False)
#removed_rows.to_csv("removed_rows.csv", index=False)
#changed_rows.to_csv("changed_rows.csv", index=False)
