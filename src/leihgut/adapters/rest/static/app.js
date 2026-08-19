/**
 * Leihgut Demo Frontend: Hauptanwendungslogik
 * 
 * Flows:
 * 1. Katalog durchsuchen + Verfügbarkeit anzeigen
 * 2. Gegenstand ausgeben (UC-01)
 * 3. Gegenstand zurücknehmen + Prüfung (UC-03/04)
 * 4. Verlust erfassen (UC-06)
 */

const app = {
  // ===== State =====
  state: {
    demoGegenstaende: [
      { inventarnummer: "INV-001", kategorie: "Bohrer", zustand: "verfuegbar" },
      { inventarnummer: "INV-002", kategorie: "Säge", zustand: "verfuegbar" },
      { inventarnummer: "INV-003", kategorie: "Schraubenzieher", zustand: "verfuegbar" },
      { inventarnummer: "INV-004", kategorie: "Hammer", zustand: "ausgeliehen" },
      { inventarnummer: "INV-005", kategorie: "Zange", zustand: "verfuegbar" },
    ],
    selectedGegenstand: null,
    currentRole: "thekendienst",
  },

  // ===== Init =====
  async init() {
    console.log("Leihgut Demo Frontend initializing...");
    this.render();
    this.attachEventListeners();
  },

  // ===== Rendering =====
  render() {
    document.getElementById("katalog").innerHTML = this.renderKatalog();
    document.getElementById("actions").innerHTML = this.renderActions();
  },

  renderKatalog() {
    const html = `
      <h2>Katalog</h2>
      <input 
        type="text" 
        id="search" 
        placeholder="Nach Inventarnummer suchen..." 
        class="search-input"
      />
      <div id="katalogListe" class="katalog-liste">
        ${this.state.demoGegenstaende
          .map(
            (g) => `
          <div class="gegenstand-card ${g.zustand}" data-inv="${g.inventarnummer}">
            <div class="inv-nummer">${g.inventarnummer}</div>
            <div class="kategorie">${g.kategorie}</div>
            <div class="zustand ${g.zustand}">${this.zustandLabel(g.zustand)}</div>
          </div>
        `
          )
          .join("")}
      </div>
    `;
    return html;
  },

  renderActions() {
    if (!this.state.selectedGegenstand) {
      return `<div class="placeholder">Bitte wählen Sie einen Gegenstand im Katalog aus.</div>`;
    }

    const g = this.state.selectedGegenstand;
    const html = `
      <h2>Aktion für ${g.inventarnummer}</h2>
      <div class="action-group">
        <p><strong>Kategorie:</strong> ${g.kategorie}</p>
        <p><strong>Status:</strong> <span class="zustand ${g.zustand}">${this.zustandLabel(g.zustand)}</span></p>
      </div>

      ${g.zustand === "verfuegbar" ? this.renderAusleihForm() : ""}
      ${g.zustand === "ausgeliehen" ? this.renderRueckgabeForm() : ""}
      ${g.zustand === "ausgeliehen" ? this.renderVerlustForm() : ""}
    `;
    return html;
  },

  renderAusleihForm() {
    return `
      <div class="form-section">
        <h3>Gegenstand Ausgeben</h3>
        <form id="ausleiheForm">
          <label for="mitgliedId">Mitglied-ID:</label>
          <input 
            type="text" 
            id="mitgliedId" 
            placeholder="z.B. M-001" 
            required 
          />
          <button type="submit" class="btn btn-primary">Ausgeben (UC-01)</button>
          <div id="ausleiheMessage" class="message"></div>
        </form>
      </div>
    `;
  },

  renderRueckgabeForm() {
    return `
      <div class="form-section">
        <h3>Gegenstand Zurücknehmen & Prüfen</h3>
        <form id="rueckgabeForm">
          <label for="ausleiheId">Ausleihe-ID:</label>
          <input 
            type="text" 
            id="ausleiheId" 
            placeholder="z.B. AUS-001" 
            required 
          />
          <label for="auffaelligkeiten">Mängel/Auffälligkeiten:</label>
          <textarea 
            id="auffaelligkeiten" 
            placeholder="z.B. 'Kratzer am Griff'" 
            rows="3"
          ></textarea>
          <button type="submit" class="btn btn-primary">Zurücknehmen (UC-03)</button>
          <div id="rueckgabeMessage" class="message"></div>
        </form>

        <form id="pruefungForm" style="display:none;">
          <h4>Prüfung Abschließen (UC-04)</h4>
          <label for="zustand">Zustand nach Prüfung:</label>
          <select id="zustand" required>
            <option value="">-- Wählen --</option>
            <option value="verfuegbar">Verfügbar</option>
            <option value="wartungsfaellig">Wartungsfällig</option>
            <option value="ausgemustert">Ausgemustert</option>
          </select>
          <label for="abzug">Kautionsabzug (€):</label>
          <input type="number" id="abzug" min="0" step="0.01" value="0" />
          <button type="submit" class="btn btn-primary">Prüfung abschließen</button>
          <div id="pruefungMessage" class="message"></div>
        </form>
      </div>
    `;
  },

  renderVerlustForm() {
    return `
      <div class="form-section warning">
        <h3>Verlust Erfassen (UC-06)</h3>
        <form id="verlustForm">
          <label for="verlustAusleiheId">Ausleihe-ID:</label>
          <input 
            type="text" 
            id="verlustAusleiheId" 
            placeholder="z.B. AUS-001" 
            required 
          />
          <p style="font-weight: bold; color: #c00;">
            ⚠ Kautionsbetrag wird einbehalten
          </p>
          <button type="submit" class="btn btn-danger">Verlust erfassen</button>
          <div id="verlustMessage" class="message"></div>
        </form>
      </div>
    `;
  },

  zustandLabel(zustand) {
    const labels = {
      verfuegbar: "✓ Verfügbar",
      ausgeliehen: "→ Ausgeliehen",
      in_pruefung: "⧗ In Prüfung",
      wartungsfaellig: "⚙ Wartungsfällig",
      ausgemustert: "✗ Ausgemustert",
    };
    return labels[zustand] || zustand;
  },

  // ===== Event Listeners =====
  attachEventListeners() {
    // Katalog: Gegenstand auswählen
    document.getElementById("katalog").addEventListener("click", (e) => {
      const card = e.target.closest(".gegenstand-card");
      if (card) {
        const inv = card.dataset.inv;
        this.state.selectedGegenstand = this.state.demoGegenstaende.find(
          (g) => g.inventarnummer === inv
        );
        this.render();
        this.attachEventListeners();
      }
    });

    // Suche
    const searchInput = document.getElementById("search");
    if (searchInput) {
      searchInput.addEventListener("input", (e) => {
        this.filterKatalog(e.target.value);
      });
    }

    // Formulare
    const ausleiheForm = document.getElementById("ausleiheForm");
    if (ausleiheForm) {
      ausleiheForm.addEventListener("submit", (e) => this.handleAusleihe(e));
    }

    const rueckgabeForm = document.getElementById("rueckgabeForm");
    if (rueckgabeForm) {
      rueckgabeForm.addEventListener("submit", (e) => this.handleRueckgabe(e));
    }

    const pruefungForm = document.getElementById("pruefungForm");
    if (pruefungForm) {
      pruefungForm.addEventListener("submit", (e) => this.handlePruefung(e));
    }

    const verlustForm = document.getElementById("verlustForm");
    if (verlustForm) {
      verlustForm.addEventListener("submit", (e) => this.handleVerlust(e));
    }
  },

  filterKatalog(query) {
    const cards = document.querySelectorAll(".gegenstand-card");
    cards.forEach((card) => {
      const inv = card.dataset.inv;
      const kategorie = card.textContent.toLowerCase();
      const matches =
        inv.toLowerCase().includes(query.toLowerCase()) ||
        kategorie.includes(query.toLowerCase());
      card.style.display = matches ? "block" : "none";
    });
  },

  // ===== API Calls =====
  async handleAusleihe(e) {
    e.preventDefault();
    const mitgliedId = document.getElementById("mitgliedId").value;
    const inv = this.state.selectedGegenstand.inventarnummer;
    const msg = document.getElementById("ausleiheMessage");

    try {
      msg.textContent = "Wird verarbeitet...";
      msg.className = "message info";

      const result = await window.api.gegenstandAusgeben(inv, mitgliedId);

      msg.textContent = `✓ Gegenstand an ${mitgliedId} ausgegeben (Ausleihe: ${result.ausleiheId})`;
      msg.className = "message success";

      // Update State
      this.state.selectedGegenstand.zustand = "ausgeliehen";
      setTimeout(() => this.render(), 2000);
    } catch (error) {
      msg.textContent = `✗ Fehler: ${error.message}`;
      msg.className = "message error";
    }
  },

  async handleRueckgabe(e) {
    e.preventDefault();
    const ausleiheId = document.getElementById("ausleiheId").value;
    const auffaelligkeiten = document.getElementById("auffaelligkeiten").value;
    const msg = document.getElementById("rueckgabeMessage");

    try {
      msg.textContent = "Wird verarbeitet...";
      msg.className = "message info";

      const result = await window.api.gegenstandZuruecknehmen(
        ausleiheId,
        auffaelligkeiten || null
      );

      msg.textContent = `✓ Gegenstand zurückgenommen (in Prüfung)`;
      msg.className = "message success";

      // Show Prüfung form
      document.getElementById("pruefungForm").style.display = "block";
      document.getElementById("ausleiheId").value = ausleiheId; // For next form

      // Update State
      this.state.selectedGegenstand.zustand = "in_pruefung";
      setTimeout(() => this.render(), 2000);
    } catch (error) {
      msg.textContent = `✗ Fehler: ${error.message}`;
      msg.className = "message error";
    }
  },

  async handlePruefung(e) {
    e.preventDefault();
    const ausleiheId = document.getElementById("ausleiheId").value;
    const zustand = document.getElementById("zustand").value;
    const abzugEuro = parseFloat(document.getElementById("abzug").value) || 0;
    const abzugCent = Math.round(abzugEuro * 100);
    const msg = document.getElementById("pruefungMessage");

    try {
      msg.textContent = "Wird verarbeitet...";
      msg.className = "message info";

      const result = await window.api.pruefungAbschliessen(
        ausleiheId,
        zustand,
        abzugCent
      );

      msg.textContent = `✓ Prüfung abgeschlossen (Zustand: ${zustand})`;
      msg.className = "message success";

      // Update State
      this.state.selectedGegenstand.zustand = zustand;
      setTimeout(() => this.render(), 2000);
    } catch (error) {
      msg.textContent = `✗ Fehler: ${error.message}`;
      msg.className = "message error";
    }
  },

  async handleVerlust(e) {
    e.preventDefault();
    const ausleiheId = document.getElementById("verlustAusleiheId").value;
    const msg = document.getElementById("verlustMessage");

    try {
      msg.textContent = "Wird verarbeitet...";
      msg.className = "message info";

      const result = await window.api.verlustEinfassen(ausleiheId);

      msg.textContent = `✓ Verlust erfasst (Kaution: ${(result.kaution_cent / 100).toFixed(2)}€)`;
      msg.className = "message success";

      // Update State
      this.state.selectedGegenstand.zustand = "ausgemustert";
      setTimeout(() => this.render(), 2000);
    } catch (error) {
      msg.textContent = `✗ Fehler: ${error.message}`;
      msg.className = "message error";
    }
  },
};

// ===== Startup =====
document.addEventListener("DOMContentLoaded", () => {
  app.init();
});
