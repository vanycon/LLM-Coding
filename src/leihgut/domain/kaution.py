"""Kautionsberechnung (BR-KAT-04, spec-domain-model.adoc, Validierungsregeln).

Reine Domänenfunktion ohne Seiteneffekte — ein einziger Berechnungsort für
die gesamte Anwendung (04_solution_strategy.adoc, "Korrektheit der
Kaution").
"""
KAUTION_MIN_CENT = 500
KAUTION_MAX_CENT = 10_000
KAUTION_ANTEIL = 0.2


def kaution_berechnen(wiederbeschaffungswert_cent: int) -> int:
    """Berechnet die Kaution: 20 % des Wiederbeschaffungswerts, kaufmännisch
    gerundet auf ganze Euro (BR-KAT-04), danach auf [5 €, 100 €] begrenzt.

    Das Ergebnis ist stets ein ganzzahliges Vielfaches von 100 Cent.
    """
    euro_gerundet = round(wiederbeschaffungswert_cent * KAUTION_ANTEIL / 100)
    cent = euro_gerundet * 100
    return max(KAUTION_MIN_CENT, min(KAUTION_MAX_CENT, cent))
