/**
 * API-Client: Synchrones Interface zur Leihgut REST-API
 * (Fehlerbehandlung: HTTP-Fehler werfen, nicht swallown)
 */

const BASE_URL = "";

class LeihgutApiClient {
  /**
   * Hilfsmethode: Fetch mit automatischem X-Rolle Header + Fehlerbehandlung
   */
  async request(method, endpoint, body = null, rolle = "thekendienst") {
    const options = {
      method,
      headers: {
        "Content-Type": "application/json",
        "X-Rolle": rolle,
      },
    };

    if (body) {
      options.body = JSON.stringify(body);
    }

    const response = await fetch(`${BASE_URL}${endpoint}`, options);
    const data = await response.json();

    if (!response.ok) {
      const error = new Error(
        data.detail?.fehlercode || data.detail || response.statusText
      );
      error.status = response.status;
      error.fehlercode = data.detail?.fehlercode;
      throw error;
    }

    return data;
  }

  // === UC-10: Verfügbarkeit prüfen ===
  async getGegenstandVerfuegbarkeit(inventarnummer) {
    return this.request("GET", `/gegenstaende/${inventarnummer}`);
  }

  async getAlleKategorienVerfuegbarkeit() {
    // Keine explizite API für "alle" — wir müssen kategorien auflisten
    // Fallback: hardcoded demo-kategorien. Real: würde /kategorien endpunkt brauchen
    return this.request("GET", `/kategorien/test/verfuegbarkeit`);
  }

  // === UC-01: Gegenstand ausgeben ===
  async gegenstandAusgeben(inventarnummer, mitgliedId, rolle = "thekendienst") {
    return this.request(
      "POST",
      `/gegenstaende/${inventarnummer}/ausgabe`,
      { mitgliedId },
      rolle
    );
  }

  // === UC-03: Gegenstand zurücknehmen ===
  async gegenstandZuruecknehmen(ausleiheId, auffaelligkeiten = null, rolle = "thekendienst") {
    const body = auffaelligkeiten ? { auffaelligkeiten } : {};
    return this.request(
      "POST",
      `/ausleihen/${ausleiheId}/rueckgabe`,
      body,
      rolle
    );
  }

  // === UC-04: Prüfung abschließen ===
  async pruefungAbschliessen(
    ausleiheId,
    zustand,
    abzugCent = 0,
    rolle = "thekendienst"
  ) {
    return this.request(
      "POST",
      `/ausleihen/${ausleiheId}/pruefprotokoll`,
      { zustand, abzugCent },
      rolle
    );
  }

  // === UC-06: Verlust erfassen ===
  async verlustEinfassen(ausleiheId, rolle = "thekendienst") {
    return this.request(
      "POST",
      `/ausleihen/${ausleiheId}/verlust`,
      {},
      rolle
    );
  }

  // === UC-02: Ausleihe verlängern ===
  async ausleiheVerlaengern(ausleiheId, rolle = "mitglied") {
    return this.request(
      "POST",
      `/ausleihen/${ausleiheId}/verlaengerung`,
      {},
      rolle
    );
  }

  // === Hilfs-API: Gegenstand Details ===
  async getGegenstand(inventarnummer) {
    return this.request("GET", `/gegenstaende/${inventarnummer}`);
  }
}

// Global instance
window.api = new LeihgutApiClient();
