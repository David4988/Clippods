"""The ASR experiment's CER must treat Indic vowel signs as characters, not punctuation."""
from evaluation.experiments.asr_model_compare import cer, normalise, script_share


def test_normalise_keeps_combining_vowel_signs_and_drops_punctuation():
    assert normalise("कबीर, अध्येता।") == "कबीरअध्येता"
    assert normalise("போகிறது.") == "போகிறது"
    assert normalise("Hello, World!") == "helloworld"


def test_cer_counts_vowel_sign_errors():
    assert cer("कबीर", "कबीर") == 0.0
    assert cer("कबीर", "कबर") == 0.25          # one missing vowel sign out of 4 code points
    assert cer("abc", "") == 1.0


def test_wrong_script_output_scores_zero_expected_script_share():
    assert script_share("استاد بسمل لاخان", "devanagari") == 0.0
    assert script_share("उस्ताद बिस्मिल्लाह", "devanagari") == 1.0
