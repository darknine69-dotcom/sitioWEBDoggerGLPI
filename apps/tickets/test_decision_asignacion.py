from django.test import SimpleTestCase

from apps.tickets.services.decision_asignacion import Candidato, elegir_candidato


class DecisionAsignacionTests(SimpleTestCase):
    def test_urgente_usa_ocupacion_y_no_conteo(self):
        decision = elegir_candidato([Candidato(1, 4, 10), Candidato(2, 5, 20)], "urgente")
        self.assertEqual(decision.candidato.pk, 2)

    def test_alta_prioriza_predeterminado_solo_en_empate(self):
        decision = elegir_candidato([Candidato(1, 2, 10), Candidato(2, 4, 20, predeterminado=True)], "alta")
        self.assertEqual(decision.candidato.pk, 2)

    def test_margen_es_en_puntos_porcentuales(self):
        bajo = Candidato(1, 0, 10)
        self.assertEqual(elegir_candidato([bajo, Candidato(2, 2, 10, predeterminado=True)], "media").candidato.pk, 2)
        self.assertEqual(elegir_candidato([bajo, Candidato(2, 3, 10, predeterminado=True)], "media").candidato.pk, 1)

    def test_capacidad_incluye_peso_nuevo_ticket(self):
        self.assertEqual(elegir_candidato([Candidato(1, 6, 10)], "urgente").motivo, "capacidad_insuficiente")
        self.assertEqual(elegir_candidato([], "baja").motivo, "sin_candidatos")

    def test_rotacion_utiliza_orden_y_id_en_empate(self):
        decision = elegir_candidato([Candidato(1, 0, 10, 9), Candidato(2, 0, 10, 3)], "alta")
        self.assertEqual(decision.candidato.pk, 2)

    def test_configuracion_invalida_se_rechaza(self):
        with self.assertRaises(ValueError):
            Candidato(1, 0, 0)
        with self.assertRaises(ValueError):
            elegir_candidato([], "media", margen_puntos=-1)
        with self.assertRaises(ValueError):
            elegir_candidato([], "media", pesos={"media": 0})
