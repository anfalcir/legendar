import io
import unittest

from scripts.phase0_fleurs import parse_reference_rows


class FleursTsvParserTests(unittest.TestCase):
    def test_parses_headerless_tsv_and_preserves_raw_reference(self):
        source = io.StringIO(
            "1860\t3120476782377592022.wav\tO gabinete afirmou 19 casos.\t"
            "o gabinete afirmou dezenove casos.\tignored\n"
            "1861\taudio/second.wav\tA segunda frase.\t"
            "a segunda frase\tignored\n"
        )
        rows = parse_reference_rows(source, samples_per_language=2)

        self.assertEqual(
            rows,
            [
                {
                    "id": "1860",
                    "filename": "3120476782377592022.wav",
                    "reference": "O gabinete afirmou 19 casos.",
                },
                {
                    "id": "1861",
                    "filename": "second.wav",
                    "reference": "A segunda frase.",
                },
            ],
        )

    def test_skips_invalid_and_duplicate_rows(self):
        source = io.StringIO(
            "\n"
            "bad\tonly-two-columns\n"
            "1\ta.wav\tvalid reference\n"
            "1\tduplicate.wav\tduplicate reference\n"
        )
        rows = parse_reference_rows(source, samples_per_language=5)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["filename"], "a.wav")

    def test_rejects_non_positive_sample_count(self):
        with self.assertRaises(ValueError):
            parse_reference_rows(io.StringIO(""), samples_per_language=0)


if __name__ == "__main__":
    unittest.main()
