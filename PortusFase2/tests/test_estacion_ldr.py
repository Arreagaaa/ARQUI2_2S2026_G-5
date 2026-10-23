"""La luz relativa conserva la escala 0-100 esperada por el servidor."""
import unittest

from PortusFase3.estacion_pi import light_percentage


class EstacionLdr(unittest.TestCase):
    def test_dark_and_bright_calibration(self):
        self.assertEqual(light_percentage(0.4, 0.4, 2.8), 0.0)
        self.assertEqual(light_percentage(1.6, 0.4, 2.8), 50.0)
        self.assertEqual(light_percentage(2.8, 0.4, 2.8), 100.0)
        self.assertEqual(light_percentage(3.0, 0.4, 2.8), 100.0)

    def test_invalid_adc_voltage_fails_instead_of_publishing_false_light(self):
        with self.assertRaises(RuntimeError):
            light_percentage(float("nan"), 0.4, 2.8)
        with self.assertRaises(RuntimeError):
            light_percentage(4.0, 0.4, 2.8)

    def test_calibration_must_increase_with_light(self):
        with self.assertRaises(ValueError):
            light_percentage(1.0, 2.8, 0.4)


if __name__ == "__main__":
    unittest.main()
