import os
import sys
import json

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

from ru_metadata_features import (
    COMPACT_FEATURES, compact_feature_vector, compact_row,
    shannon_entropy, spoofing_prefix_flag, repeat_digit_ratio,
    max_same_digit_run, beautiful_number_flag, compute_reputation_score,
    category_flags, number_type, infer_prefix_risk, clamp01,
    LABEL_TO_ID, ID_TO_LABEL,
)
from ru_number_normalizer import (
    normalize_ru_phone, is_russian_number, is_mobile_ru,
    is_landline_ru, is_tollfree_ru, is_short_code,
)


class TestFeatureCount:
    def test_feature_count_is_32(self):
        assert len(COMPACT_FEATURES) == 32

    def test_no_duplicate_features(self):
        assert len(COMPACT_FEATURES) == len(set(COMPACT_FEATURES))


class TestCompactFeatureVector:
    def test_has_all_features(self):
        # inBlacklist теперь отражает metadata, а не label (был leakage).
        features = compact_feature_vector(
            '+79001234567', 'BLOCK',
            {'negative_count': 10, 'positive_count': 0, 'review_count': 10,
             'categories': 'мошенничество', 'source_confidence': 0.9, 'is_valid_ru_range': True,
             'inBlacklist': True}
        )
        assert list(features.keys()) == COMPACT_FEATURES
        assert features['inBlacklist'] == 1.0
        assert features['reputationScore'] > 0.5

    def test_label_does_not_set_inblacklist(self):
        # Регресс-тест на фикс leakage: BLOCK label без metadata.inBlacklist => inBlacklist=0.
        features = compact_feature_vector(
            '+79001234567', 'BLOCK',
            {'negative_count': 10, 'review_count': 10, 'categories': 'мошенничество'}
        )
        assert features['inBlacklist'] == 0.0
        assert features['inAllowlist'] == 0.0

    def test_allow_label(self):
        features = compact_feature_vector(
            '+78005553535', 'ALLOW',
            {'negative_count': 0, 'positive_count': 5, 'review_count': 5,
             'categories': 'банк', 'source_confidence': 0.9, 'is_valid_ru_range': True,
             'inAllowlist': True}
        )
        assert features['inAllowlist'] == 1.0
        assert features['inBlacklist'] == 0.0

    def test_compact_row_length(self):
        row = compact_row('+79161234567', 'WARN', {'negative_count': 3, 'review_count': 5})
        assert len(row) == 32

    def test_all_values_in_range(self):
        features = compact_feature_vector(
            '+79161234567', 'WARN',
            {'negative_count': 3, 'review_count': 5, 'source_confidence': 0.5}
        )
        for name, val in features.items():
            assert isinstance(val, float), f'{name} is not float'
            assert 0.0 <= val <= 1.0, f'{name}={val} out of [0,1]'


class TestEntropy:
    def test_low_entropy(self):
        assert shannon_entropy('77777777777') < 0.1

    def test_high_entropy(self):
        assert shannon_entropy('79001234567') > 0.3

    def test_empty(self):
        assert shannon_entropy('') == 0.0

    def test_single_digit(self):
        assert shannon_entropy('1') == 0.0


class TestDigitPatterns:
    def test_repeat_digit_ratio(self):
        assert repeat_digit_ratio('1111') >= 0.9
        assert repeat_digit_ratio('1234') == 0.0

    def test_max_same_digit_run(self):
        assert max_same_digit_run('11122333') > 0.3
        assert max_same_digit_run('12345678') < 0.2

    def test_beautiful_number(self):
        assert beautiful_number_flag('1111111') is True
        assert beautiful_number_flag('1234567') is True


class TestSpoofing:
    def test_spoofing_prefix_flag(self):
        assert spoofing_prefix_flag('+84 95 123-45-67', '+84951234567') is True
        assert spoofing_prefix_flag('+7 495 123-45-67', '+74951234567') is False


class TestNormalizer:
    def test_basic(self):
        assert normalize_ru_phone('8 (800) 555-35-35') == '+78005553535'

    def test_plus7(self):
        assert normalize_ru_phone('+7 916 123-45-67') == '+79161234567'

    def test_international(self):
        assert normalize_ru_phone('+7 (495) 123-45-67') == '+74951234567'

    def test_invalid(self):
        assert normalize_ru_phone('not a number') is None

    def test_is_russian(self):
        assert is_russian_number('+79161234567') is True
        assert is_russian_number('+1234567890') is False

    def test_is_mobile(self):
        assert is_mobile_ru('+79161234567') is True
        assert is_mobile_ru('+74951234567') is False

    def test_is_landline(self):
        assert is_landline_ru('+74951234567') is True
        assert is_landline_ru('+79161234567') is False

    def test_is_tollfree(self):
        assert is_tollfree_ru('+78005553535') is True
        assert is_tollfree_ru('+79161234567') is False

    def test_is_short_code(self):
        assert is_short_code('+7112') is True
        assert is_short_code('+79161234567') is False


class TestNumberType:
    def test_mobile(self):
        assert number_type('+79161234567') == 'mobile'

    def test_tollfree(self):
        assert number_type('+78005553535') == 'tollfree'

    def test_landline(self):
        assert number_type('+74951234567') == 'landline'

    def test_foreign(self):
        assert number_type('+1234567890') == 'foreign'

    def test_unknown(self):
        assert number_type(None) == 'unknown'


class TestPrefixRisk:
    def test_tollfree_risk(self):
        assert infer_prefix_risk('+78005553535', {}) > 0.0

    def test_allowlist_zero(self):
        assert infer_prefix_risk('+79161234567', {'inAllowlist': True}) == 0.0

    def test_high_risk_def(self):
        risk = infer_prefix_risk('+79001234567', {})
        assert risk > 0.5


class TestReputationScore:
    def test_high_negative(self):
        flags = {'has_fraud_category': 1.0, 'has_telemarketing_category': 0.0}
        score = compute_reputation_score(0.9, 50, 1000, flags)
        assert score > 0.7

    def test_low_negative(self):
        flags = {'has_fraud_category': 0.0, 'has_telemarketing_category': 0.0}
        score = compute_reputation_score(0.1, 5, 10, flags)
        assert score < 0.3


class TestCategoryFlags:
    def test_fraud(self):
        flags = category_flags('мошенничество телефонное')
        assert flags['has_fraud_category'] == 1.0

    def test_telemarketing(self):
        flags = category_flags('спам реклама')
        assert flags['has_telemarketing_category'] == 1.0

    def test_finance(self):
        flags = category_flags('банк кредит')
        assert flags['has_finance_category'] == 1.0

    def test_clean(self):
        flags = category_flags('доставка еды')
        assert flags['has_fraud_category'] == 0.0


class TestClamp01:
    def test_normal(self):
        assert clamp01(0.5) == 0.5

    def test_over(self):
        assert clamp01(1.5) == 1.0

    def test_under(self):
        assert clamp01(-0.5) == 0.0

    def test_nan(self):
        assert clamp01(float('nan')) == 0.0

    def test_inf(self):
        assert clamp01(float('inf')) == 0.0


class TestSchemaSync:
    def test_feature_names_match_kotlin(self):
        kotlin_path = os.path.join(
            ROOT, 'app', 'src', 'main', 'java', 'com', 'antispam', 'blocker',
            'domain', 'tracking', 'DecisionTracker.kt'
        )
        if not os.path.exists(kotlin_path):
            return
        import re
        with open(kotlin_path, 'r', encoding='utf-8') as f:
            text = f.read()
        marker = 'val FEATURE_NAMES: List<String> = listOf('
        start = text.find(marker)
        if start < 0:
            return
        start += len(marker)
        end = text.find(')', start)
        block = text[start:end]
        kotlin_names = re.findall(r'"([A-Za-z0-9_]+)"', block)
        assert kotlin_names == COMPACT_FEATURES, f'Kotlin={kotlin_names} != Python={COMPACT_FEATURES}'

    def test_model_card_features_match(self):
        card_path = os.path.join(ROOT, 'app', 'src', 'main', 'assets', 'model_card.json')
        if not os.path.exists(card_path):
            return
        with open(card_path, 'r', encoding='utf-8') as f:
            card = json.load(f)
        assert card.get('features') == COMPACT_FEATURES
        assert card.get('feature_count') == 32


class TestDecisionTracking:
    def test_tracking_stats_fields(self):
        assert ID_TO_LABEL == {0: 'ALLOW', 1: 'WARN', 2: 'BLOCK'}

    def test_label_to_id_roundtrip(self):
        for label, lid in LABEL_TO_ID.items():
            assert ID_TO_LABEL[lid] == label
